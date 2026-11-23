from datetime import datetime
from typing import Literal

from beanie import PydanticObjectId
from pydantic import BaseModel

from ..models.common import MatchStatus, NotificationType
from .base import StrictModel
from .item import ItemView


class MatchOut(BaseModel):
    id: PydanticObjectId
    lostItemId: PydanticObjectId
    foundItemId: PydanticObjectId
    score: int
    reasons: list[str]
    status: MatchStatus
    createdAt: datetime
    # Each item in the view the caller is allowed to see.
    lostItem: ItemView
    foundItem: ItemView


class MatchPage(BaseModel):
    items: list[MatchOut]
    total: int
    page: int
    pageSize: int


class MatchStatusUpdate(StrictModel):
    """dismissed: either owner or an officer. confirmed: officers only."""

    status: Literal[MatchStatus.dismissed, MatchStatus.confirmed]


class NotificationOut(BaseModel):
    id: PydanticObjectId
    type: NotificationType
    message: str
    refId: PydanticObjectId | None
    readAt: datetime | None
    createdAt: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
    page: int
    pageSize: int
