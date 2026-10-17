"""Registration, email verification, login and Google sign-in (§5.2).

The only module that writes passwordHash. bcrypt runs in a worker thread so
the ~250 ms hash never blocks the event loop.
"""

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo.asynchronous.client_session import AsyncClientSession

from ..config import get_settings
from ..db import run_in_transaction
from ..errors import Conflict, Forbidden, ServiceError, TooManyRequests, Unauthorized
from ..models import EmailVerification, User
from ..models.common import UserStatus, utcnow
from ..security import create_access_token, hash_password, verify_password
from . import audit_service, email_service, rate_limit

VERIFICATION_TTL = timedelta(hours=24)
# Compared against when the email is unknown, so a failed login takes the same
# time whether or not the account exists.
_DUMMY_HASH = hash_password("timing-equaliser")


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    studentId: str | None = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("Password is too long")
        return value


class GoogleProfile(BaseModel):
    """The OpenID claims we use from Google's ID token."""

    sub: str
    email: EmailStr
    email_verified: bool = False
    name: str | None = None


def _hash_token(token: str) -> str:
    # The token is 256 random bits, so a fast hash is enough (unlike passwords).
    return hashlib.sha256(token.encode()).hexdigest()


def _new_verification() -> tuple[str, EmailVerification]:
    token = secrets.token_urlsafe(32)
    return token, EmailVerification(tokenHash=_hash_token(token), expiresAt=utcnow() + VERIFICATION_TTL)


def _check_domain(email: str) -> None:
    if not get_settings().email_domain_allowed(email):
        domains = ", ".join(get_settings().allowed_email_domains)
        raise Forbidden(f"Use your university email address ({domains})")


async def find_by_email(email: str, session: AsyncClientSession | None = None) -> User | None:
    return await User.find_one(User.email == email.lower(), session=session)


async def register(data: RegisterRequest, ip: str | None = None) -> User:
    _check_domain(data.email)
    password_hash = await asyncio.to_thread(hash_password, data.password)
    token, verification = _new_verification()

    async def txn(session: AsyncClientSession) -> User:
        if await find_by_email(data.email, session):
            raise Conflict("An account with this email already exists")
        user = User(
            name=data.name,
            email=data.email,
            passwordHash=password_hash,
            studentId=data.studentId,
            status=UserStatus.unverified,
            emailVerification=verification,
        )
        await user.insert(session=session)
        await audit_service.log(user.id, "user.register", "users", user.id, {"email": user.email}, ip, session)
        return user

    user = await run_in_transaction(txn)
    # Sent after the commit, so an email is never sent for a rolled-back account.
    await email_service.send_verification(user.email, user.name, token)
    return user


async def verify_email(token: str) -> User:
    async def txn(session: AsyncClientSession) -> User:
        user = await User.find_one({"emailVerification.tokenHash": _hash_token(token)}, session=session)
        expires = user.emailVerification.expiresAt if user and user.emailVerification else None
        if user is None or expires is None or expires.replace(tzinfo=expires.tzinfo or UTC) < datetime.now(UTC):
            raise ServiceError("This verification link is invalid or has expired")
        changes: dict = {"emailVerification": None}
        if user.status == UserStatus.unverified:
            changes["status"] = UserStatus.active
        await user.set(changes, session=session)
        await audit_service.log(user.id, "user.verify_email", "users", user.id, {"status": user.status}, session=session)
        return user

    return await run_in_transaction(txn)


async def resend_verification(email: str) -> None:
    """Always succeeds silently, so it cannot be used to discover accounts."""
    if not await rate_limit.hit(rate_limit.VERIFICATION_EMAILS, "verify-email", email.lower()):
        return
    user = await find_by_email(email)
    if user is None or user.status != UserStatus.unverified:
        return
    token, verification = _new_verification()
    await user.set({"emailVerification": verification})
    await email_service.send_verification(user.email, user.name, token)


async def login(email: str, password: str, ip: str) -> str:
    """Returns a JWT. 5 failed attempts per 15 minutes per account and IP."""
    key = ("login", email.lower(), ip)
    if await rate_limit.is_blocked(rate_limit.FAILED_LOGINS, *key):
        raise TooManyRequests("Too many failed logins. Try again in 15 minutes.")

    user = await find_by_email(email)
    stored = user.passwordHash if user and user.passwordHash else _DUMMY_HASH
    valid = await asyncio.to_thread(verify_password, password, stored)
    if user is None or user.passwordHash is None or not valid:
        await rate_limit.hit(rate_limit.FAILED_LOGINS, *key)
        raise Unauthorized("Incorrect email or password")

    await rate_limit.reset(rate_limit.FAILED_LOGINS, *key)
    if user.status == UserStatus.disabled:
        raise Forbidden("This account has been disabled")
    # Unverified users may log in (to see the "verify your email" banner)
    # but cannot report items or submit claims (deps.get_active_user).
    return create_access_token(str(user.id), user.role.value)


async def change_password(user: User, current: str, new: str) -> None:
    if user.passwordHash and not await asyncio.to_thread(verify_password, current, user.passwordHash):
        raise Unauthorized("Current password is incorrect")
    new_hash = await asyncio.to_thread(hash_password, new)

    async def txn(session: AsyncClientSession) -> None:
        await user.set({"passwordHash": new_hash}, session=session)
        await audit_service.log(user.id, "user.change_password", "users", user.id, session=session)

    await run_in_transaction(txn)


async def google_sign_in(profile: GoogleProfile, ip: str | None = None) -> str:
    """Find, link or create the account for a Google identity; returns a JWT.

    Google has proven the person owns the inbox, which is exactly what email
    verification proves, so these accounts are active straight away.
    """
    if not profile.email_verified:
        raise Forbidden("Your Google email address is not verified")
    _check_domain(profile.email)

    async def txn(session: AsyncClientSession) -> User:
        user = await User.find_one(User.googleSub == profile.sub, session=session)
        if user is None:
            user = await find_by_email(profile.email, session)
        if user is not None and user.status == UserStatus.disabled:
            raise Forbidden("This account has been disabled")

        if user is None:
            user = User(
                name=profile.name or profile.email.split("@")[0],
                email=profile.email,
                googleSub=profile.sub,
                status=UserStatus.active,
            )
            await user.insert(session=session)
            await audit_service.log(user.id, "user.register_google", "users", user.id, {"email": user.email}, ip, session)
        elif user.googleSub is None:
            changes: dict = {"googleSub": profile.sub}
            if user.status == UserStatus.unverified:
                # Nobody proved they own this inbox until now, so whoever set
                # the password may not be the owner: drop it (prevents an
                # account pre-registered with someone else's email from being
                # taken over once the real owner signs in with Google).
                changes |= {
                    "status": UserStatus.active,
                    "passwordHash": None,
                    "emailVerification": None,
                }
            await user.set(changes, session=session)
            await audit_service.log(
                user.id, "user.link_google", "users", user.id,
                {"passwordCleared": "passwordHash" in changes}, ip, session,
            )
        return user

    user = await run_in_transaction(txn)
    return create_access_token(str(user.id), user.role.value)
