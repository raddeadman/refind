"""The example router: public read, admin-only writes, audit trail."""

from app.models import AuditLog, Category, Item
from app.models.common import Role, UserStatus

from .conftest import auth
from .test_database_rules import make_item

NEW = {"code": "wallets", "name": "Wallets", "defaultQuestions": ["What colour is it?"]}


async def test_health(client):
    assert (await client.get("/api/health")).json() == {"status": "ok"}


async def test_list_is_public(client):
    await Category(code="keys", name="Keys").insert()
    response = await client.get("/api/categories")
    assert response.status_code == 200
    assert [c["code"] for c in response.json()] == ["keys"]


async def test_create_requires_admin(client, make_user):
    assert (await client.post("/api/categories", json=NEW)).status_code == 401
    user = await make_user(Role.user)
    assert (await client.post("/api/categories", json=NEW, headers=auth(user))).status_code == 403
    officer = await make_user(Role.officer)
    assert (await client.post("/api/categories", json=NEW, headers=auth(officer))).status_code == 403


async def test_admin_creates_category_with_audit(client, make_user):
    admin = await make_user(Role.admin)
    response = await client.post("/api/categories", json=NEW, headers=auth(admin))
    assert response.status_code == 201
    log = await AuditLog.find_one(AuditLog.action == "category.create")
    assert log is not None and log.actorId == admin.id
    # Duplicate code -> 409, never a 500.
    assert (await client.post("/api/categories", json=NEW, headers=auth(admin))).status_code == 409


async def test_invalid_code_is_422(client, make_user):
    admin = await make_user(Role.admin)
    response = await client.post("/api/categories", json=NEW | {"code": "Bad Code!"}, headers=auth(admin))
    assert response.status_code == 422


async def test_rename_keeps_code(client, make_user):
    admin = await make_user(Role.admin)
    await Category(**NEW).insert()
    response = await client.patch("/api/categories/wallets", json={"name": "Wallets & purses"}, headers=auth(admin))
    assert response.status_code == 200
    assert response.json()["code"] == "wallets" and response.json()["name"] == "Wallets & purses"


async def test_cannot_delete_category_in_use(client, make_user):
    admin = await make_user(Role.admin)
    await Category(**NEW).insert()
    await make_item(category="wallets", reporterId=admin.id).insert()
    assert (await client.delete("/api/categories/wallets", headers=auth(admin))).status_code == 409
    await Item.delete_all()
    assert (await client.delete("/api/categories/wallets", headers=auth(admin))).status_code == 204


async def test_disabled_user_rejected_immediately(client, make_user):
    admin = await make_user(Role.admin)
    headers = auth(admin)
    await admin.set({"status": UserStatus.disabled})
    # Token is still valid, but the account is checked on every request.
    assert (await client.post("/api/categories", json=NEW, headers=headers)).status_code == 401
