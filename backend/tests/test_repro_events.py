"""Standalone reproduction: in-process ASGI requests and in-memory SQLite only."""
import csv
import io
from datetime import date, timedelta

import pytest
from sqlalchemy import select, func

from conftest import FARM_ID, USER_IDS, auth, category_id, make_location
from models import Animal, AnimalAcquisitionType, AnimalSex, SpeciesType, ReproductiveCycle

pytestmark = pytest.mark.asyncio


async def animal(db, tag="COW", **values):
    species = values.pop("species", SpeciesType.CATTLE)
    record = Animal(tag_number=tag, species=species, category_id=await category_id(db, species),
                    location_id=values.pop("location_id", FARM_ID),
                    sex=values.pop("sex", AnimalSex.FEMALE), acquisition_type=AnimalAcquisitionType.BORN,
                    acquisition_date=date(2020, 1, 1), **values)
    db.add(record)
    await db.commit()
    return record.id


async def event(client, animal_id, kind, **values):
    response = await client.post(f"/api/animals/{animal_id}/reproductive-events", headers=auth("data_entry"),
                                 json={"event_type": kind, "event_date": "2026-01-01", **values})
    assert response.status_code == 200, response.text
    return response.json()


async def summary(client, animal_id):
    response = await client.get(f"/api/animals/{animal_id}/reproductive-summary", headers=auth("viewer"))
    assert response.status_code == 200, response.text
    return response.json()


async def test_service_pd_and_calving(client, db_session):
    cow = await animal(db_session)
    bull = await animal(db_session, "BULL", sex=AnimalSex.MALE)
    saved = await event(client, cow, "service", service_type="natural", bull_animal_id=bull)
    assert saved["recorded_by"] == USER_IDS["data_entry"] and saved["recorded_at"]
    assert (await summary(client, cow))["services_without_conception"] == 1
    await event(client, cow, "pd_test", pd_result="pregnant", months_pregnant=4)
    state = await summary(client, cow)
    assert (state["status"], state["months_pregnant"], state["services_without_conception"]) == ("pregnant", 4, 0)
    assert state["last_pd_date"] == "2026-01-01"
    listed = await client.get("/api/animals", headers=auth("viewer"))
    assert next(row for row in listed.json() if row["id"] == cow)["reproductive_status"] == "pregnant"
    await event(client, cow, "calving", event_date="2026-06-01", calving_outcome="live", offspring_count=1)
    state = await summary(client, cow)
    assert (state["status"], state["months_pregnant"], state["last_calving_date"]) == ("open", None, "2026-06-01")
    assert state["services_without_conception"] == 0
    assert (await db_session.scalar(select(func.count()).select_from(ReproductiveCycle))) == 0


async def test_open_recheck_abortion_and_history(client, db_session):
    cow = await animal(db_session, services_without_conception=2, reproductive_status="pregnant", months_pregnant=3)
    await event(client, cow, "abortion", abortion_stage="early")
    state = await summary(client, cow)
    assert (state["status"], state["months_pregnant"], state["services_without_conception"]) == ("open", None, 2)
    assert state["last_calving_date"] is None
    for day, result in enumerate(["pregnant", "open", "recheck", "pregnant", "recheck"], 2):
        saved = await event(client, cow, "pd_test", event_date=f"2026-01-{day:02}", pd_result=result)
        assert saved["pd_result"] == result
    state = await summary(client, cow)
    assert state["status"] == "open" and len(state["events"]) == 5
    response = await client.get(f"/api/animals/{cow}/reproductive-events", headers=auth("viewer"))
    dates = [item["event_date"] for item in response.json()]
    assert len(dates) == 6 and dates == sorted(dates, reverse=True)


async def test_repeat_breeders_filters(client, db_session):
    cow = await animal(db_session, services_without_conception=3)
    await animal(db_session, "LOW", services_without_conception=2)
    await animal(db_session, "MALE", sex=AnimalSex.MALE, services_without_conception=5)
    other = await make_location(db_session, "Other")
    await animal(db_session, "SHEEP", species=SpeciesType.SHEEP, location_id=other, services_without_conception=4)
    url = "/api/animals/repeat-breeders"
    response = await client.get(url, headers=auth("viewer"))
    assert [row["tag_number"] for row in response.json()] == ["SHEEP", "COW"]
    response = await client.get(url, params={"location_id": FARM_ID, "species": "cattle"}, headers=auth("viewer"))
    assert [row["tag_number"] for row in response.json()] == ["COW"]
    assert response.json()[0]["location_name"] == "Test Farm"
    assert (await summary(client, cow))["is_repeat_breeder"] is True


