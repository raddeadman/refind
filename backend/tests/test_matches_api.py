"""M4: matches and notifications endpoints."""

from app.models import AuditLog, Item, Match
from app.models.common import ItemStatus, MatchStatus, Role

from .conftest import auth
from .test_matching import FOUND, LOST, categories, report  # noqa: F401  (categories is an autouse fixture)

async def pair(client, make_user):
    owner, finder, officer = await make_user(), await make_user(), await make_user(Role.officer)
    found = await report(client, finder, FOUND)
    lost = await report(client, owner, LOST)
    match = await Match.find_one()
    return owner, finder, officer, found, lost, match


async def test_my_matches_show_the_viewers_fields(client, make_user):
    owner, finder, officer, found, lost, match = await pair(client, make_user)
    stranger = await make_user()

    page = (await client.get("/api/matches/mine", headers=auth(owner))).json()
    assert page["total"] == 1
    out = page["items"][0]
    assert out["lostItem"]["access"] == "full" and out["foundItem"]["access"] == "member"
    assert "description" not in out["foundItem"] and "photoIds" not in out["foundItem"]

    assert (await client.get("/api/matches/mine", headers=auth(stranger))).json()["total"] == 0
    assert (await client.get(f"/api/matches/{match.id}", headers=auth(stranger))).status_code == 404
    assert (await client.get("/api/matches", headers=auth(owner))).status_code == 403
    staff = (await client.get("/api/matches", headers=auth(officer))).json()
    assert staff["total"] == 1 and staff["items"][0]["foundItem"]["access"] == "full"


async def test_owner_dismisses_and_items_reopen(client, make_user):
    owner, finder, officer, found, lost, match = await pair(client, make_user)
    url = f"/api/matches/{match.id}"
    response = await client.patch(url, json={"status": "dismissed"}, headers=auth(owner))
    assert response.status_code == 200 and response.json()["status"] == "dismissed"
    # Their last suggestion is gone, so both items can be matched again.
    assert (await Item.get(lost["id"])).status == ItemStatus.open
    assert (await Item.get(found["id"])).status == ItemStatus.open
    assert (await client.patch(url, json={"status": "dismissed"}, headers=auth(owner))).status_code == 409
    assert await AuditLog.find(AuditLog.action == "match.dismiss").count() == 1


async def test_user_cannot_confirm_officer_can(client, make_user):
    owner, finder, officer, found, lost, match = await pair(client, make_user)
    url = f"/api/matches/{match.id}"
    assert (await client.patch(url, json={"status": "confirmed"}, headers=auth(owner))).status_code == 403
    assert (await client.patch(url, json={"status": "suggested"}, headers=auth(officer))).status_code == 422
    assert (await client.patch(url, json={"status": "confirmed", "score": 1}, headers=auth(officer))).status_code == 422
    response = await client.patch(url, json={"status": "confirmed"}, headers=auth(officer))
    assert response.status_code == 200 and response.json()["status"] == "confirmed"
    assert (await client.patch(url, json={"status": "dismissed"}, headers=auth(owner))).status_code == 409


async def test_confirm_is_one_to_one(client, make_user):
    owner, finder, officer, found, lost, match = await pair(client, make_user)
    other_owner = await make_user()
    await report(client, other_owner, LOST)
    second = await Match.find_one(Match.lostItemId != match.lostItemId)
    assert second.foundItemId == match.foundItemId

    response = await client.patch(f"/api/matches/{match.id}", json={"status": "confirmed"}, headers=auth(officer))
    assert response.status_code == 200
    # The other suggestion for the same found item was dismissed with it ...
    assert (await Match.get(second.id)).status == MatchStatus.dismissed
    # ... and its lost item, with nothing left, is open again.
    assert (await Item.get(second.lostItemId)).status == ItemStatus.open


async def test_partial_unique_index_blocks_second_confirmed(client, make_user):
    owner, finder, officer, found, lost, match = await pair(client, make_user)
    await match.set({"status": MatchStatus.confirmed})
    # Bypass the API: a second confirmed match for the same found item.
    other = await Item(**(await Item.get(lost["id"])).model_dump(exclude={"id"})).insert()
    rogue = await Match(lostItemId=other.id, foundItemId=match.foundItemId, score=70).insert()
    response = await client.patch(f"/api/matches/{rogue.id}", json={"status": "confirmed"}, headers=auth(officer))
    assert response.status_code == 409
    assert (await Match.get(rogue.id)).status == MatchStatus.suggested


async def test_notifications(client, make_user):
    owner, finder, officer, found, lost, match = await pair(client, make_user)
    assert (await client.get("/api/notifications")).status_code == 401
    page = (await client.get("/api/notifications", headers=auth(owner))).json()
    assert page["total"] == 1 and page["unread"] == 1
    note = page["items"][0]
    assert note["type"] == "new_match" and note["refId"] == str(match.id) and note["readAt"] is None

    assert (await client.get("/api/notifications", headers=auth(finder))).json()["total"] == 0
    # Someone else's notification is a 404.
    assert (await client.patch(f"/api/notifications/{note['id']}/read", headers=auth(finder))).status_code == 404
    read = await client.patch(f"/api/notifications/{note['id']}/read", headers=auth(owner))
    assert read.status_code == 200 and read.json()["readAt"] is not None
    page = (await client.get("/api/notifications?unreadOnly=true", headers=auth(owner))).json()
    assert page["total"] == 0 and page["unread"] == 0


async def test_mark_all_read(client, make_user):
    owner = await make_user()
    for _ in range(3):
        await report(client, await make_user(), FOUND)
    await report(client, owner, LOST)
    response = await client.post("/api/notifications/read-all", headers=auth(owner))
    assert response.json() == {"updated": 3}
    assert (await client.get("/api/notifications", headers=auth(owner))).json()["unread"] == 0
