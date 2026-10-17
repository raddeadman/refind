from datetime import datetime
from typing import Annotated, Literal

from beanie import Document
from pydantic import AfterValidator, BaseModel, EmailStr, Field
from pymongo import ASCENDING, IndexModel

from .common import BCRYPT_PATTERN, Role, UserStatus, utcnow


class Profile(BaseModel):
    phone: str | None = Field(default=None, max_length=30)
    preferredContact: Literal["email", "phone"] = "email"


class EmailVerification(BaseModel):
    # Only the hash of the one-time token is stored (§5.2).
    tokenHash: str
    expiresAt: datetime


class User(Document):
    name: str = Field(min_length=1, max_length=100)
    email: Annotated[EmailStr, AfterValidator(str.lower)]
    # Written only by auth_service (always bcrypt, cost 12).
    # None for accounts that only sign in with Google.
    passwordHash: str | None = Field(default=None, pattern=BCRYPT_PATTERN)
    # Google's stable account id ("sub" claim) once Google sign-in is linked.
    googleSub: str | None = None
    role: Role = Role.user
    studentId: str | None = Field(default=None, max_length=20)
    status: UserStatus = UserStatus.unverified
    profile: Profile = Field(default_factory=Profile)
    emailVerification: EmailVerification | None = None
    createdAt: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True, name="email_unique"),
            IndexModel(
                [("googleSub", ASCENDING)],
                unique=True,
                partialFilterExpression={"googleSub": {"$type": "string"}},
                name="googleSub_unique",
            ),
            IndexModel([("emailVerification.tokenHash", ASCENDING)], sparse=True, name="verification_token"),
        ]
