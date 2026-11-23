"""H1: OfficerUser lets officers and admins in, and nobody else."""

import pytest

from app.models.common import Role, UserStatus

from .conftest import auth


@pytest.mark.parametrize(
    ("role", "status", "expected"),
    [
        (Role.user, UserStatus.active, 403),
        (Role.officer, UserStatus.unverified, 403),  # must verify the email first
        (Role.officer, UserStatus.active, 200),
        (Role.admin, UserStatus.active, 200),
    ],
)
async def test_officer_endpoint(client, make_user, role, status, expected):
    user = await make_user(role, status)
    assert (await client.get("/api/matches", headers=auth(user))).status_code == expected


async def test_officer_endpoint_needs_a_token(client):
    assert (await client.get("/api/matches")).status_code == 401
