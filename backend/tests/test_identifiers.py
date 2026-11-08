"""Identifier API tests using the shared in-memory SQLite fixtures only."""
from datetime import date, datetime, timezone
import csv
import io

import pytest
from sqlalchemy import select, func

from conftest import FARM_ID, USER_IDS, auth, category_id, make_location
from models import Animal, AnimalAcquisitionType, AnimalIdentifier, AnimalSex, AnimalStatus, SpeciesType

pytestmark = pytest.mark.asyncio
LOOKUP = "/api/animals/lookup-by-id"


async def make_animal(db, tag="PRIMARY-1"):
    animal = Animal(
        tag_number=tag, species=SpeciesType.CATTLE,
        category_id=await category_id(db, SpeciesType.CATTLE), location_id=FARM_ID,
        sex=AnimalSex.FEMALE, acquisition_type=AnimalAcquisitionType.BORN,
        acquisition_date=date(2022, 1, 1), status=AnimalStatus.ACTIVE,
    )
    db.add(animal)
    await db.commit()
    return animal.id


async def create(client, animal_id, value="901020000131504", kind="eid", **extra):
    return await client.post(
        f"/api/animals/{animal_id}/identifiers", headers=auth("data_entry"),
        json={"id_type": kind, "id_value": value, **extra},
    )


async def lookup(client, value="901020000131504", kind="eid"):
    return await client.get(LOOKUP, params={"id_type": kind, "id_value": value}, headers=auth("viewer"))


async def test_crud_and_primary_tag_preserved(client, db_session):
    animal_id = await make_animal(db_session)
    url = f"/api/animals/{animal_id}/identifiers"
    assert (await client.get(url, headers=auth("viewer"))).json() == []
    response = await create(client, animal_id, notes="Original tag", recorded_date="2026-01-01")
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["is_active"] is True and item["created_at"]
    assert (await db_session.get(AnimalIdentifier, item["id"])).created_by == USER_IDS["data_entry"]
    assert (await client.get(url, headers=auth("viewer"))).json() == [item]
    item_url = f"{url}/{item['id']}"
    response = await client.put(item_url, json={"is_active": False}, headers=auth("data_entry"))
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert response.json()["notes"] == "Original tag"
    assert (await lookup(client)).status_code == 404
    response = await client.put(item_url, json={"id_value": "NEW-ID", "notes": None, "recorded_date": None},
                                headers=auth("admin"))
    assert response.status_code == 200
    assert response.json()["notes"] is None and response.json()["recorded_date"] is None
    assert response.json()["id_value"] == "NEW-ID"
    assert (await client.delete(item_url, headers=auth("data_entry"))).status_code == 200
    assert (await client.get(url, headers=auth("viewer"))).json() == []
    animal = await db_session.get(Animal, animal_id)
    await db_session.refresh(animal)
    assert animal.tag_number == "PRIMARY-1" and animal.registry_tag_id is None


async def test_duplicates_on_create_and_update(client, db_session):
    animal_id = await make_animal(db_session)
    first = (await create(client, animal_id)).json()
    second = (await create(client, animal_id, value="SECOND")).json()
    assert (await create(client, animal_id)).status_code == 409
    response = await client.put(f"/api/animals/{animal_id}/identifiers/{second['id']}",
                                json={"id_value": first["id_value"]}, headers=auth("admin"))
    assert response.status_code == 409
    assert (await lookup(client, value="SECOND")).status_code == 200
    assert (await create(client, animal_id, value="THIRD")).status_code == 200


@pytest.mark.parametrize("kind,value", [("eid", "901020000131504"), ("reader_code", "E144001234ABCD")])
async def test_lookup_existing_and_unknown(client, db_session, kind, value):
    animal_id = await make_animal(db_session)
    item = (await create(client, animal_id, value=value, kind=kind)).json()
    response = await lookup(client, value, kind)
    assert response.status_code == 200, response.text
    assert response.json()["animal"]["id"] == animal_id
    assert response.json()["animal"]["tag_number"] == "PRIMARY-1"
    assert response.json()["matched_id"] == item
    assert (await lookup(client, "unknown", kind)).status_code == 404


