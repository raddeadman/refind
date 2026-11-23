"""Claims: verification, officer review and handover (§3.1, §5.2, §5.4).

Owner: Habib.

Submitting a claim checks the answers against the hashed ones in
itemSecrets. A correct set only puts the claim in the officer queue; the
officer, who holds the item, makes the final decision. Each wrong set adds
one to failedAttempts and the third one locks the claim until an officer
unlocks it after checking in person.

A claim with status "pending" and no answers yet is a claim whose answers
were wrong so far: it is not in the officer queue.
"""

from typing import Any

from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from ..db import run_in_transaction
from ..errors import Conflict, Forbidden, InvalidInput, NotFound, ServiceError, TooManyRequests
from ..models import Claim, ClaimAnswer, Item, ItemSecret, Match, User
from ..models.common import ClaimStatus, ItemStatus, ItemType, MatchStatus, Role, utcnow
from ..schemas.claim import ClaimantOut, ClaimCreate, ClaimOut, ClaimPage, Questions
from ..security import verify_secret
from . import audit_service, item_service

STAFF = {Role.officer, Role.admin}
MAX_ATTEMPTS = 3
MAX_PENDING_PER_USER = 3  # §5.2
CLAIMABLE = (ItemStatus.open, ItemStatus.matched)


class WrongAnswers(ServiceError):
    status_code = 400


# ---------------------------------------------------------------- helpers


def claimant_id(claim: Claim) -> PydanticObjectId:
    link = claim.claimantId
    return link.ref.id if hasattr(link, "ref") else link.id  # Link (not fetched) or User


def _by_claimant(user_id: PydanticObjectId) -> dict:
    # claimantId is a DBRef (Beanie Link), so the id is at claimantId.$id.
    return {"claimantId.$id": user_id}


async def get_claim(claim_id: PydanticObjectId, session: AsyncClientSession | None = None) -> Claim:
    claim = await Claim.get(claim_id, session=session)
    if claim is None:
        raise NotFound("Claim not found")
    return claim


async def to_out(claim: Claim, viewer: User, item: Item | None = None) -> ClaimOut:
    item = item or await item_service.get_item(claim.itemId)
    claimant = None
    if viewer.role in STAFF:
        user = await User.get(claimant_id(claim))
        if user is not None:
            claimant = ClaimantOut(id=user.id, name=user.name, email=user.email, studentId=user.studentId,
                                   phone=user.profile.phone)
    return ClaimOut(
        **claim.model_dump(include={"id", "itemId", "matchId", "status", "answers", "proofNote", "failedAttempts",
                                    "submittedAt", "reviewedBy", "reviewedAt", "handover"}),
        item=item_service.to_view(item, viewer),
        claimant=claimant,
    )


async def _claimable_item(item_id: PydanticObjectId, user: User) -> Item:
    item = await item_service.get_item(item_id)
    # 404 for anything the user may not see, like GET /items/{id}.
    if not item_service.can_see(item, user) or item.type != ItemType.found:
        raise NotFound("Item not found")
    if item.reporterId == user.id:
        raise Forbidden("You cannot claim an item you reported")
    if item.status not in CLAIMABLE:
        raise Conflict("This item can no longer be claimed")
    return item


async def _secret(item_id: PydanticObjectId) -> ItemSecret:
    secret = await ItemSecret.find_one(ItemSecret.itemId == item_id)
    if secret is None:  # every found item has one (created with the item)
        raise Conflict("This item has no verification questions")
    return secret


# ------------------------------------------------------------- questions


async def questions_for(item_id: PydanticObjectId, user: User) -> Questions:
    """The questions only, shown when a user starts a claim (§5.1)."""
    item = await _claimable_item(item_id, user)
    secret = await _secret(item.id)
    return Questions(itemId=item.id, questions=[q.question for q in secret.verification])


# ---------------------------------------------------------------- submit


async def _linked_match(item: Item, user: User) -> PydanticObjectId | None:
    """The claimant's own lost report matched to this found item, if any."""
    my_lost = [d["_id"] async for d in Item.get_pymongo_collection().find(
        {"reporterId": user.id, "type": ItemType.lost.value}, {"_id": 1})]
    if not my_lost:
        return None
    match = await Match.find(
        {"foundItemId": item.id, "lostItemId": {"$in": my_lost},
         "status": {"$in": [MatchStatus.suggested.value, MatchStatus.confirmed.value]}},
    ).sort("-score").first_or_none()
    return match.id if match else None