async def test_age_sync_requires_birth_date_and_respects_status(client, db_session):
    today = date.today()
    mature = today.replace(year=today.year - 2)
    ids = [await animal(db_session, "MATURE", birth_date=mature),
           await animal(db_session, "YOUNG", birth_date=mature + timedelta(days=1)),
           await animal(db_session, "UNDATED"),
           await animal(db_session, "MALE", birth_date=mature, sex=AnimalSex.MALE),
           await animal(db_session, "PREGNANT", birth_date=mature, reproductive_status="pregnant"),
           await animal(db_session, "GOAT", birth_date=mature, species=SpeciesType.GOAT)]
    url = "/api/admin/tasks/sync-reproductive-status"
    response = await client.post(url, headers=auth("admin"))
    assert response.json() == {"updated": 2}
    assert [(await summary(client, i))["status"] for i in ids] == ["open", "unknown", "unknown", "unknown", "pregnant", "open"]
    assert (await client.post(url, headers=auth("admin"))).json() == {"updated": 0}
    for role in ("viewer", "data_entry"):
        assert (await client.post(url, headers=auth(role))).status_code == 403


async def test_permissions_missing_references_and_validation(client, db_session):
    cow = await animal(db_session)
    body = {"event_type": "service", "event_date": "2026-01-01"}
    url = f"/api/animals/{cow}/reproductive-events"
    for headers in ({}, auth("viewer")):
        assert (await client.post(url, headers=headers, json=body)).status_code == 403
    assert (await client.post(url, headers=auth("admin"), json={**body, "bull_animal_id": 999})).status_code == 404
    assert (await client.post(url, headers=auth("admin"), json={**body, "months_pregnant": -1})).status_code == 422
    assert (await client.post("/api/animals/999/reproductive-events", headers=auth("admin"), json=body)).status_code == 404
    for suffix in ("reproductive-events", "reproductive-summary"):
        assert (await client.get(f"/api/animals/999/{suffix}", headers=auth("admin"))).status_code == 404
        assert (await client.get(f"/api/animals/{cow}/{suffix}")).status_code == 403


async def test_cycle_calving_synchronizes_and_unrelated_edits_do_not_reset(client, db_session):
    cow = await animal(db_session, reproductive_status="pregnant", months_pregnant=8, services_without_conception=3)
    response = await client.post("/api/reproductive-cycles", headers=auth("admin"),
                                 json={"animal_id": cow, "actual_calving_date": "2026-01-01"})
    assert response.status_code == 200, response.text
    state = await summary(client, cow)
    assert state["last_calving_date"] == "2026-01-01" and state["services_without_conception"] == 0
    await event(client, cow, "service")
    url = f"/api/reproductive-cycles/{response.json()['id']}"
    response = await client.put(url, headers=auth("admin"), json={"notes": "Edited"})
    assert response.status_code == 200, response.text
    assert (await summary(client, cow))["services_without_conception"] == 1
    response = await client.put(url, headers=auth("admin"), json={"actual_calving_date": "2026-02-01"})
    assert response.status_code == 200, response.text
    state = await summary(client, cow)
    assert state["last_calving_date"] == "2026-02-01" and state["services_without_conception"] == 0


async def test_csv_reproductive_baseline_and_rollback(client, db_session):
    ids = [await animal(db_session, tag) for tag in ("YES", "NO", "UNKNOWN")]
    fields = ["eid", "eid_short", "reader_code", "species", "farm", "pregnancy", "months_pregnant", "last_calving"]
    fields += [f"tag_{i}{suffix}" for i in range(1, 5) for suffix in ("", "_type")]

    async def upload(rows):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return await client.post("/api/admin/import/animal-identifiers", headers=auth("admin"),
                                 files={"file": ("baseline.csv", stream.getvalue(), "text/csv")})

    response = await upload([
        {"tag_1": "YES", "pregnancy": "yEs", "months_pregnant": "4", "last_calving": "2025-01-01"},
        {"tag_1": "NO", "pregnancy": "No", "last_calving": "01/02/2025"},
        {"tag_1": "UNKNOWN", "pregnancy": ""},
    ])
    assert response.status_code == 200, response.text
    states = [await summary(client, i) for i in ids]
    assert [s["status"] for s in states] == ["pregnant", "open", "unknown"]
    assert states[0]["months_pregnant"] == 4 and states[0]["last_calving_date"] == "2025-01-01"
    assert states[1]["last_calving_date"] == "2025-02-01"
    assert response.json()["repro_fields_updated"] == 2
    # Bad reproductive values are skipped without failing the import; tag_3 is a valid match.
    response = await upload([{"tag_1": "x", "tag_3": "YES", "pregnancy": "yes", "months_pregnant": "abc"},
                             {"tag_1": "NO", "last_calving": "invalid"}])
    assert response.status_code == 200, response.text
    assert response.json()["matched"] == 2 and response.json()["repro_fields_updated"] == 1
    state = await summary(client, ids[0])
    assert state["status"] == "pregnant" and state["months_pregnant"] is None
    assert (await summary(client, ids[1]))["last_calving_date"] == "2025-02-01"
