"""Request and response models for items (§3, §5.1).

Responses come in three views. Each view is its own model, so a field that
a viewer may not see is simply not part of the model and can never be sent:

    public  guests                      category, building, date, generic title
    member  any logged-in user          + colour and brand
    full    reporter, officer, admin    everything (photos, description, ...)

The `access` field tells the front end which view it received.
"""

from datetime import UTC, datetime, time
from datetime import date as Date  # aliased: fields are also named "date"
from typing import Annotated, Literal

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import Attributes, Item, Location, StatusChange
from ..models.common import APPROX_TIME_PATTERN, CATEGORY_CODE_PATTERN, ItemStatus, ItemType
from ..models.item import CLOCK_SKEW, Building, happened_at

# ---------------------------------------------------------------- requests


class VerificationIn(BaseModel):
    question: str = Field(min_length=3, max_length=200, examples=["What name is on the ID card?"])
    # Hashed with bcrypt before it is stored; never returned.
    answer: str = Field(min_length=1, max_length=100, examples=["Ahmed"])


def midnight_utc(day: Date) -> datetime:
    """How `date` is stored: the calendar day at midnight UTC."""
    return datetime.combine(day, time(), tzinfo=UTC)


class _ItemFields(BaseModel):
    title: str = Field(min_length=1, max_length=100, examples=["Black wallet"])
    category: str = Field(pattern=CATEGORY_CODE_PATTERN, examples=["wallets"])
    attributes: Attributes = Field(default_factory=Attributes)
    description: str | None = Field(default=None, max_length=1000)
    location: Location
    date: Date = Field(description="Day the item was lost or found (YYYY-MM-DD).")
    approxTime: str | None = Field(default=None, pattern=APPROX_TIME_PATTERN, examples=["14:30"])
    heldAt: str | None = Field(default=None, max_length=100, examples=["Security office, Building 5"])


class ItemCreate(_ItemFields):
    type: ItemType
    # Found items only: at least one question; answers are hashed (§5.2).
    verification: list[VerificationIn] = Field(default_factory=list, max_length=5)
    serialNumber: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _check(self) -> "ItemCreate":
        if happened_at(midnight_utc(self.date), self.approxTime) > datetime.now(UTC) + CLOCK_SKEW:
            raise ValueError("date/approxTime cannot be in the future")
        if self.type == ItemType.found:
            if not self.verification:
                raise ValueError("A found item needs at least one verification question")
        else:
            if self.verification or self.serialNumber:
                raise ValueError("Only found items have verification questions or a serial number")
            if self.heldAt:
                raise ValueError("Only found items have heldAt")
        return self


class ItemUpdate(BaseModel):
    """Fields left out are unchanged. `version` must be the version the
    client last read; if someone else saved in between, the API returns 409."""

    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, pattern=CATEGORY_CODE_PATTERN)
    attributes: Attributes | None = None
    description: str | None = Field(default=None, max_length=1000)
    location: Location | None = None
    date: Date | None = None
    approxTime: str | None = Field(default=None, pattern=APPROX_TIME_PATTERN)
    heldAt: str | None = Field(default=None, max_length=100)


# --------------------------------------------------------------- responses


class LocationPublic(BaseModel):
    building: Building


class AttributesMember(BaseModel):
    color: str | None = None
    brand: str | None = None


class ItemPublic(BaseModel):
    # Marks `access` as always present in the OpenAPI/TypeScript types.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    access: Literal["public"] = "public"
    id: PydanticObjectId
    type: ItemType
    title: str
    category: str
    location: LocationPublic
    date: datetime
    status: ItemStatus


class ItemMember(ItemPublic):
    access: Literal["member"] = "member"  # type: ignore[assignment]
    attributes: AttributesMember


class ItemFull(ItemPublic):
    access: Literal["full"] = "full"  # type: ignore[assignment]
    attributes: Attributes
    description: str | None
    location: Location  # type: ignore[assignment]
    approxTime: str | None
    timeSubmitted: datetime
    photoIds: list[PydanticObjectId]
    reporterId: PydanticObjectId
    heldAt: str | None
    version: int
    statusHistory: list[StatusChange]


ItemView = Annotated[ItemPublic | ItemMember | ItemFull, Field(discriminator="access")]

_VIEWS: dict[str, type[ItemPublic]] = {"public": ItemPublic, "member": ItemMember, "full": ItemFull}


def view_of(item: Item, access: Literal["public", "member", "full"]) -> ItemPublic:
    model = _VIEWS[access]
    # Only the fields declared on the view are copied.
    fields = set(model.model_fields) - {"access"}
    data = item.model_dump(include=fields)
    return model.model_validate(data)


class ItemPage(BaseModel):
    items: list[ItemView]
    total: int
    page: int
    pageSize: int
