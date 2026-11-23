"""M4: matching engine (§4.3), matches and notifications endpoints."""

from datetime import UTC, datetime, timedelta

import pytest
from beanie import PydanticObjectId

from app.models import AuditLog, Category, Item, Match, Notification
from app.models.common import ItemStatus, MatchStatus
from app.services import matching_service

from .conftest import auth


def day(offset: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=offset)).date().isoformat()


FOUND = {
    "type": "found",
    "title": "Black wallet",
    "category": "wallets",
    "attributes": {"color": "Black", "brand": "Tommy Hilfiger"},
    "location": {"building": "Library", "floor": "Ground", "area": "Entrance", "details": "On the bench by the entrance"},
    "date": day(1),
    "approxTime": "14:30",
    "verification": [{"question": "What name is on the ID card?", "answer": "Ahmed"}],
}
LOST = {
    "type": "lost",
    "title": "My wallet",
    "category": "wallets",
    "attributes": {"color": "black ", "brand": "tommy hilfiger"},
    "location": {"building": "Library", "floor": "ground", "area": "entrance", "details": "Probably at the entrance"},
    "date": day(1),
    "approxTime": "13:45",
}


@pytest.fixture(autouse=True)
async def categories():
    await Category(code="wallets", name="Wallets").insert()
    await Category(code="phones", name="Phones").insert()


async def report(client, user, body):
    response = await client.post("/api/items", json=body, headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------- engine


async def test_perfect_pair_scores_100_with_reasons(client, make_user):
    owner, finder = await make_user(), await make_user()
    found = await report(client, finder, FOUND)
    assert found["status"] == "open"  # nothing to match yet

    lost = await report(client, owner, LOST)
    assert lost["status"] == "matched"  # returned after matching ran

    match = await Match.find_one()
    assert match.lostItemId == PydanticObjectId(lost["id"]) and match.foundItemId == PydanticObjectId(found["id"])
    assert match.score == 100 and match.status == MatchStatus.suggested
    assert "same building (Library)" in match.reasons and "same colour (Black)" in match.reasons
    assert "similar time of day" in match.reasons
    assert any("'entrance'" in r for r in match.reasons)
    assert (await Item.get(found["id"])).status == ItemStatus.matched

    # Only the owner of the lost item is told, once.
    notes = await Notification.find_all().to_list()
    assert [n.userId for n in notes] == [owner.id]
    assert notes[0].dedupeKey == f"new_match:{match.id}:{owner.id}"
    assert await AuditLog.find(AuditLog.action == "match.create").count() == 1


async def test_resaving_creates_no_new_match_or_alert(client, make_user):
    owner, finder = await make_user(), await make_user()
    await report(client, finder, FOUND)
    lost = await report(client, owner, LOST)
    match = await Match.find_one()

    # Edit a matching field: matching runs again, the pair is already known.
    response = await client.patch(f"/api/items/{lost['id']}", json={"version": lost["version"], "approxTime": "14:00"},
                                  headers=auth(owner))
    assert response.status_code == 200, response.text
    # Running the engine directly again changes nothing either.
    assert await matching_service.on_item_saved(await Item.get(lost["id"])) == []

    assert await Match.count() == 1 and await Notification.count() == 1
    assert (await Match.get(match.id)).score == match.score  # $setOnInsert: left untouched


@pytest.mark.parametrize(
    "change",
    [
        {"category": "phones"},  # different category
        {"date": day(9)},  # more than 7 days apart
        {"location": {"building": "Cafeteria"}, "attributes": {}, "approxTime": None},  # too little in common
    ],
)
async def test_no_match_when_not_alike(client, make_user, change):
    owner, finder = await make_user(), await make_user()
    await report(client, finder, FOUND)
    lost = await report(client, owner, LOST | change)
    assert lost["status"] == "open"
    assert await Match.count() == 0 and await Notification.count() == 0


async def test_score_parts():
    # Same category + building + same day, nothing else: 30 + 15 + 16 = 61, just above the threshold.
    finder, owner = PydanticObjectId(), PydanticObjectId()
    now = datetime.now(UTC) - timedelta(days=1)
    found = await Item(type="found", title="Wallet", category="wallets", location={"building": "Library"},
                       date=now, reporterId=finder).insert()
    lost = Item(type="lost", title="Wallet", category="wallets", location={"building": "Library"},
                date=now, reporterId=owner)
    await lost.insert()
    [candidate] = await matching_service.find_candidates(lost)
    assert candidate["_id"] == found.id and candidate["score"] == 61
    assert candidate["reasons"] == ["same category", "same building (Library)", "same day"]

    # One day apart: 30 + 15 + 13 = 58 -> dropped.
    await lost.set({"date": now - timedelta(days=1)})
    assert await matching_service.find_candidates(lost) == []


async def test_own_items_and_closed_items_are_not_candidates(client, make_user):
    user = await make_user()
    await report(client, user, FOUND)
    lost = await report(client, user, LOST)  # same reporter
    assert lost["status"] == "open" and await Match.count() == 0


async def test_user_values_are_literals_in_the_pipeline(client, make_user):
    owner, finder = await make_user(), await make_user()
    # A colour that looks like a field path must not compare equal to the title.
    await report(client, finder, FOUND | {"title": "$title", "attributes": {"color": "$title"}})
    await report(client, owner, LOST | {"title": "$title", "attributes": {"color": "$title"}})
    match = await Match.find_one()
    assert "same colour ($title)" in match.reasons


async def test_best_five_only(client, make_user):
    owner = await make_user()
    for _ in range(7):
        await report(client, await make_user(), FOUND)
    await report(client, owner, LOST)
    assert await Match.count() == 5
    assert await Notification.find(Notification.userId == owner.id).count() == 5
