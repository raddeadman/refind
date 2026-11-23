"""M5: approve, reject, unlock and handover transactions (§5.4)."""

import pytest

from app.models import AuditLog, Category, Claim, Item, Match, Notification
from app.models.common import ClaimStatus, ItemStatus, MatchStatus, NotificationType, Role

from .conftest import auth
from .test_claims_api import RIGHT, TWO_QUESTIONS, WRONG, claim, report
from .test_matching import LOST


@pytest.fixture(autouse=True)
async def categories():
    await Category(code="wallets", name="Wallets").insert()


@pytest.fixture
async def setup(client, make_user):
    """A found item with two correct claims: A from the owner of a matched lost report, B without a match."""
    officer = await make_user(Role.officer)
    owner, stranger = await make_user(), await make_user()
    found = await report(client, officer, TWO_QUESTIONS | {"heldAt": "Security office"})
    lost = await report(client, owner, LOST)
    a = (await claim(client, owner, found, RIGHT)).json()
    b = (await claim(client, stranger, found, RIGHT)).json()
    assert a["matchId"] and b["matchId"] is None
    return dict(officer=officer, owner=owner, stranger=stranger, found=found, lost=lost, a=a, b=b)


async def approve(client, officer, claim_id):
    return await client.post(f"/api/claims/{claim_id}/approve", headers=auth(officer))


