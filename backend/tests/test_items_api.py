"""M3: report, search, view, edit, withdraw items; photos in GridFS."""

from datetime import UTC, datetime, timedelta

import pytest
from beanie import PydanticObjectId

from app.models import AuditLog, Category, Item, ItemSecret
from app.models.common import ItemStatus, Role, UserStatus

from .conftest import auth

YESTERDAY = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

FOUND = {
    "type": "found",
    "title": "Black wallet",
    "category": "wallets",
    "attributes": {"color": "black", "brand": "Tommy Hilfiger"},
    "description": "Leather wallet near the entrance",
    "location": {"building": "Library", "floor": "Ground", "area": "Entrance", "details": "On the bench"},
    "date": YESTERDAY,
    "approxTime": "14:30",
    "heldAt": "Security office",
    "verification": [{"question": "What name is on the ID card?", "answer": "Ahmed  Ali!"}],
    "serialNumber": "SN-123",
}
LOST = {k: v for k, v in FOUND.items() if k not in {"verification", "serialNumber", "heldAt"}} | {"type": "lost"}


@pytest.fixture(autouse=True)
async def categories():
    await Category(code="wallets", name="Wallets").insert()
    await Category(code="phones", name="Phones").insert()


async def report(client, user, body=FOUND):
    response = await client.post("/api/items", json=body, headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- create


async def test_found_item_and_secret_saved_together(client, make_user):
    user = await make_user()
    body = await report(client, user)

    assert body["access"] == "full" and body["status"] == "open" and body["version"] == 1
    assert body["date"].startswith(YESTERDAY + "T00:00:00")
    assert body["statusHistory"][0]["status"] == "open"
    secret = await ItemSecret.find_one(ItemSecret.itemId == PydanticObjectId(body["id"]))
    assert secret is not None and len(secret.verification) == 1
    # Answers are hashed and never part of any response or audit entry.
    assert secret.verification[0].answerHash.startswith("$2b$12$")
    assert "Ahmed" not in str(body) and "SN-123" not in str(body)
    log = await AuditLog.find_one(AuditLog.action == "item.create")
    assert log is not None and "Ahmed" not in str(log.changes) and "SN-123" not in str(log.changes)


async def test_lost_item_has_no_secret(client, make_user):
    user = await make_user()
    await report(client, user, LOST)
    assert await ItemSecret.count() == 0


@pytest.mark.parametrize(
    "change",
    [
        {"verification": []},  # found item without questions
        {"category": "unknown"},  # category must exist
        {"location": {"building": "Mars"}},  # fixed building list
        {"date": (datetime.now(UTC) + timedelta(days=2)).date().isoformat()},  # future
        {"approxTime": "25:00"},
        {"title": ""},
        {"category": {"$ne": None}},  # operator injection
        {"title": {"$gt": ""}},  # operator injection on a string field
        {"attributes": {"color": {"$regex": ".*"}}},
        {"reporterId": "000000000000000000000000"},  # server-only fields are unknown fields
        {"status": "returned"},
        {"location": {"building": "Library", "$where": "1"}},  # nested unknown field
        {"verification": [{"question": "Name?", "answer": "x", "answerHash": "$2b$12$x"}]},
    ],
)
async def test_invalid_reports_rejected(client, make_user, change):
    user = await make_user()
    response = await client.post("/api/items", json=FOUND | change, headers=auth(user))
    assert response.status_code == 422, response.text
    assert await Item.count() == 0


async def test_server_sets_reporter_and_status(client, make_user):
    user = await make_user()
    item = await report(client, user)
    assert item["reporterId"] == str(user.id) and item["status"] == "open" and item["version"] == 1


async def test_lost_item_cannot_have_questions(client, make_user):
    user = await make_user()
    response = await client.post("/api/items", json=LOST | {"verification": FOUND["verification"]}, headers=auth(user))
    assert response.status_code == 422


async def test_reporting_needs_verified_account(client, make_user):
    assert (await client.post("/api/items", json=FOUND)).status_code == 401
    user = await make_user(status=UserStatus.unverified)
    assert (await client.post("/api/items", json=FOUND, headers=auth(user))).status_code == 403


# ----------------------------------------------------------------- views


async def test_fields_depend_on_viewer(client, make_user):
    reporter, other, officer = await make_user(), await make_user(), await make_user(Role.officer)
    item_id = (await report(client, reporter))["id"]

    guest = (await client.get(f"/api/items/{item_id}")).json()
    assert guest["access"] == "public"
    assert set(guest) == {"access", "id", "type", "title", "category", "location", "date", "status"}
    assert guest["location"] == {"building": "Library"}

    member = (await client.get(f"/api/items/{item_id}", headers=auth(other))).json()
    assert member["access"] == "member"
    assert member["attributes"] == {"color": "black", "brand": "Tommy Hilfiger"}
    assert "description" not in member and "photoIds" not in member and "floor" not in member["location"]

    for user in (reporter, officer):
        full = (await client.get(f"/api/items/{item_id}", headers=auth(user))).json()
        assert full["access"] == "full" and full["description"] and full["heldAt"] == "Security office"


async def test_lost_reports_are_private(client, make_user):
    reporter, other = await make_user(), await make_user()
    item_id = (await report(client, reporter, LOST))["id"]
    assert (await client.get(f"/api/items/{item_id}")).status_code == 404
    assert (await client.get(f"/api/items/{item_id}", headers=auth(other))).status_code == 404
    assert (await client.get(f"/api/items/{item_id}", headers=auth(reporter))).json()["access"] == "full"


# ---------------------------------------------------------------- search


async def test_public_search_shows_open_found_items_only(client, make_user):
    user = await make_user()
    found = await report(client, user)
    await report(client, user, LOST)
    archived = await report(client, user, FOUND | {"title": "Old wallet"})
    await client.post(f"/api/items/{archived['id']}/archive", headers=auth(user))

    page = (await client.get("/api/items")).json()
    assert page["total"] == 1 and [i["id"] for i in page["items"]] == [found["id"]]
    assert page["items"][0]["access"] == "public"
    assert (await client.get("/api/items?type=lost")).status_code == 403


async def test_search_filters(client, make_user):
    user = await make_user()
    await report(client, user)
    await report(client, user, FOUND | {"title": "iPhone 13", "category": "phones",
                                        "attributes": {"brand": "Apple"}, "description": "Blue case",
                                        "location": {"building": "Cafeteria"}})

    async def titles(query: str) -> list[str]:
        response = await client.get(f"/api/items?{query}", headers=auth(user))
        assert response.status_code == 200, response.text
        return [i["title"] for i in response.json()["items"]]

    assert await titles("category=phones") == ["iPhone 13"]
    assert await titles("building=Library") == ["Black wallet"]
    assert await titles("q=apple") == ["iPhone 13"]  # $text on brand
    assert await titles("q=wallet") == ["Black wallet"]
    assert await titles(f"dateFrom={YESTERDAY}&dateTo={YESTERDAY}") != []
    assert await titles("dateTo=2000-01-01") == []
    assert (await client.get("/api/items?building=Mars")).status_code == 422
    assert (await client.get("/api/items?category[$ne]=x")).status_code == 200  # unknown params are ignored


async def test_pagination(client, make_user):
    user = await make_user()
    for i in range(3):
        await report(client, user, FOUND | {"title": f"Wallet {i}"})
    page = (await client.get("/api/items?pageSize=2&page=2")).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert (await client.get("/api/items?pageSize=500")).status_code == 422


async def test_my_reports_include_private_ones(client, make_user):
    user, other = await make_user(), await make_user()
    await report(client, user, LOST)
    await report(client, other)
    assert (await client.get("/api/items?mine=true")).status_code == 403
    page = (await client.get("/api/items?mine=true", headers=auth(user))).json()
    assert page["total"] == 1 and page["items"][0]["type"] == "lost" and page["items"][0]["access"] == "full"


async def test_items_mine_endpoint(client, make_user):
    user, other = await make_user(), await make_user()
    mine = await report(client, user, LOST)
    await report(client, other)
    assert (await client.get("/api/items/mine")).status_code == 401
    page = (await client.get("/api/items/mine", headers=auth(user))).json()
    assert [i["id"] for i in page["items"]] == [mine["id"]] and page["items"][0]["access"] == "full"


async def test_staff_can_search_lost_items(client, make_user):
    user, officer = await make_user(), await make_user(Role.officer)
    await report(client, user, LOST)
    page = (await client.get("/api/items?type=lost", headers=auth(officer))).json()
    assert page["total"] == 1 and page["items"][0]["access"] == "full"


# ------------------------------------------------------------------ edit


async def test_reporter_edits_with_version_check(client, make_user):
    user = await make_user()
    item = await report(client, user)
    url, headers = f"/api/items/{item['id']}", auth(user)

    response = await client.patch(url, json={"version": 1, "title": "Brown wallet", "approxTime": None}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Brown wallet" and response.json()["approxTime"] is None
    assert response.json()["version"] == 2

    # A second editor still holding version 1 is told to reload.
    stale = await client.patch(url, json={"version": 1, "title": "Red wallet"}, headers=headers)
    assert stale.status_code == 409
    assert await AuditLog.find(AuditLog.action == "item.update").count() == 1


async def test_edit_rules(client, make_user):
    user, other, officer = await make_user(), await make_user(), await make_user(Role.officer)
    item = await report(client, user)
    url = f"/api/items/{item['id']}"
    assert (await client.patch(url, json={"version": 1, "title": "x"}, headers=auth(other))).status_code == 403
    future = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    assert (await client.patch(url, json={"version": 1, "date": future}, headers=auth(user))).status_code == 422
    assert (await client.patch(url, json={"version": 1, "category": "nope"}, headers=auth(user))).status_code == 422
    assert (await client.patch(url, json={"version": 1, "title": None}, headers=auth(user))).status_code == 422
    assert (await client.patch(url, json={"version": 1, "heldAt": "Desk 2"}, headers=auth(officer))).status_code == 200
    # Unknown fields and operators are rejected, not ignored.
    assert (await client.patch(url, json={"version": 2, "status": "returned"}, headers=auth(user))).status_code == 422
    assert (await client.patch(url, json={"version": 2, "title": {"$gt": ""}}, headers=auth(user))).status_code == 422
    assert (await Item.get(item["id"])).status == ItemStatus.open


async def test_officer_edits_need_current_version_too(client, make_user):
    user, officer = await make_user(), await make_user(Role.officer)
    item = await report(client, user)
    url = f"/api/items/{item['id']}"
    assert (await client.patch(url, json={"version": 1, "title": "A"}, headers=auth(user))).status_code == 200
    stale = await client.patch(url, json={"version": 1, "title": "B"}, headers=auth(officer))
    assert stale.status_code == 409
    assert (await Item.get(item["id"])).title == "A"


async def test_withdraw(client, make_user):
    user, other = await make_user(), await make_user()
    item = await report(client, user)
    url = f"/api/items/{item['id']}/archive"
    assert (await client.post(url, headers=auth(other))).status_code == 403
    response = await client.post(url, json={"note": "Found it myself"}, headers=auth(user))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "archived" and body["statusHistory"][-1]["note"] == "Found it myself"
    assert (await client.post(url, headers=auth(user))).status_code == 409
    # Archived items cannot be edited any more.
    patch = await client.patch(f"/api/items/{item['id']}", json={"version": body["version"], "title": "x"},
                               headers=auth(user))
    assert patch.status_code == 409
    assert (await Item.get(item["id"])).status == ItemStatus.archived


async def test_delete_archives_instead_of_removing(client, make_user):
    user, other = await make_user(), await make_user()
    item = await report(client, user)
    url = f"/api/items/{item['id']}"
    assert (await client.delete(url, headers=auth(other))).status_code == 403
    response = await client.delete(url, headers=auth(user))
    assert response.status_code == 200 and response.json()["status"] == "archived"
    assert await Item.count() == 1  # the record is kept for the audit trail
    assert (await client.delete(url, headers=auth(user))).status_code == 409


# ---------------------------------------------------------------- photos


async def test_photo_upload_and_download(client, make_user):
    user, other, officer = await make_user(), await make_user(), await make_user(Role.officer)
    item = await report(client, user)
    files = [("files", ("a.png", PNG, "image/png")), ("files", ("b.jpg", JPEG, "image/jpeg"))]
    response = await client.post(f"/api/items/{item['id']}/photos", files=files, headers=auth(user))
    assert response.status_code == 200, response.text
    photo_ids = response.json()["photoIds"]
    assert len(photo_ids) == 2

    url = f"/api/photos/{photo_ids[0]}"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=auth(other))).status_code == 404
    for viewer in (user, officer):
        download = await client.get(url, headers=auth(viewer))
        assert download.status_code == 200 and download.content == PNG
        assert download.headers["content-type"] == "image/png"

    removed = await client.delete(f"/api/items/{item['id']}/photos/{photo_ids[0]}", headers=auth(user))
    assert removed.status_code == 200 and removed.json()["photoIds"] == photo_ids[1:]
    assert (await client.get(url, headers=auth(user))).status_code == 404


async def test_photo_rules(client, make_user):
    user, other = await make_user(), await make_user()
    item = await report(client, user)
    url = f"/api/items/{item['id']}/photos"

    # Checked by content: a renamed text file is rejected.
    fake = [("files", ("x.png", b"not an image", "image/png"))]
    assert (await client.post(url, files=fake, headers=auth(user))).status_code == 422
    big = [("files", ("big.png", PNG + b"\x00" * (5 * 1024 * 1024), "image/png"))]
    assert (await client.post(url, files=big, headers=auth(user))).status_code == 422
    one = [("files", ("a.png", PNG, "image/png"))]
    assert (await client.post(url, files=one, headers=auth(other))).status_code == 403
    five = one * 5
    assert (await client.post(url, files=five, headers=auth(user))).status_code == 422
    for _ in range(4):
        assert (await client.post(url, files=one, headers=auth(user))).status_code == 200
    assert (await client.post(url, files=one, headers=auth(user))).status_code == 422

    # Nothing left behind in GridFS by the rejected uploads.
    from app.db import PHOTO_BUCKET, get_db

    assert await get_db()[f"{PHOTO_BUCKET}.files"].count_documents({}) == 4
