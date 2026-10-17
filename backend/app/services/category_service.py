"""Category service: the worked example for the other services.

Pattern every service follows:
  * routes never touch the database; they call a function here;
  * every write runs in run_in_transaction() together with its audit entry;
  * failures raise ServiceError subclasses that main.py turns into HTTP codes.
"""

from beanie import PydanticObjectId
from pydantic import BaseModel, Field
from pymongo.asynchronous.client_session import AsyncClientSession

from ..db import run_in_transaction
from ..errors import Conflict, NotFound
from ..models import Category, Item
from ..models.common import CATEGORY_CODE_PATTERN
from . import audit_service


class CategoryCreate(BaseModel):
    code: str = Field(pattern=CATEGORY_CODE_PATTERN, examples=["wallets"])
    name: str = Field(min_length=1, max_length=60, examples=["Wallets & purses"])
    defaultQuestions: list[str] = Field(default_factory=list, max_length=10)


class CategoryUpdate(BaseModel):
    """The code is fixed for ever; only these fields can change."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    defaultQuestions: list[str] | None = Field(default=None, max_length=10)


async def list_categories() -> list[Category]:
    return await Category.find_all().sort(+Category.name).to_list()


async def get_by_code(code: str, session: AsyncClientSession | None = None) -> Category:
    category = await Category.find_one(Category.code == code, session=session)
    if category is None:
        raise NotFound(f"Category '{code}' not found")
    return category


async def exists(code: str) -> bool:
    return await Category.find_one(Category.code == code) is not None


async def create(data: CategoryCreate, actor_id: PydanticObjectId) -> Category:
    async def txn(session: AsyncClientSession) -> Category:
        category = Category(**data.model_dump())
        # A duplicate code raises DuplicateKeyError -> 409 (see main.py).
        await category.insert(session=session)
        await audit_service.log(
            actor_id, "category.create", "categories", category.id, data.model_dump(), session=session
        )
        return category

    return await run_in_transaction(txn)


async def update(code: str, data: CategoryUpdate, actor_id: PydanticObjectId) -> Category:
    changes = data.model_dump(exclude_unset=True)

    async def txn(session: AsyncClientSession) -> Category:
        category = await get_by_code(code, session)
        if changes:
            await category.set(changes, session=session)
            await audit_service.log(actor_id, "category.update", "categories", category.id, changes, session=session)
        return category

    return await run_in_transaction(txn)


async def delete(code: str, actor_id: PydanticObjectId) -> None:
    async def txn(session: AsyncClientSession) -> None:
        category = await get_by_code(code, session)
        if await Item.find_one(Item.category == code, session=session):
            raise Conflict("Category is used by items and cannot be deleted")
        await category.delete(session=session)
        await audit_service.log(actor_id, "category.delete", "categories", category.id, {"code": code}, session=session)

    await run_in_transaction(txn)
