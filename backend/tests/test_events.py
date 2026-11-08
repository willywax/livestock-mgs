from datetime import date

import pytest

from conftest import (
    FARM_ID, api_stock, auth, category_id, lock_log, make_daily_log,
    make_location, make_stock, post_event,
)
from models import SpeciesType

pytestmark = pytest.mark.asyncio
CATTLE = SpeciesType.CATTLE


async def _setup(db):
    return await make_daily_log(db, FARM_ID, date.today()), await category_id(db, CATTLE)


async def test_create_birth_event_increases_stock(client, db_session):
    log, koo = await _setup(db_session)
    r = await post_event(client, log, event_type="birth", species="cattle", category_id=koo, count=3)
    assert r.status_code == 200
    assert await api_stock(client, FARM_ID, koo) == 53


async def test_create_death_event_decreases_stock(client, db_session):
    log, koo = await _setup(db_session)
    r = await post_event(client, log, event_type="death", species="cattle", category_id=koo, count=2)
    assert r.status_code == 200
    assert await api_stock(client, FARM_ID, koo) == 48


async def test_edit_event_adjusts_stock_correctly(client, db_session):
    log, koo = await _setup(db_session)
    ev = (await post_event(client, log, event_type="sold", species="cattle", category_id=koo, count=5)).json()
    assert await api_stock(client, FARM_ID, koo) == 45
    r = await client.put(f"/api/events/{ev['id']}", json={"count": 3}, headers=auth("admin"))
    assert r.status_code == 200
    assert await api_stock(client, FARM_ID, koo) == 47


async def test_delete_event_reverses_stock(client, db_session):
    log, koo = await _setup(db_session)
    ev = (await post_event(client, log, event_type="death", species="cattle", category_id=koo, count=4)).json()
    assert await api_stock(client, FARM_ID, koo) == 46
    r = await client.delete(f"/api/events/{ev['id']}", headers=auth("admin"))
    assert r.status_code == 200
    assert await api_stock(client, FARM_ID, koo) == 50


async def test_data_entry_cannot_edit_locked_log(client, db_session):
    log, koo = await _setup(db_session)
    ev = (await post_event(client, log, event_type="sold", species="cattle", category_id=koo, count=1)).json()
    await lock_log(db_session, log)
    r = await client.put(f"/api/events/{ev['id']}", json={"count": 2}, headers=auth("data_entry"))
    assert r.status_code == 403
    assert await api_stock(client, FARM_ID, koo) == 49  # unchanged


async def test_admin_can_edit_locked_log(client, db_session):
    log, koo = await _setup(db_session)
    ev = (await post_event(client, log, event_type="sold", species="cattle", category_id=koo, count=1)).json()
    await lock_log(db_session, log)
    r = await client.put(f"/api/events/{ev['id']}", json={"count": 2}, headers=auth("admin"))
    assert r.status_code == 200
    assert await api_stock(client, FARM_ID, koo) == 48


async def test_viewer_cannot_create_event(client, db_session):
    log, koo = await _setup(db_session)
    body = dict(event_type="birth", species="cattle", category_id=koo, count=1)
    assert (await post_event(client, log, "viewer", **body)).status_code == 403
    # Route is admin-only: data_entry is rejected too.
    assert (await post_event(client, log, "data_entry", **body)).status_code == 403
    assert await api_stock(client, FARM_ID, koo) == 50


async def test_transfer_atomic(client, db_session):
    log, koo = await _setup(db_session)
    dest = await make_location(db_session, "Dest Farm")
    await make_stock(db_session, dest, CATTLE, koo, 5)
    r = await post_event(client, log, event_type="transfer", species="cattle", category_id=koo,
                         count=3, from_location_id=FARM_ID, to_location_id=dest)
    assert r.status_code == 200
    assert await api_stock(client, FARM_ID, koo) == 47
    assert await api_stock(client, dest, koo) == 8
