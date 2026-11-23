"""M5: submitting claims, verification lock, officer queue, withdraw."""

import pytest

from app.models import AuditLog, Category, Claim, Match, User
from app.models.common import ClaimStatus, Role, UserStatus

from .conftest import auth
from .test_matching import FOUND, LOST

TWO_QUESTIONS = FOUND | {"verification": [
    {"question": "What name is on the ID card?", "answer": "Ahmed  Ali!"},
    {"question": "What colour is the card inside?", "answer": "Blue"},
]}
RIGHT = ["ahmed ali", "BLUE"]  # normalised before comparing (§5.2)
WRONG = ["Mohammed", "red"]


@pytest.fixture(autouse=True)
async def categories():
    await Category(code="wallets", name="Wallets").insert()


async def report(client, user, body):
    response = await client.post("/api/items", json=body, headers=auth(user))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def found(client, make_user):
    finder = await make_user(Role.officer)
    return await report(client, finder, TWO_QUESTIONS)


async def claim(client, user, item, answers, **extra):
    return await client.post("/api/claims", json={"itemId": item["id"], "answers": answers} | extra, headers=auth(user))


async def test_questions_without_answers(client, make_user, found):
    user = await make_user()
    response = await client.get(f"/api/items/{found['id']}/questions", headers=auth(user))
    assert response.status_code == 200
    assert response.json()["questions"] == ["What name is on the ID card?", "What colour is the card inside?"]
    assert "Ahmed" not in response.text and "answerHash" not in response.text
    assert (await client.get(f"/api/items/{found['id']}/questions")).status_code == 401


async def test_correct_answers_go_to_officer_queue(client, make_user, found):
    user, officer = await make_user(), await make_user(Role.officer)
    response = await claim(client, user, found, RIGHT, proofNote="Has my library card")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending" and body["failedAttempts"] == 0
    assert [a["answer"] for a in body["answers"]] == RIGHT  # what they typed, for the officer
    assert body["claimant"] is None  # contact details are for officers only
    assert await AuditLog.find(AuditLog.action == "claim.submit").count() == 1

    queue = (await client.get("/api/claims/review", headers=auth(officer))).json()
    assert queue["total"] == 1 and queue["items"][0]["claimant"]["email"] == user.email
    assert (await client.get("/api/claims/review", headers=auth(user))).status_code == 403

    # One claim per user per item.
    assert (await claim(client, user, found, RIGHT)).status_code == 409


async def test_third_wrong_answer_locks_the_claim(client, make_user, found):
    user, officer = await make_user(), await make_user(Role.officer)
    first = await claim(client, user, found, WRONG)
    assert first.status_code == 400 and "2 attempt(s) left" in first.json()["detail"]
    assert (await claim(client, user, found, WRONG)).status_code == 400
    third = await claim(client, user, found, WRONG)
    assert third.status_code == 403 and "locked" in third.json()["detail"]

    stored = await Claim.find_one()
    assert stored.status == ClaimStatus.locked and stored.failedAttempts == 3 and stored.answers == []
    # Even the right answers are refused now.
    assert (await claim(client, user, found, RIGHT)).status_code == 403
    # Wrong tries never reach the officer queue; locked ones have their own list.
    assert (await client.get("/api/claims/review", headers=auth(officer))).json()["total"] == 0
    locked = (await client.get("/api/claims/review?status=locked", headers=auth(officer))).json()
    assert locked["total"] == 1


async def test_right_answers_after_a_wrong_try(client, make_user, found):
    user = await make_user()
    assert (await claim(client, user, found, WRONG)).status_code == 400
    response = await claim(client, user, found, RIGHT)
    assert response.status_code == 201 and response.json()["failedAttempts"] == 1
    assert await Claim.count() == 1


@pytest.mark.parametrize(
    "body",
    [
        {"answers": ["only one"]},  # one answer per question
        {"answers": RIGHT, "status": "approved"},  # unknown field
        {"answers": [{"$ne": None}, "x"]},  # operator injection
        {"answers": RIGHT, "itemId": {"$gt": ""}},
    ],
)
async def test_invalid_claims_rejected(client, make_user, found, body):
    user = await make_user()
    response = await client.post("/api/claims", json={"itemId": found["id"]} | body, headers=auth(user))
    assert response.status_code == 422, response.text
    assert await Claim.count() == 0


async def test_who_can_claim(client, make_user, found):
    unverified = await make_user(status=UserStatus.unverified)
    assert (await claim(client, unverified, found, RIGHT)).status_code == 403
    finder = await User.get(found["reporterId"])
    assert (await claim(client, finder, found, RIGHT)).status_code == 403  # own item
    assert (await client.post("/api/claims", json={"itemId": found["id"], "answers": RIGHT})).status_code == 401


async def test_lost_reports_cannot_be_claimed(client, make_user):
    owner, other = await make_user(), await make_user()
    lost = await report(client, owner, LOST)
    assert (await claim(client, other, lost, ["x"])).status_code == 404
    assert (await client.get(f"/api/items/{lost['id']}/questions", headers=auth(other))).status_code == 404


async def test_at_most_three_pending_claims(client, make_user):
    user, finder = await make_user(), await make_user(Role.officer)
    items = [await report(client, finder, TWO_QUESTIONS) for _ in range(4)]
    for item in items[:3]:
        assert (await claim(client, user, item, RIGHT)).status_code == 201
    assert (await claim(client, user, items[3], RIGHT)).status_code == 429


async def test_claim_links_the_claimants_match(client, make_user):
    owner, finder = await make_user(), await make_user(Role.officer)
    found = await report(client, finder, TWO_QUESTIONS)
    await report(client, owner, LOST)
    match = await Match.find_one()
    body = (await claim(client, owner, found, RIGHT)).json()
    assert body["matchId"] == str(match.id)


async def test_mine_and_withdraw(client, make_user, found):
    user, other = await make_user(), await make_user()
    created = (await claim(client, user, found, RIGHT)).json()
    mine = (await client.get("/api/claims/mine", headers=auth(user))).json()
    assert [c["id"] for c in mine["items"]] == [created["id"]]
    assert (await client.get("/api/claims/mine", headers=auth(other))).json()["total"] == 0
    assert (await client.get(f"/api/claims/{created['id']}", headers=auth(other))).status_code == 404

    url = f"/api/claims/{created['id']}/withdraw"
    assert (await client.post(url, headers=auth(other))).status_code == 404
    response = await client.post(url, headers=auth(user))
    assert response.status_code == 200 and response.json()["status"] == "withdrawn"
    assert (await client.post(url, headers=auth(user))).status_code == 409
