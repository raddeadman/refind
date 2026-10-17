from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel

from ..models import Profile, User
from ..models.common import Role, UserStatus


class UserOut(BaseModel):
    """What the API returns for a user. passwordHash, googleSub and the
    verification token are not fields here, so they can never be sent."""

    id: PydanticObjectId
    name: str
    email: str
    role: Role
    status: UserStatus
    studentId: str | None
    profile: Profile
    createdAt: datetime
    hasPassword: bool
    googleLinked: bool

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(
            **user.model_dump(include={"id", "name", "email", "role", "status", "studentId", "profile", "createdAt"}),
            hasPassword=user.passwordHash is not None,
            googleLinked=user.googleSub is not None,
        )
