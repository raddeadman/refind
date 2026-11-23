"""Matches and notifications (§4.3). Owner: Abdullah."""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Query

from ..deps import ActiveUser, CurrentUser, StaffUser
from ..models.common import MatchStatus
from ..schemas.match import MatchOut, MatchPage, MatchStatusUpdate, NotificationOut, NotificationPage
from ..services import match_service, notification_service

router = APIRouter(prefix="/api/matches", tags=["matches"])
notifications_router = APIRouter(prefix="/api/notifications", tags=["notifications"])

PageSize = Annotated[int, Query(ge=1, le=50)]
Page = Annotated[int, Query(ge=1)]


@router.get("/mine", response_model=MatchPage, summary="Matches for my own items, best first")
async def list_my_matches(user: CurrentUser, status: MatchStatus | None = None, page: Page = 1,
                          pageSize: PageSize = 20) -> MatchPage:
    return await match_service.list_matches(user, status=status, mine=True, page=page, page_size=pageSize)


@router.get("", response_model=MatchPage, summary="All matches (officer)")
async def list_matches(officer: StaffUser, status: MatchStatus | None = None, page: Page = 1,
                       pageSize: PageSize = 20) -> MatchPage:
    return await match_service.list_matches(officer, status=status, mine=False, page=page, page_size=pageSize)


@router.get("/{match_id}", response_model=MatchOut, summary="One match (its owners or an officer)")
async def get_match(match_id: PydanticObjectId, user: CurrentUser) -> MatchOut:
    return await match_service.get_for(match_id, user)


@router.patch("/{match_id}", response_model=MatchOut,
              summary="Dismiss (owner or officer) or confirm (officer) a suggested match")
async def update_match(match_id: PydanticObjectId, data: MatchStatusUpdate, user: ActiveUser) -> MatchOut:
    return await match_service.set_status(match_id, data.status, user)


@notifications_router.get("", response_model=NotificationPage, summary="My notifications, newest first")
async def list_notifications(user: CurrentUser, unreadOnly: bool = False, page: Page = 1,
                             pageSize: PageSize = 20) -> NotificationPage:
    items, total, unread = await notification_service.list_for(
        user.id, unread_only=unreadOnly, page=page, page_size=pageSize
    )
    return NotificationPage(items=[NotificationOut(**n.model_dump()) for n in items], total=total, unread=unread,
                            page=page, pageSize=pageSize)


@notifications_router.patch("/{notification_id}/read", response_model=NotificationOut, summary="Mark as read")
async def mark_notification_read(notification_id: PydanticObjectId, user: CurrentUser) -> NotificationOut:
    return NotificationOut(**(await notification_service.mark_read(notification_id, user.id)).model_dump())


@notifications_router.post("/read-all", summary="Mark all my notifications as read")
async def mark_all_notifications_read(user: CurrentUser) -> dict[str, int]:
    return {"updated": await notification_service.mark_all_read(user.id)}
