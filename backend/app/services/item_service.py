"""Items: report, search, view, edit, withdraw (§3, §4.2, §5.1).

Owner: Faisal. Visibility rules live here, in one place:
  * reporter, officers and admins get the full view of an item;
  * everybody else only sees found items that are still open or matched
    (lost reports are private), as the public or member view.
"""

from datetime import datetime
from typing import Any, Literal

from beanie import PydanticObjectId
from pydantic import ValidationError
from pymongo.asynchronous.client_session import AsyncClientSession

from ..db import run_in_transaction
from ..errors import Conflict, Forbidden, InvalidInput, NotFound
from ..models import Category, Item, ItemSecret, StatusChange, User, VerificationQuestion
from ..models.common import ItemStatus, ItemType, Role
from ..schemas.item import ItemCreate, ItemPage, ItemPublic, ItemUpdate, midnight_utc, view_of
from ..security import hash_secret
from . import audit_service

STAFF = {Role.officer, Role.admin}
# Statuses a non-owner may see, and in which the reporter may still edit.
VISIBLE = (ItemStatus.open, ItemStatus.matched)
MAX_PAGE_SIZE = 50

Access = Literal["public", "member", "full"]


# ------------------------------------------------------------ visibility


def is_staff(user: User | None) -> bool:
    return user is not None and user.role in STAFF


def has_full_access(item: Item, user: User | None) -> bool:
    return user is not None and (user.role in STAFF or user.id == item.reporterId)


def access_for(item: Item, user: User | None) -> Access:
    if has_full_access(item, user):
        return "full"
    return "member" if user is not None else "public"


def can_see(item: Item, user: User | None) -> bool:
    return has_full_access(item, user) or (item.type == ItemType.found and item.status in VISIBLE)


def to_view(item: Item, user: User | None) -> ItemPublic:
    return view_of(item, access_for(item, user))


async def get_item(item_id: PydanticObjectId, session: AsyncClientSession | None = None) -> Item:
    item = await Item.get(item_id, session=session)
    if item is None:
        raise NotFound("Item not found")
    return item


async def get_visible(item_id: PydanticObjectId, user: User | None) -> Item:
    item = await get_item(item_id)
    # 404, not 403, so private reports do not reveal that they exist.
    if not can_see(item, user):
        raise NotFound("Item not found")
    return item


async def _check_category(code: str, session: AsyncClientSession) -> None:
    if await Category.find_one(Category.code == code, session=session) is None:
        raise InvalidInput(f"Unknown category '{code}'")


# ---------------------------------------------------------------- create


async def create(data: ItemCreate, reporter: User) -> Item:
    """Insert the item, and for a found item its itemSecrets, in one transaction."""
    # bcrypt is slow: hash once, outside the transaction (which may retry).
    secret_questions = [
        VerificationQuestion(question=v.question.strip(), answerHash=hash_secret(v.answer)) for v in data.verification
    ]
    serial_hash = hash_secret(data.serialNumber) if data.serialNumber else None

    async def txn(session: AsyncClientSession) -> Item:
        await _check_category(data.category, session)
        item = Item(
            **data.model_dump(include={"type", "title", "category", "attributes", "description", "location",
                                       "approxTime", "heldAt"}),
            date=midnight_utc(data.date),
            reporterId=reporter.id,
        )
        item.statusHistory = [StatusChange(status=ItemStatus.open, at=item.timeSubmitted, by=reporter.id)]
        await item.insert(session=session)
        if item.type == ItemType.found:
            await ItemSecret(itemId=item.id, verification=secret_questions, serialNumberHash=serial_hash).insert(
                session=session
            )
        await audit_service.log(
            reporter.id,
            "item.create",
            "items",
            item.id,
            # Never log answers or the serial number.
            data.model_dump(mode="json", exclude={"verification", "serialNumber"})
            | {"questions": len(secret_questions)},
            session=session,
        )
        return item

    # TODO(M4, Abdullah): run matching_service.find_matches(item) here (§4.3).
    return await run_in_transaction(txn)


# ---------------------------------------------------------------- search


