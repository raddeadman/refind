"""H4: two officers approve rival claims for one item at the same moment (§5.4).

Procedure from the proposal, run 50 times on fresh data:
  * a found item (matched) with two pending claims: A is linked to a
    suggested match with a lost item, B has no match;
  * POST /api/claims/A/approve and /B/approve fire together (asyncio.gather)
    as two different officers, alternating which one starts first;
  * exactly one 200 and one 409, never a 500; the item is claimed once,
    one claim approved and the other rejected, A's match confirmed only if
    A won, one approval and one rejection notification.

The log is written to docs/evidence/concurrency_test.log for the report.
"""

import asyncio
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import ALL_MODELS, AuditLog, Category, Claim, ClaimAnswer, Item, Match, Notification
from app.models.common import ClaimStatus, ItemStatus, MatchStatus, NotificationType, Role

from .conftest import auth

RUNS = 50
LOSING_DETAILS = {"Claim is no longer pending", "Item already claimed"}
LOG = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "concurrency_test.log"


async def fresh_data(make_user):
    for model in ALL_MODELS:
        await model.get_pymongo_collection().delete_many({})
    await Category(code="wallets", name="Wallets").insert()
    officer1, officer2 = await make_user(Role.officer), await make_user(Role.officer)
    owner, stranger = await make_user(), await make_user()
    day = datetime.now(UTC) - timedelta(days=1)
    found = await Item(type="found", title="Black wallet", category="wallets", location={"building": "Library"},
                       date=day, reporterId=officer1.id, status=ItemStatus.matched).insert()
    lost = await Item(type="lost", title="My wallet", category="wallets", location={"building": "Library"},
                      date=day, reporterId=owner.id, status=ItemStatus.matched).insert()
    match = await Match(lostItemId=lost.id, foundItemId=found.id, score=80).insert()
    answers = [ClaimAnswer(question="Name on the ID card?", answer="Ahmed")]
    a = await Claim(itemId=found.id, claimantId=owner, matchId=match.id, answers=answers).insert()
    b = await Claim(itemId=found.id, claimantId=stranger, answers=answers).insert()
    return officer1, officer2, found, lost, match, a, b


async def test_two_approvals_at_once(client, make_user):
    lines, winners, losing = [], Counter(), Counter()
    started = time.perf_counter()

    for run in range(1, RUNS + 1):
        officer1, officer2, found, lost, match, a, b = await fresh_data(make_user)

        approve_a = client.post(f"/api/claims/{a.id}/approve", headers=auth(officer1))
        approve_b = client.post(f"/api/claims/{b.id}/approve", headers=auth(officer2))
        # Alternate which request starts first so both outcomes are exercised.
        if run % 2:
            ra, rb = await asyncio.gather(approve_a, approve_b)
        else:
            rb, ra = await asyncio.gather(approve_b, approve_a)

        # Responses: one 200, one 409 with a known reason, no 500.
        codes = sorted([ra.status_code, rb.status_code])
        assert codes == [200, 409], f"run {run}: {ra.status_code} {ra.text} / {rb.status_code} {rb.text}"
        winner, loser = ("A", rb) if ra.status_code == 200 else ("B", ra)
        assert loser.json()["detail"] in LOSING_DETAILS, loser.text

        # Database state.
        assert (await Item.get(found.id)).status == ItemStatus.claimed
        statuses = {c.id: c.status for c in await Claim.find_all().to_list()}
        assert sorted(statuses.values()) == [ClaimStatus.approved, ClaimStatus.rejected]
        if winner == "A":
            assert statuses[a.id] == ClaimStatus.approved
            assert (await Match.get(match.id)).status == MatchStatus.confirmed
            assert (await Item.get(lost.id)).status == ItemStatus.claimed
        else:
            assert statuses[b.id] == ClaimStatus.approved
            assert (await Match.get(match.id)).status == MatchStatus.dismissed
            assert (await Item.get(lost.id)).status == ItemStatus.open
        assert await Match.find(Match.status == MatchStatus.confirmed).count() == (1 if winner == "A" else 0)
        assert await Notification.find(Notification.type == NotificationType.handover_ready).count() == 1
        assert await Notification.find(Notification.type == NotificationType.claim_update).count() == 1
        # Nothing remains from the losing request.
        assert await AuditLog.find(AuditLog.action == "claim.approve").count() == 1
        assert await AuditLog.find(AuditLog.action == "claim.reject").count() == 1

        winners[winner] += 1
        losing[loser.json()["detail"]] += 1
        lines.append(f"run {run:2d}: A={ra.status_code} B={rb.status_code} winner={winner} "
                     f"loser said \"{loser.json()['detail']}\" item=claimed "
                     f"match={(await Match.get(match.id)).status.value} lost={(await Item.get(lost.id)).status.value}")

    elapsed = time.perf_counter() - started
    summary = [
        "",
        f"{RUNS}/{RUNS} runs passed in {elapsed:.1f} s",
        f"winners: A (with match) {winners['A']}, B (no match) {winners['B']}",
        *[f"409 \"{detail}\": {count}" for detail, count in sorted(losing.items())],
        "no 500 responses; exactly one approved claim and one claimed item in every run",
    ]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    header = f"ReFind concurrency test (§5.4), {datetime.now(UTC):%Y-%m-%d %H:%M} UTC"
    LOG.write_text("\n".join([header, "", *lines, *summary]) + "\n")