async def test_approve_with_match(client, setup):
    s = setup
    response = await approve(client, s["officer"], s["a"]["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved" and response.json()["reviewedBy"] == str(s["officer"].id)

    assert (await Item.get(s["found"]["id"])).status == ItemStatus.claimed
    assert (await Item.get(s["lost"]["id"])).status == ItemStatus.claimed
    assert (await Match.get(s["a"]["matchId"])).status == MatchStatus.confirmed
    assert (await Claim.get(s["b"]["id"])).status == ClaimStatus.rejected

    approved = await Notification.find_one(Notification.type == NotificationType.handover_ready)
    assert approved.userId == s["owner"].id and "Security office" in approved.message
    rejected = await Notification.find_one(Notification.dedupeKey == f"claim_rejected:{s['b']['id']}:{s['stranger'].id}")
    assert rejected is not None
    actions = {log.action async for log in AuditLog.find(AuditLog.action != "item.create")}
    assert {"claim.approve", "claim.reject", "match.confirm", "item.status"} <= actions


async def test_approve_without_match_dismisses_suggestions(client, setup):
    s = setup
    response = await approve(client, s["officer"], s["b"]["id"])
    assert response.status_code == 200, response.text
    assert (await Item.get(s["found"]["id"])).status == ItemStatus.claimed
    # A's match was dismissed and its lost item, with nothing left, is open again.
    assert (await Match.get(s["a"]["matchId"])).status == MatchStatus.dismissed
    assert (await Item.get(s["lost"]["id"])).status == ItemStatus.open
    assert (await Claim.get(s["a"]["id"])).status == ClaimStatus.rejected
    assert await Match.find(Match.status == MatchStatus.confirmed).count() == 0


async def test_second_approval_is_409_and_changes_nothing(client, setup):
    s = setup
    assert (await approve(client, s["officer"], s["a"]["id"])).status_code == 200
    audit_before = await AuditLog.count()
    second = await approve(client, s["officer"], s["b"]["id"])
    assert second.status_code == 409 and second.json()["detail"] == "Claim is no longer pending"
    # A rejected claim stays rejected; nothing half-written.
    assert (await Claim.get(s["b"]["id"])).status == ClaimStatus.rejected
    assert await AuditLog.count() == audit_before
    assert await Claim.find(Claim.status == ClaimStatus.approved).count() == 1


async def test_item_already_claimed_rolls_back_step_1(client, setup):
    s = setup
    # The item is released by another route (e.g. an earlier approval), but B is still pending.
    await (await Item.get(s["found"]["id"])).set({"status": ItemStatus.claimed})
    response = await approve(client, s["officer"], s["b"]["id"])
    assert response.status_code == 409 and response.json()["detail"] == "Item already claimed"
    assert (await Claim.get(s["b"]["id"])).status == ClaimStatus.pending  # step 1 was rolled back
    assert await AuditLog.find(AuditLog.action == "claim.approve").count() == 0


async def test_confirmed_match_conflict_rolls_back(client, setup, make_user):
    s = setup
    # The lost item already has a confirmed match with another found item.
    other_found = await Item(**(await Item.get(s["found"]["id"])).model_dump(exclude={"id"})).insert()
    await Match(lostItemId=s["lost"]["id"], foundItemId=other_found.id, score=70, status="confirmed").insert()
    response = await approve(client, s["officer"], s["a"]["id"])
    assert response.status_code == 409 and response.json()["detail"] == "Item already claimed"
    assert (await Claim.get(s["a"]["id"])).status == ClaimStatus.pending
    assert (await Item.get(s["found"]["id"])).status == ItemStatus.matched


async def test_users_cannot_review(client, setup):
    s = setup
    for path in ("approve", "reject", "unlock"):
        response = await client.post(f"/api/claims/{s['a']['id']}/{path}", headers=auth(s["owner"]))
        assert response.status_code == 403
    response = await client.post(f"/api/claims/{s['a']['id']}/handover", json={"idChecked": True, "idLast4": "1234"},
                                 headers=auth(s["owner"]))
    assert response.status_code == 403


async def test_reject_and_unlock(client, setup, make_user):
    s = setup
    response = await client.post(f"/api/claims/{s['b']['id']}/reject", json={"note": "Wrong card colour"},
                                 headers=auth(s["officer"]))
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    note = await Notification.find_one(Notification.userId == s["stranger"].id)
    assert "Wrong card colour" in note.message
    assert (await client.post(f"/api/claims/{s['b']['id']}/reject", headers=auth(s["officer"]))).status_code == 409

    guesser = await make_user()
    for _ in range(3):
        await claim(client, guesser, s["found"], WRONG)
    locked = await Claim.find_one({"claimantId.$id": guesser.id})
    assert locked.status == ClaimStatus.locked
    response = await client.post(f"/api/claims/{locked.id}/unlock", headers=auth(s["officer"]))
    assert response.status_code == 200 and response.json()["status"] == "pending"
    assert response.json()["failedAttempts"] == 0
    # Three fresh tries; the right answers now go to the queue.
    assert (await claim(client, guesser, s["found"], RIGHT)).status_code == 201


async def test_handover(client, setup):
    s = setup
    url = f"/api/claims/{s['a']['id']}/handover"
    body = {"idChecked": True, "idLast4": "4821"}
    # Not approved yet.
    assert (await client.post(url, json=body, headers=auth(s["officer"]))).status_code == 409
    assert (await approve(client, s["officer"], s["a"]["id"])).status_code == 200

    assert (await client.post(url, json=body | {"idChecked": False}, headers=auth(s["officer"]))).status_code == 422
    assert (await client.post(url, json=body | {"idLast4": "12"}, headers=auth(s["officer"]))).status_code == 422
    response = await client.post(url, json=body, headers=auth(s["officer"]))
    assert response.status_code == 200, response.text
    handover = response.json()["handover"]
    assert handover["idChecked"] is True and handover["idLast4"] == "4821"
    assert handover["officerId"] == str(s["officer"].id)

    assert (await Item.get(s["found"]["id"])).status == ItemStatus.returned
    assert (await Item.get(s["lost"]["id"])).status == ItemStatus.returned
    log = await AuditLog.find_one(AuditLog.action == "claim.handover")
    assert "4821" not in str(log.changes)
    # Only once.
    assert (await client.post(url, json=body, headers=auth(s["officer"]))).status_code == 409


async def test_officer_sees_claimant_contact(client, setup):
    s = setup
    body = (await client.get(f"/api/claims/{s['a']['id']}", headers=auth(s["officer"]))).json()
    assert body["claimant"]["email"] == s["owner"].email
    assert body["item"]["access"] == "full"
    own = (await client.get(f"/api/claims/{s['a']['id']}", headers=auth(s["owner"]))).json()
    assert own["claimant"] is None and own["item"]["access"] == "member"
