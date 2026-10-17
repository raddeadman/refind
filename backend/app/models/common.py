"""Enums and helpers shared by every model.

Field names in the models are camelCase on purpose: they are exactly the
MongoDB field names from the proposal (§3), so raw queries, $jsonSchema
validators, the OpenAPI schema and the Orval TypeScript client all use the
same names.
"""

from datetime import UTC, datetime
from enum import StrEnum


def utcnow() -> datetime:
    # MongoDB stores milliseconds; trimming here keeps a document equal to
    # itself after a round trip.
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


class Role(StrEnum):
    user = "user"
    officer = "officer"
    admin = "admin"


class UserStatus(StrEnum):
    unverified = "unverified"
    active = "active"
    disabled = "disabled"


class ItemType(StrEnum):
    lost = "lost"
    found = "found"


class ItemStatus(StrEnum):
    open = "open"
    matched = "matched"
    claimed = "claimed"
    returned = "returned"
    archived = "archived"


class MatchStatus(StrEnum):
    suggested = "suggested"
    dismissed = "dismissed"
    confirmed = "confirmed"


class ClaimStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    locked = "locked"
    withdrawn = "withdrawn"


class NotificationType(StrEnum):
    new_match = "new_match"
    claim_update = "claim_update"
    handover_ready = "handover_ready"


# Fixed list of campus buildings (location.building is chosen from it, §3).
# TODO(team): replace with the real campus building names before seeding.
BUILDINGS: tuple[str, ...] = (
    "Library",
    "Building 1",
    "Building 2",
    "Building 3",
    "Building 4",
    "Building 5",
    "Engineering Building",
    "Science Building",
    "Business School",
    "Student Center",
    "Cafeteria",
    "Sports Complex",
    "Main Auditorium",
    "Administration Building",
    "Parking Area",
)

APPROX_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
CATEGORY_CODE_PATTERN = r"^[a-z0-9_-]{2,40}$"
BCRYPT_PATTERN = r"^\$2[aby]\$12\$"
