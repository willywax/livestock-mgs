"""Physical reconciliation tests: in-memory SQLite and ASGI transport only."""
from datetime import date

import pytest
from sqlalchemy import select, func

from conftest import FARM_ID, auth, category_id, make_location
from models import (
    Animal, AnimalAcquisitionType, AnimalIdentifier, AnimalIdentifierType,
    AnimalSex, AnimalStatus, SpeciesType, ReconciliationSession,
)

pytestmark = pytest.mark.asyncio
URL = "/api/reconciliation/sessions"


async def animal(db, tag, location=FARM_ID, status=AnimalStatus.ACTIVE):
    row = Animal(
        tag_number=tag, species=SpeciesType.CATTLE,
        category_id=await category_id(db, SpeciesType.CATTLE), location_id=location,
        sex=AnimalSex.FEMALE, acquisition_type=AnimalAcquisitionType.BORN,
        acquisition_date=date(2024, 1, 1), status=status,
    )
    db.add(row)
    await db.commit()
    return row.id


async def identifier(db, animal_id, value, kind=AnimalIdentifierType.EID, active=True):
    db.add(AnimalIdentifier(animal_id=animal_id, id_type=kind, id_value=value, is_active=active))
    await db.commit()


def body(entries=(), input_type="mixed", **kwargs):
    return dict(location_id=FARM_ID, session_date="2026-11-09", input_type=input_type,
                entries=[dict(raw_value=v, id_type=t) for v, t in entries], **kwargs)


async def test_buckets_and_duplicate_scans(client, db_session):
    known = await animal(db_session, "KNOWN")
    missing = await animal(db_session, "MISSING")
    await animal(db_session, "DEAD", status=AnimalStatus.DEAD)
    other = await make_location(db_session, "Other Farm")
    await animal(db_session, "ELSEWHERE", location=other)
    await identifier(db_session, known, "00123")
    await identifier(db_session, known, "RETIRED", active=False)
    response = await client.post(URL, headers=auth("data_entry"), json=body([
        ("00123", "eid"), ("KNOWN", "visual_tag"), ("UNKNOWN", "reader_code"), ("RETIRED", "eid"),
    ]))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total_scanned"] == 4 and result["matched_count"] == 1
    assert result["matched"] == [dict(animal_id=known, tag_number="KNOWN", species="cattle", matched_via="identifier")]
    assert [a["animal_id"] for a in result["in_system_not_seen"]] == [missing]
    assert result["unmatched_scan_count"] == 2 and result["coverage_pct"] == 50.0
    assert [a["raw_value"] for a in result["unmatched_scan"]] == ["UNKNOWN", "RETIRED"]


async def test_visual_fallback_and_identifier_precedence(client, db_session):
    fallback = await animal(db_session, "VISUAL")
    preferred = await animal(db_session, "PRIMARY")
    response = await client.post(URL, headers=auth("admin"), json=body([("VISUAL", "visual_tag")], "visual"))
    assert response.json()["matched"][0]["matched_via"] == "tag_number"
    assert response.json()["matched"][0]["animal_id"] == fallback
    await identifier(db_session, preferred, "VISUAL", AnimalIdentifierType.VISUAL_TAG)
    response = await client.post(URL, headers=auth("admin"), json=body([("VISUAL", "visual_tag")], "visual"))
    assert response.json()["matched"][0]["animal_id"] == preferred


async def test_list_detail_filters_and_access(client, db_session):
    created = await client.post(URL, headers=auth("admin"), json=body())
    result = created.json()
    assert result["coverage_pct"] == 0.0
    sid = result["session_id"]
    detail = await client.get(f"{URL}/{sid}", headers=auth("viewer"))
    assert detail.json() == result
    listing = await client.get(URL, headers=auth("viewer"), params={"location_id": FARM_ID, "date_from": "2026-11-09", "date_to": "2026-11-09"})
    assert listing.status_code == 200 and listing.json()[0]["id"] == sid
    assert "matched" not in listing.json()[0]
    for params in ({"location_id": 999}, {"date_from": "2026-11-10"}, {"date_to": "2026-11-08"}):
        assert (await client.get(URL, headers=auth("viewer"), params=params)).json() == []
    assert (await client.post(URL, json=body())).status_code == 403
    assert (await client.post(URL, headers=auth("viewer"), json=body())).status_code == 403
    assert (await client.get(f"{URL}/99999", headers=auth("viewer"))).status_code == 404
    invalid = body()
    invalid["location_id"] = 99999
    assert (await client.post(URL, headers=auth("admin"), json=invalid)).status_code == 404


