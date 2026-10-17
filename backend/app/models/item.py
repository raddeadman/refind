from datetime import UTC, datetime, timedelta
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo import ASCENDING, DESCENDING, TEXT, IndexModel

from .common import (
    APPROX_TIME_PATTERN,
    BUILDINGS,
    CATEGORY_CODE_PATTERN,
    ItemStatus,
    ItemType,
    utcnow,
)

Building = Literal[BUILDINGS]  # type: ignore[valid-type]

MAX_PHOTOS = 4
CLOCK_SKEW = timedelta(minutes=2)


class Attributes(BaseModel):
    color: str | None = Field(default=None, max_length=30)
    brand: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=50)


class Location(BaseModel):
    building: Building
    floor: str | None = Field(default=None, max_length=30)
    area: str | None = Field(default=None, max_length=60)
    details: str | None = Field(default=None, max_length=300)


class StatusChange(BaseModel):
    status: ItemStatus
    at: datetime = Field(default_factory=utcnow)
    by: PydanticObjectId | None = None  # None = system (e.g. archive job)
    note: str | None = None


def _as_utc(value: datetime) -> datetime:
    # PyMongo returns naive datetimes that are already UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class Item(Document):
    type: ItemType
    title: str = Field(min_length=1, max_length=100)
    category: str = Field(pattern=CATEGORY_CODE_PATTERN)  # category code
    attributes: Attributes = Field(default_factory=Attributes)
    description: str | None = Field(default=None, max_length=1000)
    location: Location
    # Day the item was lost/found, stored as midnight UTC.
    date: datetime
    approxTime: str | None = Field(default=None, pattern=APPROX_TIME_PATTERN)
    # Set by the server, never by the client.
    timeSubmitted: datetime = Field(default_factory=utcnow)
    photoIds: list[PydanticObjectId] = Field(default_factory=list, max_length=MAX_PHOTOS)
    status: ItemStatus = ItemStatus.open
    reporterId: PydanticObjectId
    heldAt: str | None = Field(default=None, max_length=100)
    version: int = Field(default=1, ge=1)
    statusHistory: list[StatusChange] = Field(default_factory=list)

    @field_validator("date")
    @classmethod
    def _date_is_midnight_utc(cls, value: datetime) -> datetime:
        value = _as_utc(value).astimezone(UTC)
        return value.replace(hour=0, minute=0, second=0, microsecond=0)

    @model_validator(mode="after")
    def _not_after_submission(self) -> "Item":
        """date + approxTime cannot be in the future or after timeSubmitted."""
        submitted = _as_utc(self.timeSubmitted)
        if submitted > datetime.now(UTC) + CLOCK_SKEW:
            raise ValueError("timeSubmitted cannot be in the future")
        happened = self.date
        if self.approxTime:
            hours, minutes = map(int, self.approxTime.split(":"))
            happened = happened + timedelta(hours=hours, minutes=minutes)
        if happened > submitted + CLOCK_SKEW:
            raise ValueError("date/approxTime cannot be later than the time the report is submitted")
        return self

    class Settings:
        name = "items"
        indexes = [
            IndexModel(
                [("type", ASCENDING), ("category", ASCENDING), ("status", ASCENDING), ("date", DESCENDING)],
                name="type_category_status_date",
            ),
            IndexModel([("location.building", ASCENDING), ("date", DESCENDING)], name="building_date"),
            IndexModel([("reporterId", ASCENDING), ("timeSubmitted", DESCENDING)], name="reporter_submitted"),
            IndexModel([("status", ASCENDING), ("date", ASCENDING)], name="status_date"),
            IndexModel(
                [
                    ("title", TEXT),
                    ("description", TEXT),
                    ("location.details", TEXT),
                    ("attributes.brand", TEXT),
                ],
                weights={"title": 5, "attributes.brand": 3, "description": 1, "location.details": 1},
                name="item_text",
            ),
        ]
