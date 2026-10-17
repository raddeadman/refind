"""Auth endpoints (§4.2, §5.2). Owner: Habib."""

import logging
from typing import Annotated
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..deps import CurrentUser
from ..errors import ServiceError
from ..schemas.user import UserOut
from ..services import auth_service
from ..services.auth_service import GoogleProfile, RegisterRequest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth = OAuth()
_settings = get_settings()
if _settings.google_enabled:
    oauth.register(
        "google",
        client_id=_settings.google_client_id,
        client_secret=_settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResendRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    currentPassword: str = ""
    newPassword: str = Field(min_length=8, max_length=72)


class Providers(BaseModel):
    google: bool


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, request: Request) -> UserOut:
    """Create an unverified account and email a verification link."""
    return UserOut.of(await auth_service.register(data, _ip(request)))


@router.post("/verify-email", response_model=UserOut)
async def verify_email(data: VerifyEmailRequest) -> UserOut:
    return UserOut.of(await auth_service.verify_email(data.token))


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(data: ResendRequest) -> None:
    await auth_service.resend_verification(data.email)


@router.post("/login", response_model=Token)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request) -> Token:
    """OAuth2 password flow, so the Authorize button in /docs works.
    `username` is the email address."""
    return Token(access_token=await auth_service.login(form.username, form.password, _ip(request)))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.of(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(data: ChangePasswordRequest, user: CurrentUser) -> None:
    await auth_service.change_password(user, data.currentPassword, data.newPassword)


@router.get("/providers", response_model=Providers)
async def providers() -> Providers:
    """Which sign-in buttons the front end should show."""
    return Providers(google=get_settings().google_enabled)


# --- Google sign-in (OpenID Connect, authorisation-code flow) -------------
# Browser -> /google/login -> Google -> /google/callback -> SPA /auth/callback#token=...
# Both URLs go through the front end's origin (Vite proxies /api), so the
# short-lived state cookie set here is sent back on the callback.


def _to_frontend(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{get_settings().frontend_url}{path}{query}", status_code=status.HTTP_302_FOUND)


@router.get("/google/login", include_in_schema=False)
async def google_login(request: Request):
    settings = get_settings()
    if not settings.google_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not configured")
    redirect_uri = f"{settings.frontend_url}/api/auth/google/callback"
    extra = {"prompt": "select_account"}
    if len(settings.allowed_email_domains) == 1:
        extra["hd"] = settings.allowed_email_domains[0]  # hint Google to show university accounts
    return await oauth.google.authorize_redirect(request, redirect_uri, **extra)


@router.get("/google/callback", include_in_schema=False)
async def google_callback(request: Request):
    if not get_settings().google_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not configured")
    try:
        token = await oauth.google.authorize_access_token(request)
        profile = GoogleProfile.model_validate(token["userinfo"])
        jwt = await auth_service.google_sign_in(profile, _ip(request))
    except OAuthError as exc:
        log.warning("Google sign-in failed: %s", exc)
        return _to_frontend("/login", error="Google sign-in was cancelled or failed")
    except ServiceError as exc:
        return _to_frontend("/login", error=exc.detail)
    # In the URL fragment, which browsers never send to a server or log.
    return _to_frontend(f"/auth/callback#token={jwt}")
