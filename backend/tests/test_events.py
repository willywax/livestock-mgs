from datetime import date

import pytest

from conftest import (
    FARM_ID, api_stock, auth, category_id, lock_log, make_daily_log,
    make_location, make_stock, post_event,
)
from models import Animal, AnimalAcquisitionType, AnimalSex, SpeciesType

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


async def test_manual_animal_transfer_writes_location_history(client, db_session):
    _, koo = await _setup(db_session)
    loc_b = await make_location(db_session, "Loc B")
    aid = await _mk_animal(client, "T-800", koo)
    r = await client.post(f"/api/animals/{aid}/transfer", headers=auth("admin"),
                          json={"to_location_id": loc_b, "transfer_date": "2026-05-12", "notes": "rotation"})
    assert r.status_code == 200
    hist = (await client.get(f"/api/animals/{aid}/location-history", headers=auth("viewer"))).json()
    assert len(hist) == 1
    assert hist[0]["from_location_id"] == FARM_ID and hist[0]["to_location_id"] == loc_b
    assert hist[0]["moved_date"] == "2026-05-12" and hist[0]["notes"] == "rotation"
    assert hist[0]["event_id"] is not None


async def test_edit_animal_location_writes_history_only_when_changed(client, db_session):
    _, koo = await _setup(db_session)
    loc_b = await make_location(db_session, "Loc B")
    aid = await _mk_animal(client, "T-900", koo)
    # same location: no history row
    r = await client.put(f"/api/animals/{aid}", json={"location_id": FARM_ID, "name": "Bella"},
                         headers=auth("admin"))
    assert r.status_code == 200
    assert (await client.get(f"/api/animals/{aid}/location-history", headers=auth("admin"))).json() == []
    # location omitted: no history row
    await client.put(f"/api/animals/{aid}", json={"name": "Bella2"}, headers=auth("admin"))
    assert (await client.get(f"/api/animals/{aid}/location-history", headers=auth("admin"))).json() == []
    # changed location: one row, no event
    r = await client.put(f"/api/animals/{aid}", json={"location_id": loc_b}, headers=auth("admin"))
    assert r.status_code == 200 and r.json()["location_id"] == loc_b
    hist = (await client.get(f"/api/animals/{aid}/location-history", headers=auth("admin"))).json()
    assert len(hist) == 1
    assert hist[0]["from_location_id"] == FARM_ID and hist[0]["to_location_id"] == loc_b
    assert hist[0]["event_id"] is None


async def test_create_daily_log_syncs_register_per_event(client, db_session):
    koo = await category_id(db_session, CATTLE)
    aid = await _mk_animal(client, "T-1000", koo)
    r = await client.post("/api/daily-logs", headers=auth("data_entry"), json={
        "location_id": FARM_ID, "log_date": "2024-02-02", "has_events": True,
        "events": [
            {"event_type": "death", "species": "cattle", "category_id": koo, "count": 1,
             "animal_tags": "T-1000"},
            {"event_type": "bought", "species": "cattle", "category_id": koo, "count": 1,
             "animal_tags": "NEW-LOG-1"},
            {"event_type": "death", "species": "cattle", "category_id": koo, "count": 1,
             "animal_tags": "NOPE-2"},
        ],
    })
    assert r.status_code == 200, r.text
    evs = r.json()["events"]
    assert evs[0]["sync_warnings"] is None and evs[1]["sync_warnings"] is None
    assert any("NOPE-2" in w for w in evs[2]["sync_warnings"])
    assert (await _animal(client, aid))["status"] == "dead"
    found = (await client.get("/api/animals?search=NEW-LOG-1", headers=auth("admin"))).json()
    assert len(found) == 1 and found[0]["status"] == "active"
    assert await api_stock(client, FARM_ID, koo) == 49  # 50 - 2 deaths + 1 bought


async def test_register_sync_failure_never_breaks_daily_log_save(client, db_session, monkeypatch):
    from services import animal_sync

    async def boom(*a, **k):
        raise RuntimeError("register exploded")

    monkeypatch.setattr(animal_sync, "_find_animal", boom)
    koo = await category_id(db_session, CATTLE)
    r = await client.post("/api/daily-logs", headers=auth("admin"), json={
        "location_id": FARM_ID, "log_date": "2024-03-03", "has_events": True,
        "events": [
            {"event_type": "death", "species": "cattle", "category_id": koo, "count": 1, "animal_tags": "A-1"},
            {"event_type": "death", "species": "cattle", "category_id": koo, "count": 1, "animal_tags": "A-2"},
        ],
    })
    assert r.status_code == 200, r.text
    evs = r.json()["events"]
    assert len(evs) == 2
    assert all(e["sync_warnings"] and "register could not be updated" in e["sync_warnings"][0] for e in evs)
    assert await api_stock(client, FARM_ID, koo) == 48  # stock committed regardless


