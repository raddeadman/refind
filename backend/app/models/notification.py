from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from .common import NotificationType, utcnow

READ_RETENTION_SECONDS = 90 * 24 * 3600


class Notification(Document):
    userId: PydanticObjectId
    type: NotificationType
    message: str = Field(max_length=500)
    refId: PydanticObjectId | None = None
    # e.g. "new_match:<matchId>:<userId>"; unique, so a retried request can
    # never create the same alert twice (§4.3).
    dedupeKey: str
    readAt: datetime | None = None
    createdAt: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "notifications"
        indexes = [
            IndexModel([("dedupeKey", ASCENDING)], unique=True, name="dedupeKey_unique"),
            IndexModel([("userId", ASCENDING), ("createdAt", -1)], name="user_created"),
            # TTL: deleted 90 days after being read; unread ones (readAt null) are kept.
            IndexModel([("readAt", ASCENDING)], expireAfterSeconds=READ_RETENTION_SECONDS, name="readAt_ttl"),
        ]
