"""Matching engine (§4.3). Owner: Abdullah.

on_item_saved() runs after an item is reported or edited:

1. one aggregation pipeline finds candidates of the opposite type
   (same category, status open/matched, date within ±7 days) using the
   type_category_status_date index, scores them and keeps score >= 60,
   best first, at most 5;
2. keywords both location descriptions share are added to the reasons;
3. in one transaction each candidate is upserted on the (lost, found) pair
   with $setOnInsert, so an existing match is never changed or duplicated;
   only a newly inserted match moves items open -> matched, notifies the
   owner of the lost item and writes an audit entry.

Re-saving an item therefore never creates a second match or alert.

Score (max 100):
    category 30 (always, from the $match)
    location up to 25: same building 15, same floor 5, same area 5
    date up to 20: 16 on the same day, -3 per day apart, +4 when both
                   approximate times are within 2 hours on the same day
    attributes up to 25: same colour 15, same brand 10
"""

import logging
import re
from datetime import timedelta
from typing import Any

from beanie import PydanticObjectId
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import PyMongoError

from ..db import run_in_transaction
from ..models import Item, Match, StatusChange
from ..models.common import ItemStatus, ItemType, MatchStatus, NotificationType, utcnow
from . import audit_service, notification_service

log = logging.getLogger(__name__)

WINDOW_DAYS = 7
MIN_SCORE = 60
MAX_CANDIDATES = 5
TIME_BONUS_MINUTES = 120
ACTIVE = [ItemStatus.open.value, ItemStatus.matched.value]

_WORD = re.compile(r"[a-z]{4,}")
_STOPWORDS = {
    "near", "next", "with", "from", "that", "this", "there", "left", "right", "inside", "outside",
    "under", "behind", "front", "floor", "room", "area", "side", "found", "lost", "item", "about",
}


# ------------------------------------------------------------- pipeline


def _lit(value: Any) -> dict:
    # Every user-supplied value goes into the pipeline as a $literal, so a
    # colour such as "$title" is compared as text, never read as a field path.
    return {"$literal": value}


