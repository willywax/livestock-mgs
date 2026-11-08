import pytest

from conftest import TEST_PASSWORD, USER_PHONES

pytestmark = pytest.mark.asyncio

# The 13 business GET routes that were open before R1 (KNOWN_ISSUES K02).
CLOSED_ROUTES = [
    "/api/locations",
    "/api/locations/1",
    "/api/categories",
    "/api/diseases",
    "/api/opening-balances",
    "/api/daily-logs",
    "/api/daily-logs/1",
    "/api/stock-levels",
    "/api/dashboard",
    "/api/reports/daily",
    "/api/reports/range",
    "/api/reports/analytics",
    "/api/reports/detailed",
]


@pytest.mark.parametrize("route", CLOSED_ROUTES)
async def test_protected_routes_reject_anonymous(client, route):
    assert (await client.get(route)).status_code == 403


@pytest.mark.parametrize("route", CLOSED_ROUTES)
async def test_protected_routes_reject_garbage_token(client, route):
    r = await client.get(route, headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


async def test_login_success(client):
    r = await client.post("/api/auth/login",
                          json={"phone": USER_PHONES["admin"], "password": TEST_PASSWORD})
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_login_wrong_password(client):
    r = await client.post("/api/auth/login",
                          json={"phone": USER_PHONES["admin"], "password": "wrong"})
    assert r.status_code == 401


async def test_health_is_public(client):
    assert (await client.get("/api/")).status_code == 200
