"""FastAPI dependencies: current user and RBAC (§5.1, §5.2).

Owner: Habib. Usage on a route:
    user: User = Depends(require_role(Role.officer, Role.admin))
"""

from typing import Annotated

import jwt
from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .models import User
from .models.common import Role, UserStatus
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_optional_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> User | None:
    """The logged-in user, or None for a guest. Invalid tokens are a 401."""
    if token is None:
        return None
    try:
        user_id = PydanticObjectId(decode_access_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise _UNAUTHORISED from None
    # Loaded on every request, so disabling an account takes effect
    # immediately instead of when the token expires.
    user = await User.get(user_id)
    if user is None or user.status == UserStatus.disabled:
        raise _UNAUTHORISED
    return user


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise _UNAUTHORISED
    return user


async def get_active_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Verified accounts only: needed to report items or submit claims."""
    if user.status != UserStatus.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verify your email first")
    return user


def require_role(*roles: Role):
    async def checker(user: Annotated[User, Depends(get_active_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return checker


CurrentUser = Annotated[User, Depends(get_current_user)]
ActiveUser = Annotated[User, Depends(get_active_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
AdminUser = Annotated[User, Depends(require_role(Role.admin))]
StaffUser = Annotated[User, Depends(require_role(Role.officer, Role.admin))]