async def test_lookup_ambiguous_and_inactive(client, db_session):
    first = await make_animal(db_session)
    second = await make_animal(db_session, "PRIMARY-2")
    assert (await create(client, first)).status_code == 200
    response = await create(client, second)
    assert response.status_code == 200  # The uniqueness constraint is per animal.
    identifier_id = response.json()["id"]
    assert (await lookup(client)).status_code == 409
    await client.put(f"/api/animals/{second}/identifiers/{identifier_id}",
                     json={"is_active": False}, headers=auth("admin"))
    assert (await lookup(client)).json()["animal"]["id"] == first


async def test_ordering_and_all_types(client, db_session):
    animal_id = await make_animal(db_session)
    for kind in ("other", "branding_mark", "visual_tag", "reader_code", "uhf_tag", "eid"):
        assert (await create(client, animal_id, value=kind, kind=kind)).status_code == 200
    older = (await create(client, animal_id, value="older-eid")).json()
    record = await db_session.get(AnimalIdentifier, older["id"])
    record.created_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    await db_session.commit()
    items = (await client.get(f"/api/animals/{animal_id}/identifiers", headers=auth("viewer"))).json()
    assert [item["id_type"] for item in items] == sorted(item["id_type"] for item in items)
    assert [item["id_value"] for item in items if item["id_type"] == "eid"] == ["older-eid", "eid"]


async def test_missing_and_cross_animal_records(client, db_session):
    first = await make_animal(db_session)
    second = await make_animal(db_session, "PRIMARY-2")
    item = (await create(client, first)).json()
    assert (await create(client, 999)).status_code == 404
    assert (await client.get("/api/animals/999/identifiers", headers=auth("viewer"))).status_code == 404
    for animal_id, identifier_id in ((second, item["id"]), (first, 999), (999, item["id"])):
        url = f"/api/animals/{animal_id}/identifiers/{identifier_id}"
        assert (await client.put(url, json={"notes": "wrong"}, headers=auth("admin"))).status_code == 404
        assert (await client.delete(url, headers=auth("admin"))).status_code == 404
    assert (await lookup(client)).status_code == 200


async def test_permissions(client, db_session):
    animal_id = await make_animal(db_session)
    item = (await create(client, animal_id)).json()
    url = f"/api/animals/{animal_id}/identifiers"
    item_url = f"{url}/{item['id']}"
    for role in ("admin", "data_entry", "viewer"):
        assert (await client.get(url, headers=auth(role))).status_code == 200
        assert (await client.get(LOOKUP, params={"id_type": "eid", "id_value": item["id_value"]},
                                 headers=auth(role))).status_code == 200
    for headers in ({}, auth("viewer")):
        assert (await client.post(url, json={"id_type": "eid", "id_value": "x"}, headers=headers)).status_code == 403
        assert (await client.put(item_url, json={"notes": "x"}, headers=headers)).status_code == 403
        assert (await client.delete(item_url, headers=headers)).status_code == 403
    assert (await client.get(url)).status_code == 403
    assert (await client.get(LOOKUP, params={"id_type": "eid", "id_value": "x"})).status_code == 403


async def test_input_validation(client, db_session):
    animal_id = await make_animal(db_session)
    item = (await create(client, animal_id)).json()
    for value in ("", "x" * 101, None):
        assert (await create(client, animal_id, value=value)).status_code == 422
        assert (await client.put(f"/api/animals/{animal_id}/identifiers/{item['id']}",
                                 json={"id_value": value}, headers=auth("admin"))).status_code == 422
    assert (await create(client, animal_id, kind="unknown")).status_code == 422
    assert (await client.put(f"/api/animals/{animal_id}/identifiers/{item['id']}",
                             json={"is_active": None}, headers=auth("admin"))).status_code == 422


IMPORT_URL = "/api/admin/import/animal-identifiers"
CSV_FIELDS = ["eid", "eid_short", "reader_code", "species", "farm"] + [
    f"tag_{i}{suffix}" for i in range(1, 5) for suffix in ("_type", "")
]


