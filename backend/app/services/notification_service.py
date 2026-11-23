"""Notifications: written by other services, read by their owner (§4.3).

Owner: Abdullah. notify() is idempotent: it upserts on the unique
dedupeKey with $setOnInsert, so a retried request or a re-run transaction
can never create the same alert twice and never hits a duplicate-key error
(which would abort the surrounding transaction).
"""

from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from ..errors import NotFound
from ..models import Notification
from ..models.common import NotificationType, utcnow

MAX_PAGE_SIZE = 50


async def notify(
    user_id: PydanticObjectId,
    type: NotificationType,
    message: str,
    ref_id: PydanticObjectId | None,
    dedupe_key: str,
    session: AsyncClientSession | None = None,
) -> bool:
    """Create the notification unless one with this dedupeKey exists. True if created."""
    doc = Notification(userId=user_id, type=type, message=message[:500], refId=ref_id, dedupeKey=dedupe_key)
    result = await Notification.get_pymongo_collection().update_one(
        {"dedupeKey": dedupe_key},
        {"$setOnInsert": doc.model_dump(exclude={"id"})},
        upsert=True,
        session=session,
    )
    return result.upserted_id is not None


async def list_for(
    user_id: PydanticObjectId, *, unread_only: bool = False, page: int = 1, page_size: int = 20
) -> tuple[list[Notification], int, int]:
    """(page of notifications newest first, total, unread count). Uses the user_created index."""
    query: dict = {"userId": user_id}
    if unread_only:
        query["readAt"] = None
    total = await Notification.find(query).count()
    unread = await Notification.find({"userId": user_id, "readAt": None}).count()
    items = (
        await Notification.find(query).sort("-createdAt").skip((page - 1) * page_size).limit(page_size).to_list()
    )
    return items, total, unread


async def mark_read(notification_id: PydanticObjectId, user_id: PydanticObjectId) -> Notification:
    """Sets readAt once; the TTL index deletes it 90 days later. Another user's notification is a 404."""
    notification = await Notification.find_one({"_id": notification_id, "userId": user_id})
    if notification is None:
        raise NotFound("Notification not found")
    if notification.readAt is None:
        await notification.set({"readAt": utcnow()})
    return notification


async def mark_all_read(user_id: PydanticObjectId) -> int:
    result = await Notification.get_pymongo_collection().update_many(
        {"userId": user_id, "readAt": None}, {"$set": {"readAt": utcnow()}}
    )
    return result.modified_count