# ---- temp tags ----------------------------------------------------------------

async def _mk_temp_animal(db, cat, tag="TEMP-TES-20260101-001", loc=FARM_ID, temp=True):
    a = Animal(tag_number=tag, species=CATTLE, category_id=cat, location_id=loc, sex=AnimalSex.FEMALE,
               acquisition_type=AnimalAcquisitionType.BORN, acquisition_date=date.today(), is_temp_tag=temp)
    db.add(a)
    await db.commit()
    return a.id


async def _all_animals(client, **params):
    r = await client.get("/api/animals", params=params, headers=auth("admin"))
    assert r.status_code == 200
    return r.json()


async def test_temp_tag_generated_for_empty_offspring(client, db_session):
    log, _ = await _setup(db_session)
    calf = await category_id(db_session, CATTLE, "Ndama Jike")
    r = await post_event(client, log, event_type="birth", species="cattle", category_id=calf,
                         count=3, offspring_tags="KK-001, , KK-003")
    assert r.status_code == 200 and not r.json()["sync_warnings"]
    animals = await _all_animals(client)
    by_tag = {a["tag_number"]: a for a in animals}
    assert by_tag["KK-001"]["is_temp_tag"] is False and by_tag["KK-003"]["is_temp_tag"] is False
    temps = [a for a in animals if a["is_temp_tag"]]
    assert len(temps) == 1
    assert temps[0]["tag_number"] == f"TEMP-TES-{date.today():%Y%m%d}-001"
    assert temps[0]["acquisition_type"] == "born" and temps[0]["sex"] == "female"


async def test_blank_offspring_creates_temp_animals_per_count(client, db_session):
    log, _ = await _setup(db_session)
    calf = await category_id(db_session, CATTLE, "Ndama Dume")
    r = await post_event(client, log, event_type="birth", species="cattle", category_id=calf, count=2)
    assert r.status_code == 200
    temps = await _all_animals(client, is_temp_tag="true")
    assert sorted(a["tag_number"] for a in temps) == [
        f"TEMP-TES-{date.today():%Y%m%d}-001", f"TEMP-TES-{date.today():%Y%m%d}-002",
    ]
    assert all(a["sex"] == "male" for a in temps)


async def test_resaving_birth_event_does_not_duplicate_temp_animals(client, db_session):
    log, _ = await _setup(db_session)
    calf = await category_id(db_session, CATTLE, "Ndama Jike")
    ev = (await post_event(client, log, event_type="birth", species="cattle", category_id=calf,
                           count=2, offspring_tags="KK-9, ")).json()
    assert len(await _all_animals(client, is_temp_tag="true")) == 1
    r = await client.put(f"/api/events/{ev['id']}", json={"notes": "edited"}, headers=auth("admin"))
    assert r.status_code == 200
    r = await client.put(f"/api/events/{ev['id']}", json={"notes": "edited again"}, headers=auth("admin"))
    assert r.status_code == 200
    assert len(await _all_animals(client, is_temp_tag="true")) == 1
    assert len(await _all_animals(client)) == 2


async def test_replace_tag_success(client, db_session):
    _, koo = await _setup(db_session)
    aid = await _mk_temp_animal(db_session, koo)
    r = await client.post(f"/api/animals/{aid}/replace-tag", json={"new_tag_number": " KK-001 "},
                          headers=auth("data_entry"))
    assert r.status_code == 200
    assert r.json() == {"message": "Tag replaced", "old_tag": "TEMP-TES-20260101-001",
                        "new_tag": "KK-001", "animal_id": aid}
    a = await _animal(client, aid)
    assert a["tag_number"] == "KK-001" and a["is_temp_tag"] is False


