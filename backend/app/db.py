"""One MongoDB client and connection pool for the whole app (§4.2)."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .models import ALL_MODELS

T = TypeVar("T")

_client: AsyncMongoClient | None = None
_db: AsyncDatabase | None = None


async def connect(uri: str, db_name: str) -> AsyncDatabase:
    """Create the client, register every Beanie model and build indexes."""
    global _client, _db
    _client = AsyncMongoClient(uri, tz_aware=True, uuidRepresentation="standard")
    _db = _client[db_name]
    await init_beanie(database=_db, document_models=ALL_MODELS)
    return _db


async def disconnect() -> None:
    global _client, _db
    if _client is not None:
        await _client.close()
    _client = _db = None


def get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("Database not connected")
    return _client


def get_db() -> AsyncDatabase:
    if _db is None:
        raise RuntimeError("Database not connected")
    return _db


async def run_in_transaction(callback: Callable[[AsyncClientSession], Awaitable[T]]) -> T:
    """Run callback(session) as one multi-document transaction (§5.4).

    with_transaction() retries the whole callback on transient errors such
    as WriteConflict, so the callback must be safe to run more than once.
    Pass session=session to every Beanie/PyMongo call inside it.
    """
    async with get_client().start_session() as session:
        return await session.with_transaction(
            callback,
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
        )