async def test_reprocess_and_read_does_not_rematch(client, db_session):
    created = (await client.post(URL, headers=auth("admin"), json=body([("NEW", "reader_code")], "rfid"))).json()
    sid = created["session_id"]
    aid = await animal(db_session, "NEW-PRIMARY")
    await identifier(db_session, aid, "NEW", AnimalIdentifierType.READER_CODE)
    assert (await client.get(f"{URL}/{sid}", headers=auth("viewer"))).json()["matched_count"] == 0
    for role in ("viewer", "data_entry"):
        assert (await client.post(f"{URL}/{sid}/reprocess", headers=auth(role))).status_code == 403
    result = (await client.post(f"{URL}/{sid}/reprocess", headers=auth("admin"))).json()
    assert result["matched_count"] == 1 and result["coverage_pct"] == 100.0
    ident = (await db_session.execute(select(AnimalIdentifier))).scalar_one()
    ident.is_active = False
    await db_session.commit()
    result = (await client.post(f"{URL}/{sid}/reprocess", headers=auth("admin"))).json()
    assert result["matched_count"] == 0 and result["in_system_not_seen_count"] == 1


@pytest.mark.parametrize("entries,kind", [
    ([("VISUAL", "visual_tag")], "rfid"), ([("123", "eid")], "visual"),
    ([("123", "uhf_tag")], "mixed"), ([(" ", "eid")], "rfid"),
    ([("x" * 101, "eid")], "rfid"),
])
async def test_validation(client, entries, kind):
    assert (await client.post(URL, headers=auth("admin"), json=body(entries, kind))).status_code == 422


async def test_ambiguous_match_rolls_back(client, db_session):
    first = await animal(db_session, "FIRST")
    second = await animal(db_session, "SECOND")
    await identifier(db_session, first, "DUPLICATE")
    await identifier(db_session, second, "DUPLICATE")
    response = await client.post(URL, headers=auth("admin"), json=body([("FIRST", "visual_tag"), ("DUPLICATE", "eid")]))
    assert response.status_code == 409
    assert (await db_session.execute(select(func.count(ReconciliationSession.id)))).scalar_one() == 0


async def test_newest_first(client):
    ids = []
    for day in ("2026-11-08", "2026-11-09", "2026-11-09"):
        payload = body()
        payload["session_date"] = day
        ids.append((await client.post(URL, headers=auth("admin"), json=payload)).json()["session_id"])
    listing = (await client.get(URL, headers=auth("viewer"))).json()
    assert [row["id"] for row in listing] == list(reversed(ids))


async def test_failed_reprocess_preserves_previous_matches(client, db_session):
    first = await animal(db_session, "FIRST")
    second = await animal(db_session, "SECOND")
    await identifier(db_session, first, "ORIGINAL")
    await identifier(db_session, second, "LATER-AMBIGUOUS")
    created = (await client.post(URL, headers=auth("admin"), json=body([
        ("ORIGINAL", "eid"), ("LATER-AMBIGUOUS", "eid"),
    ]))).json()
    original = (await db_session.execute(select(AnimalIdentifier).where(
        AnimalIdentifier.id_value == "ORIGINAL",
    ))).scalar_one()
    original.is_active = False
    await db_session.commit()
    await identifier(db_session, first, "LATER-AMBIGUOUS")
    sid = created["session_id"]
    response = await client.post(f"{URL}/{sid}/reprocess", headers=auth("admin"))
    assert response.status_code == 409
    detail = (await client.get(f"{URL}/{sid}", headers=auth("viewer"))).json()
    assert detail["matched_count"] == 2 and detail["unmatched_scan_count"] == 0