async def test_replace_tag_rejected_on_real_animal(client, db_session):
    _, koo = await _setup(db_session)
    aid = await _mk_animal(client, "REAL-1", koo)
    r = await client.post(f"/api/animals/{aid}/replace-tag", json={"new_tag_number": "KK-002"},
                          headers=auth("admin"))
    assert r.status_code == 400
    assert "does not have a temporary tag" in r.json()["detail"]
    assert (await _animal(client, aid))["tag_number"] == "REAL-1"


async def test_replace_tag_conflict_missing_and_viewer(client, db_session):
    _, koo = await _setup(db_session)
    await _mk_animal(client, "TAKEN-1", koo)
    aid = await _mk_temp_animal(db_session, koo)
    r = await client.post(f"/api/animals/{aid}/replace-tag", json={"new_tag_number": "TAKEN-1"},
                          headers=auth("admin"))
    assert r.status_code == 409
    assert (await _animal(client, aid))["is_temp_tag"] is True
    assert (await client.post("/api/animals/9999/replace-tag", json={"new_tag_number": "X"},
                              headers=auth("admin"))).status_code == 404
    assert (await client.post(f"/api/animals/{aid}/replace-tag", json={"new_tag_number": "OK-1"},
                              headers=auth("viewer"))).status_code == 403


async def test_list_animals_temp_filter(client, db_session):
    _, koo = await _setup(db_session)
    await _mk_temp_animal(db_session, koo, tag="TEMP-TES-20260101-001")
    await _mk_temp_animal(db_session, koo, tag="REAL-2", temp=False)
    only_temp = await _all_animals(client, is_temp_tag="true")
    only_real = await _all_animals(client, is_temp_tag="false")
    both = await _all_animals(client)
    assert [a["tag_number"] for a in only_temp] == ["TEMP-TES-20260101-001"]
    assert [a["tag_number"] for a in only_real] == ["REAL-2"]
    assert len(both) == 2


async def test_edit_abortion_event_stage_and_mother_tag(client, db_session):
    log, koo = await _setup(db_session)
    ev = (await post_event(client, log, event_type="abortion", species="cattle", count=1,
                           is_stock_event=False, abortion_stage="early")).json()
    r = await client.put(f"/api/events/{ev['id']}", json={"abortion_stage": "late", "mother_tag": "M-1"},
                         headers=auth("admin"))
    assert r.status_code == 200, r.text
    assert (r.json()["abortion_stage"], r.json()["mother_tag"]) == ("late", "M-1")


async def test_edit_event_rejects_fields_of_another_type_and_can_clear_text(client, db_session):
    log, koo = await _setup(db_session)
    ev = (await post_event(client, log, event_type="sold", species="cattle", category_id=koo, count=1,
                           buyer_name="Asha")).json()
    bad = await client.put(f"/api/events/{ev['id']}", json={"abortion_stage": "early"}, headers=auth("admin"))
    assert bad.status_code == 400
    ok = await client.put(f"/api/events/{ev['id']}", json={"buyer_name": ""}, headers=auth("admin"))
    assert ok.status_code == 200 and ok.json()["buyer_name"] == ""


async def test_edit_event_type_change_clears_old_fields_and_fixes_stock(client, db_session):
    log, koo = await _setup(db_session)
    ev = (await post_event(client, log, event_type="sold", species="cattle", category_id=koo, count=2,
                           buyer_name="Asha", sale_price=100)).json()
    assert await api_stock(client, FARM_ID, koo) == 48
    r = await client.put(f"/api/events/{ev['id']}",
                         json={"event_type": "death", "cause_of_death": "Disease", "days_sick": 3},
                         headers=auth("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_type"] == "death" and body["buyer_name"] is None and body["sale_price"] is None
    assert body["cause_of_death"] == "Disease" and body["days_sick"] == 3
    assert await api_stock(client, FARM_ID, koo) == 48  # sold -2 reversed, death -2 applied
    # Old-type fields sent with a type change are still rejected
    bad = await client.put(f"/api/events/{ev['id']}", json={"event_type": "birth", "buyer_name": "X"},
                           headers=auth("admin"))
    assert bad.status_code == 400
    # Changing to abortion makes it a non-stock event and restores stock
    to_abortion = await client.put(f"/api/events/{ev['id']}", json={"event_type": "abortion"}, headers=auth("admin"))
    assert to_abortion.status_code == 200 and to_abortion.json()["is_stock_event"] is False
    assert await api_stock(client, FARM_ID, koo) == 50
