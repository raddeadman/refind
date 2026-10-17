from fastapi import APIRouter

from ..db import get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    await get_db().command("ping")
    return {"status": "ok"}
