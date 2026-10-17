from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from .common import MatchStatus, utcnow

_CONFIRMED = {"status": MatchStatus.confirmed.value}


class Match(Document):
    lostItemId: PydanticObjectId
    foundItemId: PydanticObjectId
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    status: MatchStatus = MatchStatus.suggested
    createdAt: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "matches"
        indexes = [
            # The same lost/found pair is never suggested twice.
            IndexModel([("lostItemId", ASCENDING), ("foundItemId", ASCENDING)], unique=True, name="pair_unique"),
            # At most one *confirmed* match per lost item and per found item (§4.3).
            IndexModel(
                [("lostItemId", ASCENDING)],
                unique=True,
                partialFilterExpression=_CONFIRMED,
                name="lost_confirmed_unique",
            ),
            IndexModel(
                [("foundItemId", ASCENDING)],
                unique=True,
                partialFilterExpression=_CONFIRMED,
                name="found_confirmed_unique",
            ),
        ]
