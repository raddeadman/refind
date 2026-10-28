"""Matches, claims, notifications and audit entries for the seed (PR1).

Builds a consistent story on top of the seeded items: every document obeys
the same rules the services will enforce (§3.1 lifecycles, §4.3 one
confirmed match per item, §5.4 one approved claim per found item), so the
data can be used to demonstrate the indexes and the CRUD queries.

Item documents are changed in place (status, statusHistory, version) and
must be inserted after make_activity() returns.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from beanie import PydanticObjectId

from app.models import (
    AuditLog,
    Claim,
    ClaimAnswer,
    Handover,
    Item,
    Match,
    Notification,
    StatusChange,
    User,
)
from app.models.common import (
    ClaimStatus,
    ItemStatus,
    ItemType,
    MatchStatus,
    NotificationType,
)

N_CONFIRMED = 6  # approved claims linked to a match; the first 3 are handed over
N_SUGGESTED = 10  # open suggestions; the first 5 have a pending claim
N_DISMISSED = 4
SEED_IP = "10.0.0.1"
MATCH_WINDOW = timedelta(days=7)


@dataclass
class Activity:
    matches: list[Match] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)
    audit: list[AuditLog] = field(default_factory=list)


def _set_status(item: Item, status: ItemStatus, at: datetime, by) -> None:
    item.status = status
    item.version += 1
    item.statusHistory.append(StatusChange(status=status, at=at, by=by))


def _later(start: datetime, now: datetime, max_hours: int = 72) -> datetime:
    return min(start + timedelta(minutes=random.randint(10, max_hours * 60)), now)


def _answers(category_questions: list[str], item: Item, correct: bool) -> list[ClaimAnswer]:
    guesses = [item.attributes.color or "black", "blue sticker"] if correct else ["no idea", "maybe red"]
    return [ClaimAnswer(question=q, answer=a) for q, a in zip(category_questions, guesses)]


def _pairs(items: list[Item], needed: int) -> list[tuple[Item, Item]]:
    """Distinct (lost, found) pairs the engine could suggest: same category,
    dates within MATCH_WINDOW (§4.3 step 1), each item used once."""
    pairs: list[tuple[Item, Item]] = []
    used: set = set()
    lost_items = [i for i in items if i.type == ItemType.lost]
    found_items = [i for i in items if i.type == ItemType.found]
    for lost in lost_items:
        for found in found_items:
            if (found.id not in used and found.category == lost.category
                    and abs(found.date - lost.date) <= MATCH_WINDOW):
                pairs.append((lost, found))
                used.add(found.id)
                break
    random.shuffle(pairs)
    if len(pairs) < needed:
        raise SystemExit(f"Need {needed} lost/found pairs, only {len(pairs)} available")
    return pairs[:needed]


def _score(lost: Item, found: Item) -> tuple[int, list[str]]:
    score, reasons = 30, ["same category"]
    if lost.location.building == found.location.building:
        score += 15
        reasons.append(f"same building ({found.location.building})")
    if lost.attributes.color == found.attributes.color:
        score += 15
        reasons.append(f"same colour ({found.attributes.color})")
    if lost.attributes.brand and lost.attributes.brand == found.attributes.brand:
        score += 10
        reasons.append(f"same brand ({found.attributes.brand})")
    days = abs((lost.date - found.date).days)
    score += max(0, 20 - 3 * days)
    reasons.append(f"dates {days} day(s) apart")
    return score, reasons


def make_activity(
    items: list[Item],
    users: list[User],
    category_questions: dict[str, list[str]],
    now: datetime,
) -> Activity:
    out = Activity()
    by_id = {u.id: u for u in users}
    officers = [u for u in users if u.role == "officer"]
    students = [u for u in users if u.role == "user" and u.status == "active"]

    def notify(user_id, kind: NotificationType, message: str, ref_id, key: str, at: datetime) -> None:
        read = random.random() < 0.4
        out.notifications.append(Notification(
            userId=user_id, type=kind, message=message, refId=ref_id,
            dedupeKey=f"{kind.value}:{key}:{user_id}", createdAt=at,
            readAt=_later(at, now, 24) if read else None,
        ))

    def audit(actor, action: str, collection: str, target, changes: dict, at: datetime) -> None:
        out.audit.append(AuditLog(
            actorId=actor, action=action, targetCollection=collection, targetId=target,
            changes=changes, ip=SEED_IP if actor else None, timestamp=at,
        ))

    def claim(found: Item, claimant: User, status: ClaimStatus, match: Match | None, at: datetime,
              correct: bool = True, failed: int = 0) -> Claim:
        c = Claim(
            itemId=found.id, claimantId=claimant, matchId=match.id if match else None,
            answers=_answers(category_questions[found.category], found, correct),
            proofNote="I can describe a scratch on the back." if correct else None,
            status=status, failedAttempts=failed, submittedAt=at,
        )
        c.id = PydanticObjectId()  # known before insert, so audit entries can point at it
        out.claims.append(c)
        audit(claimant.id, "claim.submit", "claims", c.id, {"itemId": str(found.id)}, at)
        return c

    pairs = _pairs(items, N_CONFIRMED + N_SUGGESTED + N_DISMISSED)
    for n, (lost, found) in enumerate(pairs):
        # Random items rarely look alike; make each pair resemble a real match
        # so the scores spread above the engine's threshold of 60.
        color = lost.attributes.color
        found.attributes.color, found.title = color, lost.title
        found.description = f"Found {color} {found.attributes.brand or ''} item".replace("  ", " ")
        if random.random() < 0.6:
            found.location.building = lost.location.building
        score, reasons = _score(lost, found)
        if score < 60:  # the engine only keeps scores >= 60 (§4.3 step 4)
            found.location.building = lost.location.building
            score, reasons = _score(lost, found)
        created = _later(max(lost.timeSubmitted, found.timeSubmitted), now, 1)
        if n < N_CONFIRMED:
            status = MatchStatus.confirmed
        elif n < N_CONFIRMED + N_SUGGESTED:
            status = MatchStatus.suggested
        else:
            status = MatchStatus.dismissed
        match = Match(id=PydanticObjectId(), lostItemId=lost.id, foundItemId=found.id,
                      score=min(score, 100), reasons=reasons, status=status, createdAt=created)
        out.matches.append(match)
        audit(None, "match.create", "matches", match.id, {"score": match.score}, created)
        for item in (lost, found):
            _set_status(item, ItemStatus.matched, created, None)
        notify(lost.reporterId, NotificationType.new_match,
               f"Possible match for your {lost.title.lower()} ({match.score}%)", match.id, str(match.id), created)

        owner = by_id[lost.reporterId]
        if status == MatchStatus.dismissed:
            at = _later(created, now, 48)
            match_dismiss = {"status": [MatchStatus.suggested.value, MatchStatus.dismissed.value]}
            audit(owner.id, "match.dismiss", "matches", match.id, match_dismiss, at)
            for item in (lost, found):
                _set_status(item, ItemStatus.open, at, owner.id)
            continue

        if status == MatchStatus.suggested:
            if n < N_CONFIRMED + N_SUGGESTED // 2:
                claim(found, owner, ClaimStatus.pending, match, _later(created, now, 24))
            continue

        # Confirmed: the owner's claim was approved inside the approval transaction (§5.4).
        submitted = _later(created, now, 24)
        winner = claim(found, owner, ClaimStatus.approved, match, submitted)
        officer = random.choice(officers)
        reviewed = _later(submitted, now, 24)
        winner.reviewedBy, winner.reviewedAt = officer.id, reviewed
        audit(officer.id, "claim.approve", "claims", winner.id,
              {"status": ["pending", "approved"], "matchId": str(match.id)}, reviewed)
        for item in (lost, found):
            _set_status(item, ItemStatus.claimed, reviewed, officer.id)
            audit(officer.id, "item.status", "items", item.id, {"status": ["matched", "claimed"]}, reviewed)
        notify(owner.id, NotificationType.claim_update, "Your claim was approved", winner.id,
               f"{winner.id}:approved", reviewed)

        # Two of the confirmed items also had a competing claim, rejected in the same transaction.
        if n < 2:
            rival = next(s for s in students if s.id not in (owner.id, found.reporterId))
            loser = claim(found, rival, ClaimStatus.rejected, None, _later(created, submitted, 12), correct=False)
            loser.reviewedBy, loser.reviewedAt = officer.id, reviewed
            audit(officer.id, "claim.reject", "claims", loser.id, {"status": ["pending", "rejected"]}, reviewed)
            notify(rival.id, NotificationType.claim_update, "Your claim was not approved", loser.id,
                   f"{loser.id}:rejected", reviewed)

        if n < 3:
            handed = _later(reviewed, now, 48)
            winner.handover = Handover(at=handed, officerId=officer.id, idChecked=True,
                                       idLast4=f"{random.randint(0, 9999):04d}")
            audit(officer.id, "claim.handover", "claims", winner.id, {"idChecked": True}, handed)
            for item in (lost, found):
                _set_status(item, ItemStatus.returned, handed, officer.id)
        else:
            notify(owner.id, NotificationType.handover_ready,
                   f"Collect your {found.title.lower()} from {found.heldAt}", winner.id, str(winner.id), reviewed)

    # Claims on found items nobody reported losing (matchId null, §5.4).
    used = {c.itemId for c in out.claims}
    unmatched = [i for i in items if i.type == ItemType.found and i.status == ItemStatus.open and i.id not in used]
    for found, status in zip(unmatched, [ClaimStatus.pending, ClaimStatus.locked, ClaimStatus.withdrawn]):
        claimant = random.choice([s for s in students if s.id != found.reporterId])
        at = _later(found.timeSubmitted, now, 72)
        locked = status == ClaimStatus.locked
        c = claim(found, claimant, status, None, at, correct=not locked, failed=3 if locked else 0)
        if locked:
            audit(None, "claim.lock", "claims", c.id, {"failedAttempts": 3}, _later(at, now, 1))
        elif status == ClaimStatus.withdrawn:
            audit(claimant.id, "claim.withdraw", "claims", c.id, {"status": ["pending", "withdrawn"]},
                  _later(at, now, 24))

    # Account events, so auditLogs covers users as well as items and claims.
    for user in random.sample(students, 5):
        audit(user.id, "user.verify_email", "users", user.id, {"status": ["unverified", "active"]}, user.createdAt)
    return out
