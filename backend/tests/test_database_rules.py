"""M2 acceptance: models, validators, indexes and transactions."""

from datetime import UTC, datetime, timedelta

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, OperationFailure, WriteError

from app.db import get_db, run_in_transaction
from app.models import Category, Item, Match, Notification, User
from app.models.common import MatchStatus


def make_item(**overrides) -> Item:
    data = dict(
        type="found",
        title="Black wallet",
        category="wallets",
        location={"building": "Library"},
        date=datetime.now(UTC),
        reporterId=PydanticObjectId(),
    )
    return Item(**(data | overrides))


async def test_jsonschema_rejects_plaintext_password():
    # A raw insert that bypasses Pydantic is still stopped by the database.
    with pytest.raises(WriteError) as exc:
        await User.get_pymongo_collection().insert_one(
            {"name": "x", "email": "x@university.edu", "passwordHash": "hunter2",
             "role": "user", "status": "active", "createdAt": datetime.now(UTC)}
        )
    assert exc.value.code == 121  # DocumentValidationFailure


async def test_jsonschema_rejects_unknown_building():
    item = make_item().model_dump(exclude={"id"})
    item["location"]["building"] = "Mars"
    with pytest.raises(WriteError):
        await Item.get_pymongo_collection().insert_one(item)


async def test_api_account_cannot_remove_validators():
    with pytest.raises(OperationFailure) as exc:
        await get_db().command("collMod", "users", validator={})
    assert exc.value.code == 13  # Unauthorized


async def test_email_is_unique(make_user):
    await make_user(email="dup@university.edu")
    with pytest.raises(DuplicateKeyError):
        await make_user(email="DUP@university.edu")  # stored lower-case


def test_item_date_cannot_be_after_submission():
    with pytest.raises(ValidationError, match="later than"):
        make_item(date=datetime.now(UTC) + timedelta(days=1))
    with pytest.raises(ValidationError):
        make_item(approxTime="25:00")
    with pytest.raises(ValidationError):
        make_item(location={"building": "Mars"})


async def test_only_one_confirmed_match_per_item():
    lost, found, other_lost = PydanticObjectId(), PydanticObjectId(), PydanticObjectId()
    await Match(lostItemId=lost, foundItemId=found, score=80, status=MatchStatus.confirmed).insert()
    # Several *suggested* matches for the same found item are fine...
    await Match(lostItemId=other_lost, foundItemId=found, score=70).insert()
    # ...but a second confirmed one is rejected by the partial unique index.
    with pytest.raises(DuplicateKeyError):
        await Match.find_one(Match.lostItemId == other_lost).set({Match.status: MatchStatus.confirmed})
    # And the same pair is never suggested twice.
    with pytest.raises(DuplicateKeyError):
        await Match(lostItemId=lost, foundItemId=found, score=90).insert()


async def test_notification_dedupe_key():
    data = dict(userId=PydanticObjectId(), type="new_match", message="m", dedupeKey="new_match:1:2")
    await Notification(**data).insert()
    with pytest.raises(DuplicateKeyError):
        await Notification(**data).insert()


async def test_ttl_indexes_exist():
    notif = await Notification.get_pymongo_collection().index_information()
    audit = await get_db()["auditLogs"].index_information()
    assert notif["readAt_ttl"]["expireAfterSeconds"] == 90 * 24 * 3600
    assert audit["timestamp_ttl"]["expireAfterSeconds"] == 365 * 24 * 3600


async def test_transaction_commits():
    async def txn(session):
        await Category(code="wallets", name="Wallets").insert(session=session)
        await Category(code="keys", name="Keys").insert(session=session)

    await run_in_transaction(txn)
    assert await Category.count() == 2


async def test_transaction_rolls_back_on_error():
    async def txn(session):
        await Category(code="wallets", name="Wallets").insert(session=session)
        await Category(code="wallets", name="Duplicate").insert(session=session)

    with pytest.raises(DuplicateKeyError):
        await run_in_transaction(txn)
    assert await Category.count() == 0  # the first insert was rolled back too
