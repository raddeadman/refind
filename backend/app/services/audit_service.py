"""Every service function that changes data calls log() explicitly (§4.5).

Pass the transaction's session so the change and its audit entry commit or
roll back together.
"""

from typing import Any

from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from ..models import AuditLog


async def log(
    actor_id: PydanticObjectId | None,
    action: str,
    target_collection: str,
    target_id: PydanticObjectId | None = None,
    changes: dict[str, Any] | None = None,
    ip: str | None = None,
    session: AsyncClientSession | None = None,
) -> AuditLog:
    entry = AuditLog(
        actorId=actor_id,
        action=action,
        targetCollection=target_collection,
        targetId=target_id,
        changes=changes or {},
        ip=ip,
    )
    await entry.insert(session=session)
    return entry
