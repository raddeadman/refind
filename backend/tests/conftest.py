"""Integration tests run against the refind_test database as refindApp.

Collections are emptied with delete_many (not dropped) so the $jsonSchema
validators applied by scripts/setup_db.py stay in place.
"""

import os

from app.config import get_settings

os.environ["MONGO_DB"] = get_settings().mongo_test_db  # before the app reads settings
get_settings.cache_clear()

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from pymongo.errors import ConnectionFailure  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ALL_MODELS, User  # noqa: E402
from app.models.common import Role, UserStatus  # noqa: E402
from app.services import rate_limit  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402

settings = get_settings()


@pytest.fixture(scope="session", autouse=True)
async def database():
    try:
        await db.connect(settings.app_uri + "&serverSelectionTimeoutMS=2000", settings.mongo_db)
    except ConnectionFailure as exc:
        pytest.skip(f"MongoDB not reachable ({exc.__class__.__name__}); run docker compose up -d")
    yield db.get_db()
    rate_limit.close()
    await db.disconnect()


@pytest.fixture(autouse=True)
async def clean(database):
    for model in ALL_MODELS:
        await model.get_pymongo_collection().delete_many({})
    for name in ("rateLimitCounters", "rateLimitWindows"):
        await database[name].delete_many({})
    yield


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password("Password123!")  # bcrypt is slow; hash once


@pytest.fixture
def make_user(password_hash):
    async def _make(role: Role = Role.user, status: UserStatus = UserStatus.active, email: str | None = None) -> User:
        count = await User.count()
        user = User(
            name=f"{role.value} {count}",
            email=email or f"{role.value}{count}@{settings.allowed_email_domains[0]}",
            passwordHash=password_hash,
            role=role,
            status=status,
        )
        return await user.insert()

    return _make


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
