"""Rate limits stored in MongoDB, so counters survive restarts and are shared
between worker processes (§5.2).

Uses `limits` (the library slowapi is built on) directly, because logins must
count only *failed* attempts, keyed by account and IP. Its async MongoDB
backend needs the deprecated Motor driver, so the sync backend runs in a
worker thread.
"""

import asyncio
from functools import lru_cache

from limits import RateLimitItem, parse
from limits.storage import MongoDBStorage
from limits.strategies import MovingWindowRateLimiter

from ..config import get_settings

FAILED_LOGINS = parse("5/15 minutes")
VERIFICATION_EMAILS = parse("3/hour")


@lru_cache
def _limiter() -> MovingWindowRateLimiter:
    settings = get_settings()
    storage = MongoDBStorage(
        settings.app_uri,
        database_name=settings.mongo_db,
        counter_collection_name="rateLimitCounters",
        window_collection_name="rateLimitWindows",
    )
    return MovingWindowRateLimiter(storage)


async def is_blocked(item: RateLimitItem, *key: str) -> bool:
    return not await asyncio.to_thread(_limiter().test, item, *key)


async def hit(item: RateLimitItem, *key: str) -> bool:
    """Count one event; False if the limit is now exceeded."""
    return await asyncio.to_thread(_limiter().hit, item, *key)


async def reset(item: RateLimitItem, *key: str) -> None:
    await asyncio.to_thread(_limiter().clear, item, *key)


def close() -> None:
    """Close the limiter's own MongoDB client (called on shutdown)."""
    if _limiter.cache_info().currsize:
        _limiter().storage.storage.close()  # type: ignore[attr-defined]
        _limiter.cache_clear()
