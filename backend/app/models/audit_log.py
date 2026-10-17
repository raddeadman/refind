from datetime import datetime
from typing import Any

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from .common import utcnow

RETENTION_SECONDS = 365 * 24 * 3600


class AuditLog(Document):
    actorId: PydanticObjectId | None  # None = system job
    action: str = Field(max_length=60)  # e.g. "claim.approve"
    targetCollection: str
    targetId: PydanticObjectId | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
    ip: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "auditLogs"
        indexes = [
            IndexModel([("timestamp", ASCENDING)], expireAfterSeconds=RETENTION_SECONDS, name="timestamp_ttl"),
            IndexModel([("targetCollection", ASCENDING), ("targetId", ASCENDING)], name="target"),
        ]
