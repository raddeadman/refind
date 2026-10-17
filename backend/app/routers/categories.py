"""Example router: copy this shape for items, matches, claims, ...

Routes only check access (dependencies), validate input (Pydantic) and call
a service function. They never touch the database directly.
"""

from fastapi import APIRouter, status

from ..deps import AdminUser
from ..models import Category
from ..services import category_service
from ..services.category_service import CategoryCreate, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[Category], summary="List categories (public)")
async def list_categories() -> list[Category]:
    return await category_service.list_categories()


@router.post("", response_model=Category, status_code=status.HTTP_201_CREATED)
async def create_category(data: CategoryCreate, admin: AdminUser) -> Category:
    return await category_service.create(data, admin.id)


@router.patch("/{code}", response_model=Category)
async def update_category(code: str, data: CategoryUpdate, admin: AdminUser) -> Category:
    return await category_service.update(code, data, admin.id)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(code: str, admin: AdminUser) -> None:
    await category_service.delete(code, admin.id)
