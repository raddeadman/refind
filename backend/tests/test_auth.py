"""Registration, email verification, login, rate limits and Google sign-in."""

from datetime import timedelta

import pytest

from app.errors import Forbidden
from app.models import AuditLog, User
from app.models.common import Role, UserStatus, utcnow
from app.services import auth_service, email_service
from app.services.auth_service import GoogleProfile

from .conftest import auth

DOMAIN = "university.edu"
NEW_USER = {"name": "Sara Ali", "email": f"sara@{DOMAIN}", "password": "correct-horse", "studentId": "F2300001"}


@pytest.fixture
def outbox(monkeypatch):
    """Captures verification emails instead of sending them."""
    sent: list[dict] = []

    async def fake_send(to: str, name: str, token: str) -> bool:
        sent.append({"to": to, "token": token})
        return True

    monkeypatch.setattr(email_service, "send_verification", fake_send)
    return sent


async def login(client, email=NEW_USER["email"], password=NEW_USER["password"]):
    return await client.post("/api/auth/login", data={"username": email, "password": password})


async def test_register_creates_unverified_user(client, outbox):
    response = await client.post("/api/auth/register", json=NEW_USER)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "unverified" and body["role"] == "user" and body["hasPassword"] is True
    assert "passwordHash" not in body and "emailVerification" not in body
    user = await User.find_one(User.email == NEW_USER["email"])
    assert user.passwordHash.startswith("$2b$12$")
    assert user.emailVerification.tokenHash != outbox[0]["token"]  # only the hash is stored
    assert await AuditLog.find_one(AuditLog.action == "user.register")


async def test_register_rules(client, outbox):
    other_domain = NEW_USER | {"email": "sara@gmail.com"}
    assert (await client.post("/api/auth/register", json=other_domain)).status_code == 403
    assert (await client.post("/api/auth/register", json=NEW_USER | {"password": "short"})).status_code == 422
    assert (await client.post("/api/auth/register", json=NEW_USER)).status_code == 201
    duplicate = NEW_USER | {"email": NEW_USER["email"].upper()}
    assert (await client.post("/api/auth/register", json=duplicate)).status_code == 409


async def test_verify_email(client, outbox):
    await client.post("/api/auth/register", json=NEW_USER)
    token = outbox[0]["token"]
    response = await client.post("/api/auth/verify-email", json={"token": token})
    assert response.status_code == 200 and response.json()["status"] == "active"
    # One-time: the same link cannot be used again.
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 400


async def test_expired_verification_link(client, outbox):
    await client.post("/api/auth/register", json=NEW_USER)
    user = await User.find_one(User.email == NEW_USER["email"])
    await user.set({"emailVerification.expiresAt": utcnow() - timedelta(minutes=1)})
    response = await client.post("/api/auth/verify-email", json={"token": outbox[0]["token"]})
    assert response.status_code == 400


async def test_resend_does_not_reveal_accounts(client, outbox):
    assert (await client.post("/api/auth/resend-verification", json={"email": f"nobody@{DOMAIN}"})).status_code == 202
    assert outbox == []
    await client.post("/api/auth/register", json=NEW_USER)
    await client.post("/api/auth/resend-verification", json={"email": NEW_USER["email"]})
    assert len(outbox) == 2 and outbox[0]["token"] != outbox[1]["token"]


async def test_login_and_me(client, outbox):
    await client.post("/api/auth/register", json=NEW_USER)
    response = await login(client)
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == NEW_USER["email"]
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await client.get("/api/auth/me", headers={"Authorization": "Bearer junk"})).status_code == 401


async def test_wrong_password_and_rate_limit(client, outbox):
    await client.post("/api/auth/register", json=NEW_USER)
    for _ in range(5):
        assert (await login(client, password="wrong-password")).status_code == 401
    # Locked out for 15 minutes, even with the right password.
    assert (await login(client)).status_code == 429
    # Unknown accounts get the same 401 as a wrong password.
    assert (await login(client, email=f"ghost@{DOMAIN}")).status_code == 401


async def test_disabled_user_cannot_log_in(client, make_user):
    user = await make_user(Role.user, UserStatus.disabled, email=f"off@{DOMAIN}")
    assert (await login(client, email=user.email, password="Password123!")).status_code == 403


async def test_change_password(client, make_user):
    user = await make_user(email=f"cp@{DOMAIN}")
    body = {"currentPassword": "wrong", "newPassword": "a-new-password"}
    assert (await client.post("/api/auth/change-password", json=body, headers=auth(user))).status_code == 401
    body["currentPassword"] = "Password123!"
    assert (await client.post("/api/auth/change-password", json=body, headers=auth(user))).status_code == 204
    assert (await login(client, email=user.email, password="a-new-password")).status_code == 200


async def test_providers(client):
    assert (await client.get("/api/auth/providers")).json() == {"google": False}
    assert (await client.get("/api/auth/google/login")).status_code == 503


# --- Google sign-in (service level: the redirect dance needs real Google) ---

def google(email=f"g@{DOMAIN}", sub="google-123", verified=True) -> GoogleProfile:
    return GoogleProfile(sub=sub, email=email, email_verified=verified, name="Google User")


async def test_google_creates_active_account_without_password():
    await auth_service.google_sign_in(google())
    user = await User.find_one(User.googleSub == "google-123")
    assert user.status == UserStatus.active and user.passwordHash is None
    # Signing in again finds the same account.
    await auth_service.google_sign_in(google())
    assert await User.count() == 1


async def test_google_links_existing_active_account(make_user):
    user = await make_user(email=f"g@{DOMAIN}")
    await auth_service.google_sign_in(google())
    user = await User.get(user.id)
    assert user.googleSub == "google-123" and user.passwordHash is not None


async def test_google_clears_password_of_unverified_squatter(make_user):
    # Someone registered the owner's email but never proved they own it...
    squatter = await make_user(status=UserStatus.unverified, email=f"g@{DOMAIN}")
    # ...then the real owner signs in with Google.
    await auth_service.google_sign_in(google())
    user = await User.get(squatter.id)
    assert user.status == UserStatus.active and user.passwordHash is None


@pytest.mark.parametrize("profile", [google(verified=False), google(email="g@gmail.com")])
async def test_google_rejects_unverified_or_outside_emails(profile):
    with pytest.raises(Forbidden):
        await auth_service.google_sign_in(profile)
    assert await User.count() == 0


async def test_google_rejects_disabled_account(make_user):
    await make_user(status=UserStatus.disabled, email=f"g@{DOMAIN}")
    with pytest.raises(Forbidden):
        await auth_service.google_sign_in(google())