async def submit(data: ClaimCreate, user: User) -> Claim:
    item = await _claimable_item(data.itemId, user)
    secret = await _secret(item.id)
    if len(data.answers) != len(secret.verification):
        raise InvalidInput(f"Expected {len(secret.verification)} answer(s)")

    existing = await Claim.find_one({"itemId": item.id, **_by_claimant(user.id)})
    if existing is not None:
        if existing.status == ClaimStatus.locked:
            raise Forbidden("This claim is locked after 3 wrong answers; please visit the Lost & Found desk")
        if existing.status != ClaimStatus.pending or existing.answers:
            raise Conflict("You have already claimed this item")
    else:
        pending = await Claim.find({**_by_claimant(user.id), "status": ClaimStatus.pending.value}).count()
        if pending >= MAX_PENDING_PER_USER:
            raise TooManyRequests(f"You can have at most {MAX_PENDING_PER_USER} pending claims")

    # bcrypt is slow: compare outside the transaction (which may be retried).
    correct = all(verify_secret(answer, q.answerHash) for answer, q in zip(data.answers, secret.verification))
    if not correct:
        attempts = await run_in_transaction(lambda s: _record_failure(item, user, s))
        left = MAX_ATTEMPTS - attempts
        if left <= 0:
            raise Forbidden("Wrong answers. The claim is now locked; please visit the Lost & Found desk")
        raise WrongAnswers(f"The answers do not match. {left} attempt(s) left")

    answers = [ClaimAnswer(question=q.question, answer=a.strip())
               for a, q in zip(data.answers, secret.verification)]
    match_id = await _linked_match(item, user)

    async def txn(session: AsyncClientSession) -> Claim:
        claim = await Claim.find_one({"itemId": item.id, **_by_claimant(user.id)}, session=session)
        values = {"answers": answers, "proofNote": data.proofNote, "matchId": match_id, "submittedAt": utcnow()}
        if claim is None:
            claim = Claim(itemId=item.id, claimantId=user, **values)
            await claim.insert(session=session)  # a duplicate (race) -> 409
        else:
            # Earlier wrong tries left a pending claim without answers.
            result = await Claim.get_pymongo_collection().update_one(
                {"_id": claim.id, "status": ClaimStatus.pending.value, "answers": []},
                {"$set": values | {"answers": [a.model_dump() for a in answers]}},
                session=session,
            )
            if result.modified_count == 0:
                raise Conflict("You have already claimed this item")
            claim = await get_claim(claim.id, session)
        await audit_service.log(user.id, "claim.submit", "claims", claim.id,
                                {"itemId": str(item.id), "matchId": str(match_id) if match_id else None},
                                session=session)
        return claim

    return await run_in_transaction(txn)


async def _record_failure(item: Item, user: User, session: AsyncClientSession) -> int:
    """$inc failedAttempts (creating the claim on the first try); the third locks it."""
    claim = await Claim.find_one({"itemId": item.id, **_by_claimant(user.id)}, session=session)
    if claim is None:
        claim = Claim(itemId=item.id, claimantId=user, failedAttempts=1)
        await claim.insert(session=session)
    else:
        await Claim.get_pymongo_collection().update_one(
            {"_id": claim.id, "status": ClaimStatus.pending.value}, {"$inc": {"failedAttempts": 1}}, session=session
        )
        claim = await get_claim(claim.id, session)
    await audit_service.log(user.id, "claim.wrong_answers", "claims", claim.id,
                            {"failedAttempts": claim.failedAttempts}, session=session)
    if claim.failedAttempts >= MAX_ATTEMPTS:
        await Claim.get_pymongo_collection().update_one(
            {"_id": claim.id, "status": ClaimStatus.pending.value},
            {"$set": {"status": ClaimStatus.locked.value}}, session=session,
        )
        await audit_service.log(None, "claim.lock", "claims", claim.id,
                                {"status": [ClaimStatus.pending.value, ClaimStatus.locked.value]}, session=session)
    return claim.failedAttempts


# ------------------------------------------------------------------ read


async def get_for(claim_id: PydanticObjectId, user: User) -> Claim:
    claim = await get_claim(claim_id)
    if user.role not in STAFF and claimant_id(claim) != user.id:
        raise NotFound("Claim not found")
    return claim


async def _page(query: dict[str, Any], sort: str, viewer: User, page: int, page_size: int) -> ClaimPage:
    total = await Claim.find(query).count()
    claims = await Claim.find(query).sort(sort).skip((page - 1) * page_size).limit(page_size).to_list()
    items = {i.id: i for i in await Item.find({"_id": {"$in": list({c.itemId for c in claims})}}).to_list()}
    return ClaimPage(items=[await to_out(c, viewer, items.get(c.itemId)) for c in claims], total=total, page=page,
                     pageSize=page_size)


async def list_mine(user: User, page: int = 1, page_size: int = 20) -> ClaimPage:
    return await _page(_by_claimant(user.id), "-submittedAt", user, page, page_size)


async def review_queue(officer: User, status: ClaimStatus = ClaimStatus.pending, page: int = 1,
                       page_size: int = 20) -> ClaimPage:
    """Oldest first, on the review_queue index. Pending claims appear only
    once their answers were correct."""
    query: dict[str, Any] = {"status": status.value}
    if status == ClaimStatus.pending:
        query["answers"] = {"$ne": []}
    return await _page(query, "+submittedAt", officer, page, page_size)


# -------------------------------------------------------------- withdraw


async def withdraw(claim_id: PydanticObjectId, user: User) -> Claim:
    async def txn(session: AsyncClientSession) -> Claim:
        claim = await get_claim(claim_id, session)
        if claimant_id(claim) != user.id:
            raise NotFound("Claim not found")
        result = await Claim.get_pymongo_collection().update_one(
            {"_id": claim.id, "status": ClaimStatus.pending.value},
            {"$set": {"status": ClaimStatus.withdrawn.value}}, session=session,
        )
        if result.modified_count == 0:
            raise Conflict(f"A {claim.status.value} claim cannot be withdrawn")
        await audit_service.log(user.id, "claim.withdraw", "claims", claim.id,
                                {"status": [ClaimStatus.pending.value, ClaimStatus.withdrawn.value]}, session=session)
        return await get_claim(claim.id, session)

    return await run_in_transaction(txn)
