"""Category transition rules, queue, confirm (animal + stock together) and the first-calving hook.
SQLite in-memory: Postgres enums, row locks and the savepoint race path are verified by reading code only."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

import server
from conftest import FARM_ID, auth, category_id, make_stock, stock_count
from models import (
    Animal, AnimalAcquisitionType, AnimalSex, AnimalStatus, CategoryTransition, CategoryTransitionRule,
    SpeciesType,
)

pytestmark = pytest.mark.asyncio
CATTLE = SpeciesType.CATTLE


async def seeded(db):
    await server._seed_category_transition_rules(db)


async def make_animal(db, tag, cat_name, sex, birth=None, status=AnimalStatus.ACTIVE):
    cat = await category_id(db, CATTLE, cat_name)
    animal = Animal(tag_number=tag, species=CATTLE, category_id=cat, location_id=FARM_ID, sex=sex,
                    acquisition_type=AnimalAcquisitionType.BORN, acquisition_date=date(2024, 1, 1),
                    birth_date=birth, status=status)
    db.add(animal)
    await db.commit()
    return animal.id, cat


def months_ago(n):
    return date.today() - timedelta(days=31 * n + 3)


async def test_seed_creates_rules_once(db_session):
    await seeded(db_session)
    first = (await db_session.execute(select(CategoryTransitionRule))).scalars().all()
    assert len(first) == 15  # 5 per species
    assert await server._seed_category_transition_rules(db_session) == 0  # idempotent


async def test_confirm_updates_category_and_moves_stock(client, db_session):
    await seeded(db_session)
    animal_id, old = await make_animal(db_session, "H-1", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19))
    new = await category_id(db_session, CATTLE, "Mitamba")
    await make_stock(db_session, FARM_ID, CATTLE, old, 3)
    await make_stock(db_session, FARM_ID, CATTLE, new, 2)

    r = await client.post(f"/api/animals/{animal_id}/confirm-transition",
                          json={"to_category_id": new, "notes": "aged"}, headers=auth("data_entry"))
    assert r.status_code == 200, r.text
    assert r.json()["from_category"] == "Achishwa Jike" and r.json()["to_category"] == "Mitamba"
    assert r.json()["trigger"] == "age_18m"
    db_session.expire_all()
    assert (await db_session.get(Animal, animal_id)).category_id == new
    assert await stock_count(db_session, FARM_ID, CATTLE, old) == 2
    assert await stock_count(db_session, FARM_ID, CATTLE, new) == 3
    history = (await client.get(f"/api/animals/{animal_id}/transition-history", headers=auth("viewer"))).json()
    assert len(history) == 1 and history[0]["tag_number"] == "H-1"


async def test_confirm_creates_missing_stock_row(client, db_session):
    animal_id, old = await make_animal(db_session, "H-2", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19))
    new = await category_id(db_session, CATTLE, "Mitamba")
    await make_stock(db_session, FARM_ID, CATTLE, old, 1)
    r = await client.post(f"/api/animals/{animal_id}/confirm-transition",
                          json={"to_category_id": new}, headers=auth("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["trigger"] == "manual"  # rules were not seeded here
    db_session.expire_all()
    assert await stock_count(db_session, FARM_ID, CATTLE, new) == 1
    assert await stock_count(db_session, FARM_ID, CATTLE, old) == 0


async def test_duplicate_confirm_is_400(client, db_session):
    animal_id, old = await make_animal(db_session, "H-3", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19))
    new = await category_id(db_session, CATTLE, "Mitamba")
    await make_stock(db_session, FARM_ID, CATTLE, old, 2)
    body = {"to_category_id": new}
    assert (await client.post(f"/api/animals/{animal_id}/confirm-transition", json=body, headers=auth("admin"))).status_code == 200
    again = await client.post(f"/api/animals/{animal_id}/confirm-transition", json=body, headers=auth("admin"))
    assert again.status_code == 400
    db_session.expire_all()
    assert await stock_count(db_session, FARM_ID, CATTLE, new) == 1  # not counted twice


async def test_zero_source_stock_is_409_and_changes_nothing(client, db_session):
    animal_id, old = await make_animal(db_session, "H-4", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19))
    new = await category_id(db_session, CATTLE, "Mitamba")
    await make_stock(db_session, FARM_ID, CATTLE, old, 0)
    r = await client.post(f"/api/animals/{animal_id}/confirm-transition",
                          json={"to_category_id": new}, headers=auth("admin"))
    assert r.status_code == 409
    db_session.expire_all()
    assert (await db_session.get(Animal, animal_id)).category_id == old
    assert (await db_session.execute(select(CategoryTransition))).scalars().all() == []


async def test_roles(client, db_session):
    animal_id, old = await make_animal(db_session, "H-5", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19))
    new = await category_id(db_session, CATTLE, "Mitamba")
    body = {"to_category_id": new}
    assert (await client.post(f"/api/animals/{animal_id}/confirm-transition", json=body, headers=auth("viewer"))).status_code == 403
    assert (await client.get("/api/animals/transition-queue", headers=auth("viewer"))).status_code == 200
    assert (await client.get("/api/animals/transition-queue")).status_code == 403
    assert (await client.post("/api/admin/tasks/sync-category-transitions", headers=auth("data_entry"))).status_code == 403


async def test_queue_lists_animals_past_threshold_only(client, db_session):
    await seeded(db_session)
    due, _ = await make_animal(db_session, "Q-DUE", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19))
    await make_animal(db_session, "Q-YOUNG", "Achishwa Jike", AnimalSex.FEMALE, months_ago(10))
    await make_animal(db_session, "Q-NODOB", "Achishwa Jike", AnimalSex.FEMALE, None)
    await make_animal(db_session, "Q-SOLD", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19), AnimalStatus.SOLD)
    male, _ = await make_animal(db_session, "Q-MALE", "Achishwa Dume", AnimalSex.MALE, months_ago(20))

    for r in (await client.get("/api/animals/transition-queue?species=cattle", headers=auth("viewer")),
              await client.post("/api/admin/tasks/sync-category-transitions", headers=auth("admin"))):
        assert r.status_code == 200, r.text
        items = {i["tag_number"]: i for i in r.json()["pending"]}
        assert set(items) == {"Q-DUE", "Q-MALE"} and r.json()["total"] == 2
        assert items["Q-DUE"]["to_category"] == "Mitamba" and items["Q-MALE"]["to_category"] == "Dume Wadogo"
    # read-only: nothing was moved
    db_session.expire_all()
    assert (await db_session.get(Animal, due)).category_id != await category_id(db_session, CATTLE, "Mitamba")


async def test_bulk_confirm_reports_each_animal(client, db_session):
    good, old = await make_animal(db_session, "B-1", "Achishwa Jike", AnimalSex.FEMALE, months_ago(19))
    new = await category_id(db_session, CATTLE, "Mitamba")
    await make_stock(db_session, FARM_ID, CATTLE, old, 1)
    r = await client.post("/api/animals/bulk-confirm-transitions", headers=auth("admin"), json={
        "transitions": [{"animal_id": good, "to_category_id": new}, {"animal_id": 99999, "to_category_id": new}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["succeeded"], body["failed"]) == (1, 1)
    assert body["results"][0]["success"] and not body["results"][1]["success"]
    db_session.expire_all()
    assert (await db_session.get(Animal, good)).category_id == new


async def test_rule_update_validation(client, db_session):
    await seeded(db_session)
    rules = (await client.get("/api/admin/transition-rules", headers=auth("viewer"))).json()
    age_rule = next(r for r in rules if r["trigger_type"] == "age")
    event_rule = next(r for r in rules if r["trigger_type"] == "event")
    ok = await client.put(f"/api/admin/transition-rules/{age_rule['id']}", json={"trigger_age_months": 9}, headers=auth("admin"))
    assert ok.status_code == 200 and ok.json()["trigger_age_months"] == 9
    assert (await client.put(f"/api/admin/transition-rules/{event_rule['id']}", json={"trigger_age_months": 9}, headers=auth("admin"))).status_code == 400
    assert (await client.put(f"/api/admin/transition-rules/{age_rule['id']}", json={"is_active": False}, headers=auth("data_entry"))).status_code == 403
    sheep_cat = await category_id(db_session, SpeciesType.SHEEP, "Koo")
    wrong = await client.put(f"/api/admin/transition-rules/{age_rule['id']}", json={"to_category_id_f": sheep_cat}, headers=auth("admin"))
    assert wrong.status_code == 400  # category of another species


async def test_calving_hook_moves_heifer_to_cow_once(client, db_session):
    await seeded(db_session)
    animal_id, heifer = await make_animal(db_session, "C-1", "Mitamba", AnimalSex.FEMALE, months_ago(30))
    cow = await category_id(db_session, CATTLE, "Koo")
    await make_stock(db_session, FARM_ID, CATTLE, heifer, 2)
    await make_stock(db_session, FARM_ID, CATTLE, cow, 5)

    r = await client.post(f"/api/animals/{animal_id}/reproductive-events", headers=auth("data_entry"),
                          json={"event_type": "calving", "event_date": "2026-06-01", "calving_outcome": "live"})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert (await db_session.get(Animal, animal_id)).category_id == cow
    assert await stock_count(db_session, FARM_ID, CATTLE, heifer) == 1
    assert await stock_count(db_session, FARM_ID, CATTLE, cow) == 6
    log = (await db_session.execute(select(CategoryTransition))).scalars().all()
    assert len(log) == 1 and log[0].trigger == "first_calving" and log[0].confirmed_by == 2

    # second calving: already a cow, no further transition and no stock change
    again = await client.post(f"/api/animals/{animal_id}/reproductive-events", headers=auth("data_entry"),
                              json={"event_type": "calving", "event_date": "2027-06-01", "calving_outcome": "live"})
    assert again.status_code == 200
    db_session.expire_all()
    assert await stock_count(db_session, FARM_ID, CATTLE, cow) == 6
    assert len((await db_session.execute(select(CategoryTransition))).scalars().all()) == 1


async def test_calving_hook_failure_never_blocks_the_calving_record(client, db_session):
    await seeded(db_session)
    animal_id, heifer = await make_animal(db_session, "C-2", "Mitamba", AnimalSex.FEMALE, months_ago(30))
    await make_stock(db_session, FARM_ID, CATTLE, heifer, 0)  # stock cannot cover the move
    r = await client.post(f"/api/animals/{animal_id}/reproductive-events", headers=auth("admin"),
                          json={"event_type": "calving", "event_date": "2026-06-01", "calving_outcome": "live"})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    animal = await db_session.get(Animal, animal_id)
    assert animal.category_id == heifer and str(animal.last_calving_date) == "2026-06-01"
