import pytest

from conftest import FARM_ID, category_id, make_location, make_stock, stock_count
from models import EventType, SpeciesType
from schemas import EventCreate
from server import apply_event_to_stock, check_stock_availability, reverse_event_stock

pytestmark = pytest.mark.asyncio
CATTLE = SpeciesType.CATTLE


async def _apply(db, event_type, count, cat, **kw):
    ev = EventCreate(event_type=event_type, species=CATTLE, category_id=cat, count=count, **kw)
    await apply_event_to_stock(db, FARM_ID, ev)
    return ev


async def test_birth_increases_stock(db_session):
    koo = await category_id(db_session, CATTLE)
    await make_stock(db_session, FARM_ID, CATTLE, koo, 10)
    await _apply(db_session, EventType.BIRTH, 3, koo)
    assert await stock_count(db_session, FARM_ID, CATTLE, koo) == 13


async def test_death_decreases_stock(db_session):
    koo = await category_id(db_session, CATTLE)
    await make_stock(db_session, FARM_ID, CATTLE, koo, 10)
    await _apply(db_session, EventType.DEATH, 2, koo)
    assert await stock_count(db_session, FARM_ID, CATTLE, koo) == 8


async def test_sold_decreases_stock(db_session):
    koo = await category_id(db_session, CATTLE)
    await make_stock(db_session, FARM_ID, CATTLE, koo, 10)
    await _apply(db_session, EventType.SOLD, 5, koo)
    assert await stock_count(db_session, FARM_ID, CATTLE, koo) == 5


async def test_transfer_moves_between_locations(db_session):
    koo = await category_id(db_session, CATTLE)
    dest = await make_location(db_session, "Dest Farm")
    await make_stock(db_session, FARM_ID, CATTLE, koo, 20)
    await make_stock(db_session, dest, CATTLE, koo, 5)
    await _apply(db_session, EventType.TRANSFER, 3, koo, from_location_id=FARM_ID, to_location_id=dest)
    assert await stock_count(db_session, FARM_ID, CATTLE, koo) == 17
    assert await stock_count(db_session, dest, CATTLE, koo) == 8


async def test_category_change_moves_between_categories(db_session):
    src = await category_id(db_session, CATTLE, "Koo")
    dst = await category_id(db_session, CATTLE, "Mitamba")
    await make_stock(db_session, FARM_ID, CATTLE, src, 15)
    await make_stock(db_session, FARM_ID, CATTLE, dst, 0)
    await _apply(db_session, EventType.CATEGORY_CHANGE, 4, None, from_category_id=src, to_category_id=dst)
    assert await stock_count(db_session, FARM_ID, CATTLE, src) == 11
    assert await stock_count(db_session, FARM_ID, CATTLE, dst) == 4


async def test_check_stock_blocks_negative(db_session):
    koo = await category_id(db_session, CATTLE)
    await make_stock(db_session, FARM_ID, CATTLE, koo, 5)
    ev = EventCreate(event_type=EventType.DEATH, species=CATTLE, category_id=koo, count=10)
    ok, msg = await check_stock_availability(db_session, FARM_ID, ev, False)
    assert ok is False and "Insufficient" in msg
    ok, msg = await check_stock_availability(db_session, FARM_ID, ev, True)  # admin override
    assert ok is True and "Warning" in msg


async def test_reverse_undoes_apply(db_session):
    koo = await category_id(db_session, CATTLE)
    await make_stock(db_session, FARM_ID, CATTLE, koo, 10)
    ev = await _apply(db_session, EventType.SOLD, 4, koo)
    assert await stock_count(db_session, FARM_ID, CATTLE, koo) == 6
    await reverse_event_stock(db_session, FARM_ID, ev)
    assert await stock_count(db_session, FARM_ID, CATTLE, koo) == 10


async def test_abortion_does_not_affect_stock(db_session):
    # apply_event_to_stock has no ABORTION branch (and no is_stock_event check): a no-op.
    koo = await category_id(db_session, CATTLE)
    await make_stock(db_session, FARM_ID, CATTLE, koo, 10)
    await _apply(db_session, EventType.ABORTION, 2, koo, is_stock_event=False)
    assert await stock_count(db_session, FARM_ID, CATTLE, koo) == 10
