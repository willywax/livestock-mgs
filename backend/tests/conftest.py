"""Mocked-infrastructure test fixtures: SQLite in-memory, no network, no server.

The env vars below MUST be set before `server`/`auth`/`database` are imported:
auth.py reads JWT_SECRET and database.py builds its engine at import time.
"""
import os
import sys

os.environ["JWT_SECRET"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date  # noqa: E402

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import and_, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from auth import create_access_token, get_password_hash  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import (  # noqa: E402
    Category, DailyLog, Location, OpeningBalance, SpeciesType, StockLevel,
    User, UserRole,
)
from seed_data import get_seed_categories  # noqa: E402
from server import app  # noqa: E402

TEST_PASSWORD = "test-pass"
# bcrypt is slow: hash once, reuse for every seeded user.
_PASSWORD_HASH = get_password_hash(TEST_PASSWORD)
# Seeded in this order on a fresh DB, so ids are deterministic.
USER_IDS = {"admin": 1, "data_entry": 2, "viewer": 3}
USER_PHONES = {"admin": "255700000001", "data_entry": "255700000002", "viewer": "255700000003"}
FARM_ID = 1  # "Test Farm"


def token(role: str) -> str:
    """Bearer header value for the seeded user of that role."""
    return "Bearer " + create_access_token({"sub": str(USER_IDS[role])})


def auth(role: str) -> dict:
    return {"Authorization": token(role)}


async def make_location(db: AsyncSession, name: str) -> int:
    loc = Location(name=name)
    db.add(loc)
    await db.commit()
    return loc.id


async def make_daily_log(db: AsyncSession, location_id: int, log_date: date) -> int:
    log = DailyLog(location_id=location_id, log_date=log_date)
    db.add(log)
    await db.commit()
    return log.id


async def lock_log(db: AsyncSession, log_id: int) -> None:
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id))).scalar_one()
    log.is_locked = True
    await db.commit()


async def category_id(db: AsyncSession, species: SpeciesType, name_sw: str = "Koo") -> int:
    q = select(Category.id).where(and_(Category.species == species, Category.name_sw == name_sw))
    return (await db.execute(q)).scalar_one()


async def make_stock(db, location_id, species, cat_id, count) -> None:
    """Upsert a StockLevel row."""
    q = select(StockLevel).where(and_(
        StockLevel.location_id == location_id,
        StockLevel.species == species,
        StockLevel.category_id == cat_id,
    ))
    row = (await db.execute(q)).scalar_one_or_none()
    if row:
        row.current_count = count
    else:
        db.add(StockLevel(location_id=location_id, species=species,
                          category_id=cat_id, current_count=count))
    await db.commit()


async def stock_count(db, location_id, species, cat_id) -> int:
    q = select(StockLevel.current_count).where(and_(
        StockLevel.location_id == location_id,
        StockLevel.species == species,
        StockLevel.category_id == cat_id,
    ))
    return (await db.execute(q)).scalar_one()


async def post_event(client, log_id: int, role: str = "admin", **body):
    return await client.post(f"/api/daily-logs/{log_id}/events", json=body, headers=auth(role))


async def api_stock(client, location_id: int, cat_id: int) -> int:
    """Stock count for a category, read through the HTTP API."""
    r = await client.get(
        f"/api/stock-levels?location_id={location_id}&species=cattle", headers=auth("admin")
    )
    return next(s["current_count"] for s in r.json() if s["category_id"] == cat_id)


@pytest_asyncio.fixture
async def async_engine():
    """Fresh in-memory DB per test (millisecond-cheap; isolates routes that commit)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(Location(name="Test Farm"))
        for role in ("admin", "data_entry", "viewer"):
            s.add(User(phone=USER_PHONES[role], password_hash=_PASSWORD_HASH,
                       name=role, role=UserRole(role)))
        s.add_all(get_seed_categories())
        await s.flush()
        koo = await category_id(s, SpeciesType.CATTLE)
        s.add(OpeningBalance(location_id=FARM_ID, species=SpeciesType.CATTLE,
                             category_id=koo, count=50, period_start=date(2024, 1, 1)))
        # stock_levels is a separate projection: opening balances do not fill it.
        s.add(StockLevel(location_id=FARM_ID, species=SpeciesType.CATTLE,
                         category_id=koo, current_count=50))
        await s.commit()
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        app.dependency_overrides[get_db] = lambda: session
        yield session
        app.dependency_overrides.pop(get_db, None)
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
