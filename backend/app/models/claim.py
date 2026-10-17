from datetime import datetime

from beanie import Document, Link, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from .common import ClaimStatus, utcnow
from .user import User


class ClaimAnswer(BaseModel):
    # What the claimant typed; shown to the officer, who compares it with
    # the physical item (§5.2).
    question: str
    answer: str = Field(max_length=200)


class Handover(BaseModel):
    at: datetime = Field(default_factory=utcnow)
    officerId: PydanticObjectId
    idChecked: bool
    idLast4: str = Field(pattern=r"^\d{4}$")


class Claim(Document):
    itemId: PydanticObjectId  # the found item
    # Stored as a DBRef; claim.claimantId.fetch() loads the user (§4.5 Links).
    claimantId: Link[User]
    # None when the claimant never filed a lost report.
    matchId: PydanticObjectId | None = None
    answers: list[ClaimAnswer] = Field(default_factory=list)
    proofNote: str | None = Field(default=None, max_length=1000)
    status: ClaimStatus = ClaimStatus.pending
    failedAttempts: int = Field(default=0, ge=0)
    submittedAt: datetime = Field(default_factory=utcnow)
    reviewedBy: PydanticObjectId | None = None
    reviewedAt: datetime | None = None
    handover: Handover | None = None

    class Settings:
        name = "claims"
        indexes = [
            IndexModel([("itemId", ASCENDING), ("claimantId", ASCENDING)], unique=True, name="item_claimant_unique"),
            IndexModel([("status", ASCENDING), ("submittedAt", ASCENDING)], name="review_queue"),
        ]