def _norm(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


def _same_text(field: str, value: str | None) -> dict:
    """True when `field` (case-insensitive, trimmed) equals value; never for empty values."""
    if value is None:
        return {"$literal": False}
    return {"$eq": [{"$toLower": {"$trim": {"input": {"$ifNull": [f"${field}", ""]}}}}, _lit(value)]}


def _minutes(expr: Any) -> dict:
    """'HH:MM' -> minutes after midnight."""
    return {
        "$add": [
            {"$multiply": [{"$toInt": {"$substrBytes": [expr, 0, 2]}}, 60]},
            {"$toInt": {"$substrBytes": [expr, 3, 2]}},
        ]
    }


def _reason(condition: Any, text: Any) -> dict:
    return {"$cond": [condition, [text], []]}


def build_pipeline(item: Item) -> list[dict]:
    loc, attrs = item.location, item.attributes
    floor, area = _norm(loc.floor), _norm(loc.area)
    color, brand = _norm(attrs.color), _norm(attrs.brand)
    window = timedelta(days=WINDOW_DAYS)

    if item.approxTime:
        hours, minutes = map(int, item.approxTime.split(":"))
        time_close: Any = {
            "$and": [
                {"$eq": ["$_days", 0]},
                {"$ne": [{"$ifNull": ["$approxTime", None]}, None]},
                {"$lte": [{"$abs": {"$subtract": [_minutes("$approxTime"), hours * 60 + minutes]}},
                          TIME_BONUS_MINUTES]},
            ]
        }
    else:
        time_close = {"$literal": False}

    return [
        # 1. Candidates: served by the type_category_status_date index.
        {
            "$match": {
                "type": (ItemType.found if item.type == ItemType.lost else ItemType.lost).value,
                "category": item.category,
                "status": {"$in": ACTIVE},
                "date": {"$gte": item.date - window, "$lte": item.date + window},
                "_id": {"$ne": item.id},
                "reporterId": {"$ne": item.reporterId},
            }
        },
        # 2. Score each part.
        {
            "$addFields": {
                "_days": {"$abs": {"$dateDiff": {"startDate": "$date", "endDate": _lit(item.date), "unit": "day"}}},
                "_building": {"$eq": ["$location.building", _lit(loc.building)]},
                "_floor": _same_text("location.floor", floor),
                "_area": _same_text("location.area", area),
                "_color": _same_text("attributes.color", color),
                "_brand": _same_text("attributes.brand", brand),
            }
        },
        {"$addFields": {"_timeClose": time_close}},
        {
            "$addFields": {
                "score": {
                    "$add": [
                        30,
                        {"$cond": ["$_building", 15, 0]},
                        {"$cond": ["$_floor", 5, 0]},
                        {"$cond": ["$_area", 5, 0]},
                        {"$max": [0, {"$subtract": [16, {"$multiply": ["$_days", 3]}]}]},
                        {"$cond": ["$_timeClose", 4, 0]},
                        {"$cond": ["$_color", 15, 0]},
                        {"$cond": ["$_brand", 10, 0]},
                    ]
                },
                "reasons": {
                    "$concatArrays": [
                        ["same category"],
                        _reason("$_building", {"$concat": ["same building (", "$location.building", ")"]}),
                        _reason("$_floor", "same floor"),
                        _reason("$_area", "same area"),
                        [{"$cond": [{"$eq": ["$_days", 0]}, "same day",
                                    {"$concat": ["dates ", {"$toString": "$_days"}, " day(s) apart"]}]}],
                        _reason("$_timeClose", "similar time of day"),
                        _reason("$_color", {"$concat": ["same colour (", "$attributes.color", ")"]}),
                        _reason("$_brand", {"$concat": ["same brand (", "$attributes.brand", ")"]}),
                    ]
                },
            }
        },
        # 4. Keep the good ones, best first.
        {"$match": {"score": {"$gte": MIN_SCORE}}},
        {"$sort": {"score": -1, "date": -1}},
        {"$limit": MAX_CANDIDATES},
        {"$project": {"score": 1, "reasons": 1, "type": 1, "title": 1, "reporterId": 1, "status": 1,
                      "location.area": 1, "location.details": 1}},
    ]


def _keywords(location: dict | Any) -> set[str]:
    if not isinstance(location, dict):
        location = location.model_dump()
    text = " ".join(filter(None, [location.get("area"), location.get("details")])).lower()
    return set(_WORD.findall(text)) - _STOPWORDS


async def find_candidates(item: Item, session: AsyncClientSession | None = None) -> list[dict]:
    cursor = await Item.get_pymongo_collection().aggregate(build_pipeline(item), session=session)
    candidates = await cursor.to_list()
    mine = _keywords(item.location)
    for candidate in candidates:
        # 3. Shared words in the location descriptions explain the match.
        shared = sorted(mine & _keywords(candidate.get("location", {})))
        if shared:
            candidate["reasons"].append("both mention " + ", ".join(f"'{w}'" for w in shared[:3]))
    return candidates


# ---------------------------------------------------------------- saving


async def _set_matched(
    item_ids: list[PydanticObjectId], session: AsyncClientSession
) -> list[PydanticObjectId]:
    """open -> matched for those still open; returns the ids that changed."""
    collection = Item.get_pymongo_collection()
    changed = [d["_id"] async for d in collection.find({"_id": {"$in": item_ids}, "status": "open"}, {"_id": 1},
                                                       session=session)]
    if changed:
        change = StatusChange(status=ItemStatus.matched, note="matching engine").model_dump()
        await collection.update_many(
            {"_id": {"$in": changed}, "status": "open"},
            {"$set": {"status": ItemStatus.matched.value}, "$push": {"statusHistory": change}, "$inc": {"version": 1}},
            session=session,
        )
    return changed


async def on_item_saved(item: Item) -> list[Match]:
    """Find and save matches for a just-saved item; returns the newly created ones.

    A failure here never undoes the item report (already committed): it is
    logged, and the next edit of either item runs matching again.
    """
    if item.status not in (ItemStatus.open, ItemStatus.matched):
        return []
    try:
        candidates = await find_candidates(item)
        if not candidates:
            return []
        return await run_in_transaction(lambda session: _save(item, candidates, session))
    except PyMongoError:
        log.exception("Matching failed for item %s", item.id)
        return []


async def _save(item: Item, candidates: list[dict], session: AsyncClientSession) -> list[Match]:
    created: list[Match] = []
    collection = Match.get_pymongo_collection()
    for candidate in candidates:
        lost_id, found_id = (item.id, candidate["_id"]) if item.type == ItemType.lost else (candidate["_id"], item.id)
        match = Match(lostItemId=lost_id, foundItemId=found_id, score=min(int(candidate["score"]), 100),
                      reasons=candidate["reasons"], status=MatchStatus.suggested, createdAt=utcnow())
        result = await collection.update_one(
            {"lostItemId": lost_id, "foundItemId": found_id},
            {"$setOnInsert": match.model_dump(exclude={"id", "lostItemId", "foundItemId"})},
            upsert=True,
            session=session,
        )
        if result.upserted_id is None:
            continue  # pair already known: left untouched, no new alert
        match.id = result.upserted_id
        created.append(match)
        await audit_service.log(None, "match.create", "matches", match.id,
                                {"lostItemId": str(lost_id), "foundItemId": str(found_id), "score": match.score},
                                session=session)

        lost = item if item.type == ItemType.lost else None
        lost_owner = lost.reporterId if lost else candidate["reporterId"]
        lost_title = lost.title if lost else candidate["title"]
        await notification_service.notify(
            lost_owner,
            NotificationType.new_match,
            f"Possible match for your {lost_title.lower()} ({match.score}%)",
            match.id,
            f"new_match:{match.id}:{lost_owner}",
            session=session,
        )

    if created:
        ids = list({m.lostItemId for m in created} | {m.foundItemId for m in created})
        for item_id in await _set_matched(ids, session):
            await audit_service.log(None, "item.status", "items", item_id, {"from": "open", "to": "matched"},
                                    session=session)
    return created


# --------------------------------------------------- after a dismissal


async def reopen_if_unmatched(item_ids: list[PydanticObjectId], session: AsyncClientSession,
                              actor_id: PydanticObjectId | None = None) -> list[PydanticObjectId]:
    """matched -> open for items left with no suggested or confirmed match (§3.1).

    Used when a match is dismissed and by the claim approval transaction.
    """
    reopened = []
    items = Item.get_pymongo_collection()
    for item_id in item_ids:
        live = await Match.get_pymongo_collection().find_one(
            {"$or": [{"lostItemId": item_id}, {"foundItemId": item_id}],
             "status": {"$in": [MatchStatus.suggested.value, MatchStatus.confirmed.value]}},
            {"_id": 1},
            session=session,
        )
        if live is not None:
            continue
        change = StatusChange(status=ItemStatus.open, by=actor_id, note="no matches left").model_dump()
        result = await items.update_one(
            {"_id": item_id, "status": ItemStatus.matched.value},
            {"$set": {"status": ItemStatus.open.value}, "$push": {"statusHistory": change}, "$inc": {"version": 1}},
            session=session,
        )
        if result.modified_count:
            reopened.append(item_id)
            await audit_service.log(actor_id, "item.status", "items", item_id, {"from": "matched", "to": "open"},
                                    session=session)
    return reopened
