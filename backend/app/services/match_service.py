"""Matches seen through the API: list, dismiss, confirm (§4.3, §5.1).

Owner: Abdullah. Who may do what:
    user      sees matches for their own items; may dismiss them
    officer   sees all matches; may dismiss and confirm
A confirmed match is one-to-one: the partial unique indexes on matches
reject a second confirmed match for the same lost or found item.
"""

from typing import Any

from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from ..db import run_in_transaction
from ..errors import Conflict, Forbidden, NotFound
from ..models import Item, Match, User
from ..models.common import MatchStatus, NotificationType, Role
from ..schemas.match import MatchOut, MatchPage
from . import audit_service, item_service, matching_service, notification_service

STAFF = {Role.officer, Role.admin}


async def _get(match_id: PydanticObjectId, session: AsyncClientSession | None = None) -> Match:
    match = await Match.get(match_id, session=session)
    if match is None:
        raise NotFound("Match not found")
    return match


async def _items(match: Match, session: AsyncClientSession | None = None) -> tuple[Item, Item]:
    lost = await item_service.get_item(match.lostItemId, session)
    found = await item_service.get_item(match.foundItemId, session)
    return lost, found


def _is_party(user: User, lost: Item, found: Item) -> bool:
    return user.id in (lost.reporterId, found.reporterId)


async def to_out(match: Match, user: User, items: dict[PydanticObjectId, Item] | None = None) -> MatchOut:
    if items is None:
        lost, found = await _items(match)
    else:
        lost, found = items[match.lostItemId], items[match.foundItemId]
    # Each item is shown with the fields this viewer may see (§5.1): the
    # owner of the lost item sees the found item's member view, not its photos.
    return MatchOut(
        **match.model_dump(include={"id", "lostItemId", "foundItemId", "score", "reasons", "status", "createdAt"}),
        lostItem=item_service.to_view(lost, user),
        foundItem=item_service.to_view(found, user),
    )


async def list_matches(
    user: User, *, status: MatchStatus | None = None, mine: bool = True, page: int = 1, page_size: int = 20
) -> MatchPage:
    query: dict[str, Any] = {}
    if mine or user.role not in STAFF:
        my_items = [d["_id"] async for d in Item.get_pymongo_collection().find({"reporterId": user.id}, {"_id": 1})]
        query["$or"] = [{"lostItemId": {"$in": my_items}}, {"foundItemId": {"$in": my_items}}]
    if status is not None:
        query["status"] = status.value

    total = await Match.find(query).count()
    matches = await Match.find(query).sort("-score", "-createdAt").skip((page - 1) * page_size).limit(page_size).to_list()
    ids = list({m.lostItemId for m in matches} | {m.foundItemId for m in matches})
    items = {i.id: i for i in await Item.find({"_id": {"$in": ids}}).to_list()}
    return MatchPage(items=[await to_out(m, user, items) for m in matches], total=total, page=page, pageSize=page_size)


async def get_for(match_id: PydanticObjectId, user: User) -> MatchOut:
    match = await _get(match_id)
    lost, found = await _items(match)
    if user.role not in STAFF and not _is_party(user, lost, found):
        raise NotFound("Match not found")
    return await to_out(match, user, {lost.id: lost, found.id: found})


async def dismiss(match_id: PydanticObjectId, user: User) -> MatchOut:
    """suggested -> dismissed; items left without matches go back to open."""

    async def txn(session: AsyncClientSession) -> Match:
        match = await _get(match_id, session)
        lost, found = await _items(match, session)
        if user.role not in STAFF and not _is_party(user, lost, found):
            raise NotFound("Match not found")
        result = await Match.get_pymongo_collection().update_one(
            {"_id": match.id, "status": MatchStatus.suggested.value},
            {"$set": {"status": MatchStatus.dismissed.value}},
            session=session,
        )
        if result.modified_count == 0:
            raise Conflict(f"A {match.status.value} match cannot be dismissed")
        await audit_service.log(user.id, "match.dismiss", "matches", match.id,
                                {"status": [MatchStatus.suggested.value, MatchStatus.dismissed.value]}, session=session)
        await matching_service.reopen_if_unmatched([lost.id, found.id], session, user.id)
        return await _get(match_id, session)

    return await to_out(await run_in_transaction(txn), user)


async def confirm(match_id: PydanticObjectId, officer: User) -> MatchOut:
    """Officer: suggested -> confirmed. Other suggestions for both items are
    dismissed in the same transaction (§4.3 point 3)."""

    async def txn(session: AsyncClientSession) -> Match:
        match = await _get(match_id, session)
        lost, found = await _items(match, session)
        result = await Match.get_pymongo_collection().update_one(
            {"_id": match.id, "status": MatchStatus.suggested.value},
            {"$set": {"status": MatchStatus.confirmed.value}},
            session=session,
        )
        if result.modified_count == 0:
            raise Conflict(f"A {match.status.value} match cannot be confirmed")
        others = await Match.get_pymongo_collection().update_many(
            {"_id": {"$ne": match.id}, "status": MatchStatus.suggested.value,
             "$or": [{"lostItemId": lost.id}, {"foundItemId": found.id}]},
            {"$set": {"status": MatchStatus.dismissed.value}},
            session=session,
        )
        await audit_service.log(officer.id, "match.confirm", "matches", match.id,
                                {"status": [MatchStatus.suggested.value, MatchStatus.confirmed.value],
                                 "otherSuggestionsDismissed": others.modified_count}, session=session)
        # Items that only had those other suggestions are free to match again.
        affected = [d async for d in Match.get_pymongo_collection().find(
            {"_id": {"$ne": match.id}, "$or": [{"lostItemId": lost.id}, {"foundItemId": found.id}]},
            {"lostItemId": 1, "foundItemId": 1}, session=session)]
        others_ids = {d["foundItemId"] for d in affected} | {d["lostItemId"] for d in affected}
        await matching_service.reopen_if_unmatched(list(others_ids - {lost.id, found.id}), session, officer.id)
        await notification_service.notify(
            lost.reporterId, NotificationType.new_match,
            f"An officer confirmed a match for your {lost.title.lower()}; you can now claim it",
            match.id, f"match_confirmed:{match.id}:{lost.reporterId}", session=session,
        )
        return await _get(match_id, session)

    try:
        match = await run_in_transaction(txn)
    except DuplicateKeyError:
        # Partial unique index: one of the items already has a confirmed match.
        raise Conflict("One of these items already has a confirmed match") from None
    return await to_out(match, officer)


async def set_status(match_id: PydanticObjectId, status: MatchStatus, user: User) -> MatchOut:
    if status == MatchStatus.dismissed:
        return await dismiss(match_id, user)
    if status == MatchStatus.confirmed:
        if user.role not in STAFF:
            raise Forbidden("Only an officer can confirm a match")
        return await confirm(match_id, user)
    raise Conflict("A match cannot be set back to suggested")
