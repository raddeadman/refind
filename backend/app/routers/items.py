"""Items and photos (§4.2). Owner: Faisal.

Routes only check access, validate input and call a service.
"""

from datetime import date as Date
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, File, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from ..deps import ActiveUser, CurrentUser, OptionalUser
from ..models.common import CATEGORY_CODE_PATTERN, ItemStatus, ItemType
from ..models.item import Building
from ..schemas.item import ItemCreate, ItemFull, ItemPage, ItemUpdate, ItemView
from ..services import item_service, photo_service
from ..services.item_service import MAX_PAGE_SIZE

router = APIRouter(prefix="/api/items", tags=["items"])
photos_router = APIRouter(prefix="/api/photos", tags=["items"])


class ArchiveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=300)


@router.post("", response_model=ItemFull, status_code=status.HTTP_201_CREATED, summary="Report a lost or found item")
async def create_item(data: ItemCreate, user: ActiveUser):
    item = await item_service.create(data, user)
    return item_service.to_view(item, user)


@router.get("", response_model=ItemPage, summary="Search items (guests: public fields of found items)")
async def list_items(
    user: OptionalUser,
    type: ItemType | None = None,
    category: Annotated[str | None, Query(pattern=CATEGORY_CODE_PATTERN)] = None,
    building: Building | None = None,
    status: ItemStatus | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Keywords (title, brand, description)")] = None,
    dateFrom: Date | None = None,
    dateTo: Date | None = None,
    mine: Annotated[bool, Query(description="Only my own reports (full view)")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> ItemPage:
    return await item_service.search(
        user,
        type=type,
        category=category,
        building=building,
        status=status,
        q=q,
        date_from=dateFrom,
        date_to=dateTo,
        mine=mine,
        page=page,
        page_size=pageSize,
    )


@router.get("/{item_id}", response_model=ItemView, summary="Get one item (fields depend on who asks)")
async def get_item(item_id: PydanticObjectId, user: OptionalUser):
    item = await item_service.get_visible(item_id, user)
    return item_service.to_view(item, user)


@router.patch("/{item_id}", response_model=ItemFull, summary="Edit an item (reporter or officer)")
async def update_item(item_id: PydanticObjectId, data: ItemUpdate, user: ActiveUser):
    item = await item_service.update(item_id, data, user)
    return item_service.to_view(item, user)


@router.post("/{item_id}/archive", response_model=ItemFull, summary="Withdraw / archive an item")
async def archive_item(item_id: PydanticObjectId, user: ActiveUser, data: ArchiveRequest | None = None):
    item = await item_service.archive(item_id, user, data.note if data else None)
    return item_service.to_view(item, user)


@router.post("/{item_id}/photos", response_model=ItemFull, summary="Add photos (JPEG/PNG, 5 MB, max 4 per item)")
async def upload_item_photos(
    item_id: PydanticObjectId,
    user: ActiveUser,
    files: Annotated[list[UploadFile], File(description="One to four JPEG or PNG files")],
):
    uploads = [
        # Read one byte past the limit so oversized files are detected without reading them whole.
        photo_service.Upload(content=await f.read(photo_service.MAX_BYTES + 1), filename=f.filename)
        for f in files
    ]
    item = await photo_service.add_photos(item_id, uploads, user)
    return item_service.to_view(item, user)


@router.delete("/{item_id}/photos/{photo_id}", response_model=ItemFull, summary="Remove a photo")
async def delete_item_photo(item_id: PydanticObjectId, photo_id: PydanticObjectId, user: ActiveUser):
    item = await photo_service.remove_photo(item_id, photo_id, user)
    return item_service.to_view(item, user)


@photos_router.get(
    "/{photo_id}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}},
    summary="Download a photo (reporter, officer, admin)",
)
async def get_photo(photo_id: PydanticObjectId, user: CurrentUser) -> Response:
    photo = await photo_service.get_photo(photo_id, user)
    return Response(
        photo.content,
        media_type=photo.content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