def baseline_csv(*rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({"species": "cattle", "farm": "Test Farm", **row})
    return stream.getvalue().encode("utf-8-sig")


async def import_csv(client, content, role="admin", filename="baseline.csv"):
    return await client.post(IMPORT_URL, files={"file": (filename, content, "text/csv")},
                             headers=auth(role) if role else {})


async def test_import_mappings_repeat_and_inactive(client, db_session):
    animal_id = await make_animal(db_session, "008")
    content = baseline_csv({"eid": " 001234567890123 ", "eid_short": "00123", "reader_code": "E144ABCD",
                            "tag_1_type": "Ear tag", "tag_1": "008", "tag_2_type": "UHF ear tag", "tag_2": "009",
                            "tag_3_type": "Ear tag", "tag_3": "SECOND", "tag_4_type": "Other", "tag_4": "MARK"})
    response = await import_csv(client, content)
    assert response.status_code == 200, response.text
    assert response.json() == {"matched": 1, "identifiers_added": 5, "already_existed": 0, "unmatched_eids": []}
    records = (await db_session.execute(select(AnimalIdentifier))).scalars().all()
    assert {(r.id_type.value, r.id_value) for r in records} == {
        ("eid", "001234567890123"), ("reader_code", "E144ABCD"), ("uhf_tag", "009"),
        ("visual_tag", "SECOND"), ("other", "MARK"),
    }
    assert all(r.created_by == USER_IDS["admin"] for r in records)
    record_id = records[0].id
    records[0].is_active = False
    await db_session.commit()
    response = await import_csv(client, content)
    assert response.json() == {"matched": 1, "identifiers_added": 0, "already_existed": 5, "unmatched_eids": []}
    await db_session.refresh(records[0])
    assert (await db_session.get(AnimalIdentifier, record_id)).is_active is False
    assert (await db_session.get(Animal, animal_id)).tag_number == "008"


async def test_import_fallback_scoping_and_unmatched(client, db_session):
    first = await make_animal(db_session, "008")
    other_location = await make_location(db_session, "Other Farm")
    second = await make_animal(db_session, "SECOND")
    animal = await db_session.get(Animal, second)
    animal.location_id = other_location
    animal.tag_number = "008"
    await db_session.commit()
    content = baseline_csv(
        {"eid": "E1", "eid_short": "1", "tag_1": "unknown", "tag_2": "008", "tag_3_type": "unsupported", "tag_3": "ignored"},
        {"eid": "E2", "eid_short": "2", "tag_1": "008", "farm": "Other Farm"},
        {"eid": "E3", "eid_short": "003", "tag_1": "008", "farm": ""},
        {"eid": "E4", "eid_short": "004", "tag_1": "missing"},
        {"eid": "E5", "eid_short": "005", "tag_1": "008", "species": "goat"},
    )
    response = await import_csv(client, content)
    assert response.status_code == 200, response.text
    assert response.json() == {"matched": 2, "identifiers_added": 2, "already_existed": 0,
                               "unmatched_eids": ["003", "004", "005"]}
    assert (await lookup(client, "E1")).json()["animal"]["id"] == first
    assert (await lookup(client, "E2")).json()["animal"]["id"] == second
    assert (await db_session.execute(select(func.count(Animal.id)))).scalar_one() == 2


@pytest.mark.parametrize("failure", ["length", "columns", "encoding", "quotes", "species"])
async def test_import_rolls_back_invalid_csv(client, db_session, failure):
    await make_animal(db_session)
    first = {"eid": "VALID", "tag_1": "PRIMARY-1"}
    if failure == "length":
        content = baseline_csv(first, {"eid": "x" * 101, "tag_1": "PRIMARY-1"})
    elif failure == "species":
        content = baseline_csv(first, {"eid": "BAD", "tag_1": "PRIMARY-1", "species": "invalid"})
    else:
        tail = {"columns": b"too,few\n", "encoding": b"\xff", "quotes": b'"unterminated'}[failure]
        content = baseline_csv(first) + tail
    response = await import_csv(client, content)
    assert response.status_code == 400, response.text
    assert (await db_session.execute(select(func.count(AnimalIdentifier.id)))).scalar_one() == 0


async def test_import_permissions_and_file_validation(client):
    content = baseline_csv()
    for role in (None, "viewer", "data_entry"):
        assert (await import_csv(client, content, role=role)).status_code == 403
    assert (await import_csv(client, content, filename="baseline.txt")).status_code == 400
    assert (await import_csv(client, b"wrong,headers\n")).status_code == 400