async def search(
    user: User | None,
    *,
    type: ItemType | None = None,
    category: str | None = None,
    building: str | None = None,
    status: ItemStatus | None = None,
    q: str | None = None,
    date_from=None,
    date_to=None,
    mine: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> ItemPage:
    """Filters are built only from these whitelisted parameters (§5.3)."""
    query: dict[str, Any] = {}

    if mine:
        if user is None:
            raise Forbidden("Log in to see your reports")
        query["reporterId"] = user.id
    elif not is_staff(user):
        # Public search: open/matched found items only.
        if type == ItemType.lost:
            raise Forbidden("Lost reports are private")
        type = ItemType.found
        if status is not None and status not in VISIBLE:
            return ItemPage(items=[], total=0, page=page, pageSize=page_size)
        query["status"] = {"$in": [s.value for s in VISIBLE]}

    if type is not None:
        query["type"] = type.value
    if status is not None:
        query["status"] = status.value
    if category:
        query["category"] = category
    if building:
        query["location.building"] = building
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = midnight_utc(date_from)
        if date_to:
            query["date"]["$lte"] = midnight_utc(date_to)
    if q and q.strip():
        query["$text"] = {"$search": q.strip()}

    total = await Item.find(query).count()
    items = await Item.find(query).sort("-date", "-timeSubmitted").skip((page - 1) * page_size).limit(page_size).to_list()
    return ItemPage(items=[to_view(i, user) for i in items], total=total, page=page, pageSize=page_size)


# ------------------------------------------------------------------ edit


def _check_can_edit(item: Item, user: User) -> None:
    if not has_full_access(item, user):
        raise Forbidden("Only the reporter or an officer can change this item")
    if item.status in (ItemStatus.returned, ItemStatus.archived):
        raise Conflict(f"A {item.status.value} item cannot be changed")
    if item.status not in VISIBLE and not is_staff(user):
        raise Conflict(f"A {item.status.value} item can only be changed by an officer")


async def update(item_id: PydanticObjectId, data: ItemUpdate, user: User) -> Item:
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if "date" in changes and changes["date"] is not None:
        changes["date"] = midnight_utc(changes["date"])
    for required in ("title", "category", "location", "date", "attributes"):
        if required in changes and changes[required] is None:
            raise InvalidInput(f"{required} cannot be empty")

    async def txn(session: AsyncClientSession) -> Item:
        item = await get_item(item_id, session)
        _check_can_edit(item, user)
        # Optimistic concurrency: a concurrent save changes the version (and,
        # inside the snapshot transaction, causes a retry that lands here).
        if item.version != data.version:
            raise Conflict("The item was changed by someone else; reload and try again")
        if not changes:
            return item
        if item.type == ItemType.lost and changes.get("heldAt"):
            raise InvalidInput("Only found items have heldAt")
        if "category" in changes:
            await _check_category(changes["category"], session)
        try:
            # Re-runs every model rule, e.g. date/approxTime not after timeSubmitted.
            merged = Item.model_validate(item.model_dump() | changes)
        except ValidationError as exc:
            raise InvalidInput(exc.errors()[0]["msg"].removeprefix("Value error, ")) from None
        new_values = {key: getattr(merged, key) for key in changes} | {"version": item.version + 1}
        await item.set(new_values, session=session)
        await audit_service.log(
            user.id, "item.update", "items", item.id, data.model_dump(mode="json", exclude_unset=True),
            session=session,
        )
        return item

    return await run_in_transaction(txn)


async def archive(item_id: PydanticObjectId, user: User, note: str | None = None) -> Item:
    """Reporter withdraws the report, or an officer archives it (open/matched -> archived)."""

    async def txn(session: AsyncClientSession) -> Item:
        item = await get_item(item_id, session)
        if not has_full_access(item, user):
            raise Forbidden("Only the reporter or an officer can withdraw this item")
        previous = item.status
        if previous not in VISIBLE:
            raise Conflict(f"A {previous.value} item cannot be withdrawn")
        change = StatusChange(status=ItemStatus.archived, by=user.id, note=note)
        await item.update(
            {
                "$set": {"status": ItemStatus.archived.value},
                "$push": {"statusHistory": change.model_dump()},
                "$inc": {"version": 1},
            },
            session=session,
        )
        await audit_service.log(
            user.id, "item.archive", "items", item.id, {"from": previous.value, "note": note}, session=session
        )
        return await get_item(item_id, session)

    return await run_in_transaction(txn)
