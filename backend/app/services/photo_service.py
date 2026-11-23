"""Item photos in GridFS (§4.5, §5.3). Owner: Faisal.

Rules: JPEG/PNG only (checked by content, not by the file name), at most
5 MB each and 4 per item; files are stored under a random name with
metadata {itemId, uploadedBy, contentType}. Photos are only served through
the role-checked GET /api/photos/{id} (reporter, officer, admin).

GridFS cannot run inside a multi-document transaction, so an upload stores
the files first and then attaches them to the item in a transaction; if that
step fails, the new files are deleted again.
"""

import uuid
from dataclasses import dataclass

from beanie import PydanticObjectId
from gridfs import AsyncGridFSBucket
from gridfs.errors import NoFile
from pymongo.asynchronous.client_session import AsyncClientSession

from ..db import PHOTO_BUCKET, get_db, run_in_transaction
from ..errors import Forbidden, InvalidInput, NotFound
from ..models import Item, User
from ..models.item import MAX_PHOTOS
from . import audit_service
from .item_service import VISIBLE, get_item, has_full_access, is_staff

MAX_BYTES = 5 * 1024 * 1024
_SIGNATURES = {
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}


@dataclass
class Upload:
    content: bytes
    filename: str | None = None


@dataclass
class Photo:
    content: bytes
    content_type: str


def bucket() -> AsyncGridFSBucket:
    return AsyncGridFSBucket(get_db(), bucket_name=PHOTO_BUCKET)


def detect_type(content: bytes) -> tuple[str, str]:
    for signature, kind in _SIGNATURES.items():
        if content.startswith(signature):
            return kind
    raise InvalidInput("Only JPEG and PNG photos are allowed")


async def add_photos(item_id: PydanticObjectId, uploads: list[Upload], user: User) -> Item:
    if not uploads:
        raise InvalidInput("Choose at least one photo")
    item = await get_item(item_id)
    if not has_full_access(item, user):
        raise Forbidden("Only the reporter or an officer can add photos")
    if item.status not in VISIBLE and not is_staff(user):
        raise InvalidInput(f"Photos cannot be added to a {item.status.value} item")
    if len(item.photoIds) + len(uploads) > MAX_PHOTOS:
        raise InvalidInput(f"An item can have at most {MAX_PHOTOS} photos")

    checked: list[tuple[bytes, str, str]] = []
    for upload in uploads:
        if len(upload.content) > MAX_BYTES:
            raise InvalidInput(f"{upload.filename or 'A photo'} is larger than 5 MB")
        content_type, ext = detect_type(upload.content)
        checked.append((upload.content, content_type, ext))

    fs = bucket()
    new_ids: list[PydanticObjectId] = []
    try:
        for content, content_type, ext in checked:
            file_id = await fs.upload_from_stream(
                f"{uuid.uuid4().hex}.{ext}",  # never the client's file name
                content,
                metadata={"itemId": item.id, "uploadedBy": user.id, "contentType": content_type},
            )
            new_ids.append(PydanticObjectId(file_id))

        async def txn(session: AsyncClientSession) -> Item:
            current = await get_item(item_id, session)
            # Re-checked: another upload may have finished in the meantime.
            if len(current.photoIds) + len(new_ids) > MAX_PHOTOS:
                raise InvalidInput(f"An item can have at most {MAX_PHOTOS} photos")
            await current.update(
                {"$push": {"photoIds": {"$each": new_ids}}, "$inc": {"version": 1}}, session=session
            )
            await audit_service.log(
                user.id, "item.addPhotos", "items", item.id, {"photoIds": [str(i) for i in new_ids]}, session=session
            )
            return await get_item(item_id, session)

        return await run_in_transaction(txn)
    except BaseException:
        for file_id in new_ids:
            try:
                await fs.delete(file_id)
            except NoFile:
                pass
        raise


async def get_photo(photo_id: PydanticObjectId, user: User) -> Photo:
    try:
        stream = await bucket().open_download_stream(photo_id)
    except NoFile:
        raise NotFound("Photo not found") from None
    metadata = stream.metadata or {}
    item = await Item.get(metadata.get("itemId"))
    # Photos can show names or marks used for verification (§5.1).
    if item is None or photo_id not in item.photoIds or not has_full_access(item, user):
        raise NotFound("Photo not found")
    return Photo(content=await stream.read(), content_type=metadata.get("contentType", "application/octet-stream"))


async def remove_photo(item_id: PydanticObjectId, photo_id: PydanticObjectId, user: User) -> Item:
    async def txn(session: AsyncClientSession) -> Item:
        item = await get_item(item_id, session)
        if not has_full_access(item, user):
            raise Forbidden("Only the reporter or an officer can remove photos")
        if photo_id not in item.photoIds:
            raise NotFound("Photo not found")
        await item.update({"$pull": {"photoIds": photo_id}, "$inc": {"version": 1}}, session=session)
        await audit_service.log(
            user.id, "item.removePhoto", "items", item.id, {"photoId": str(photo_id)}, session=session
        )
        return await get_item(item_id, session)

    item = await run_in_transaction(txn)
    try:
        await bucket().delete(photo_id)  # after the commit: the item no longer points to it
    except NoFile:
        pass
    return item
