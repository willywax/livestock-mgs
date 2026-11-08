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


# ---- animal register sync ----------------------------------------------------

async def _mk_animal(client, tag, cat, loc=FARM_ID, sex="female"):
    r = await client.post("/api/animals", json={
        "tag_number": tag, "species": "cattle", "category_id": cat, "location_id": loc,
        "sex": sex, "acquisition_type": "bought", "acquisition_date": "2024-01-01",
    }, headers=auth("admin"))
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _animal(client, animal_id):
    return (await client.get(f"/api/animals/{animal_id}", headers=auth("admin"))).json()


async def test_death_event_marks_animal_dead(client, db_session):
    log, koo = await _setup(db_session)
    aid = await _mk_animal(client, "T-100", koo)
    r = await post_event(client, log, event_type="death", species="cattle", category_id=koo,
                         count=1, animal_tags="T-100")
    assert r.status_code == 200
    assert (await _animal(client, aid))["status"] == "dead"
    assert await api_stock(client, FARM_ID, koo) == 49


async def test_transfer_event_updates_location(client, db_session):
    log, koo = await _setup(db_session)
    loc_b = await make_location(db_session, "Loc B")
    aid = await _mk_animal(client, "T-200", koo)
    r = await post_event(client, log, event_type="transfer", species="cattle", category_id=koo,
                         count=1, from_location_id=FARM_ID, to_location_id=loc_b, animal_tags="T-200")
    assert r.status_code == 200
    assert (await _animal(client, aid))["location_id"] == loc_b
    hist = (await client.get(f"/api/animals/{aid}/location-history", headers=auth("viewer"))).json()
    assert len(hist) == 1
    assert hist[0]["from_location_id"] == FARM_ID and hist[0]["to_location_id"] == loc_b
    assert hist[0]["event_id"] == r.json()["id"]
    assert hist[0]["to_location_name"] == "Loc B"


async def test_bought_event_creates_animal(client, db_session):
    log, koo = await _setup(db_session)
    r = await post_event(client, log, event_type="bought", species="cattle", category_id=koo,
                         count=1, animal_tags="NEW-1")
    assert r.status_code == 200
    found = (await client.get("/api/animals?search=NEW-1", headers=auth("admin"))).json()
    assert len(found) == 1
    assert found[0]["status"] == "active" and found[0]["location_id"] == FARM_ID
    assert found[0]["acquisition_type"] == "bought" and found[0]["sex"] == "female"


async def test_birth_event_creates_offspring(client, db_session):
    log, _ = await _setup(db_session)
    calf = await category_id(db_session, CATTLE, "Ndama Jike")
    r = await post_event(client, log, event_type="birth", species="cattle", category_id=calf,
                         count=1, offspring_tags="CALF-1")
    assert r.status_code == 200
    found = (await client.get("/api/animals?search=CALF-1", headers=auth("admin"))).json()
    assert len(found) == 1
    assert found[0]["acquisition_type"] == "born" and found[0]["sex"] == "female"
    assert found[0]["status"] == "active"


async def test_delete_death_event_restores_animal(client, db_session):
    log, koo = await _setup(db_session)
    aid = await _mk_animal(client, "T-300", koo)
    ev = (await post_event(client, log, event_type="death", species="cattle", category_id=koo,
                           count=1, animal_tags="T-300")).json()
    assert (await _animal(client, aid))["status"] == "dead"
    r = await client.delete(f"/api/events/{ev['id']}", headers=auth("admin"))
    assert r.status_code == 200
    assert (await _animal(client, aid))["status"] == "active"
    assert await api_stock(client, FARM_ID, koo) == 50


async def test_delete_transfer_event_moves_animal_back(client, db_session):
    log, koo = await _setup(db_session)
    loc_b = await make_location(db_session, "Loc B")
    aid = await _mk_animal(client, "T-400", koo)
    ev = (await post_event(client, log, event_type="transfer", species="cattle", category_id=koo,
                           count=1, from_location_id=FARM_ID, to_location_id=loc_b,
                           animal_tags="T-400")).json()
    assert (await _animal(client, aid))["location_id"] == loc_b
    assert (await client.delete(f"/api/events/{ev['id']}", headers=auth("admin"))).status_code == 200
    assert (await _animal(client, aid))["location_id"] == FARM_ID
    assert (await client.get(f"/api/animals/{aid}/location-history", headers=auth("admin"))).json() == []


async def test_edit_event_tags_reverses_old_and_applies_new(client, db_session):
    log, koo = await _setup(db_session)
    a1 = await _mk_animal(client, "T-501", koo)
    a2 = await _mk_animal(client, "T-502", koo)
    ev = (await post_event(client, log, event_type="death", species="cattle", category_id=koo,
                           count=1, animal_tags="T-501")).json()
    r = await client.put(f"/api/events/{ev['id']}", json={"animal_tags": "T-502"}, headers=auth("admin"))
    assert r.status_code == 200
    assert (await _animal(client, a1))["status"] == "active"
    assert (await _animal(client, a2))["status"] == "dead"
    assert await api_stock(client, FARM_ID, koo) == 49


async def test_bought_event_does_not_reactivate_dead_animal(client, db_session):
    log, koo = await _setup(db_session)
    aid = await _mk_animal(client, "T-600", koo)
    await post_event(client, log, event_type="death", species="cattle", category_id=koo,
                     count=1, animal_tags="T-600")
    r = await post_event(client, log, event_type="bought", species="cattle", category_id=koo,
                         count=1, animal_tags="T-600")
    assert r.status_code == 200
    assert (await _animal(client, aid))["status"] == "dead"
    assert any("not reactivated" in w for w in r.json()["sync_warnings"])


async def test_unknown_tag_on_death_warns_but_saves_stock(client, db_session):
    log, koo = await _setup(db_session)
    r = await post_event(client, log, event_type="death", species="cattle", category_id=koo,
                         count=1, animal_tags="NOPE-1")
    assert r.status_code == 200
    assert any("NOPE-1" in w for w in r.json()["sync_warnings"])
    assert await api_stock(client, FARM_ID, koo) == 49


async def test_reconciliation_counts_registered_vs_stock(client, db_session):
    _, koo = await _setup(db_session)
    await _mk_animal(client, "T-700", koo)
    r = await client.get("/api/animals/register-reconciliation", headers=auth("viewer"))
    assert r.status_code == 200
    row = next(x for x in r.json() if x["location_id"] == FARM_ID and x["species"] == "cattle")
    assert row["stock_count"] == 50 and row["registered_active"] == 1
    assert row["unregistered"] == 49 and row["registered_pct"] == 2.0
