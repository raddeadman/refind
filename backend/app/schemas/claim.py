"""Request and response models for claims (§5.2, §5.4). Owner: Habib."""

from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from ..models import ClaimAnswer, Handover
from ..models.common import ClaimStatus
from .base import StrictModel
from .item import ItemView

# ---------------------------------------------------------------- requests


class ClaimCreate(StrictModel):
    itemId: PydanticObjectId
    # One answer per verification question, in the order GET /items/{id}/questions returned them.
    answers: list[str] = Field(min_length=1, max_length=5, examples=[["Ahmed Ali"]])
    proofNote: str | None = Field(default=None, max_length=1000, examples=["Bought it at the campus bookshop"])


class HandoverIn(StrictModel):
    # The officer looked at the claimant's university ID card in person.
    idChecked: bool
    idLast4: str = Field(pattern=r"^\d{4}$", examples=["1234"])


class ReviewNote(StrictModel):
    note: str | None = Field(default=None, max_length=300)


# --------------------------------------------------------------- responses


class Questions(BaseModel):
    itemId: PydanticObjectId
    questions: list[str]


class ClaimantOut(BaseModel):
    """Contact details, shown only to officers for the handover (§5.1)."""

    id: PydanticObjectId
    name: str
    email: str
    studentId: str | None
    phone: str | None


class ClaimOut(BaseModel):
    id: PydanticObjectId
    itemId: PydanticObjectId
    matchId: PydanticObjectId | None
    status: ClaimStatus
    answers: list[ClaimAnswer]
    proofNote: str | None
    failedAttempts: int
    submittedAt: datetime
    reviewedBy: PydanticObjectId | None
    reviewedAt: datetime | None
    handover: Handover | None
    item: ItemView
    claimant: ClaimantOut | None = None


class ClaimPage(BaseModel):
    items: list[ClaimOut]
    total: int
    page: int
    pageSize: int
