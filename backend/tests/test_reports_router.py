"""Reproduction reports (/api/reports/calving, /reproductive-status, /abortions). SQLite in-memory."""
from datetime import date, datetime, timezone

import pytest

from conftest import FARM_ID, auth, category_id, make_location
from models import (
    AbortionStage, Animal, AnimalAcquisitionType, AnimalIdentifier, AnimalIdentifierType, AnimalSex,
    AnimalStatus, CalvingOutcome, ReproductiveCycle, ReproductiveCycleStatus as CS, SpeciesType,
)

pytestmark = pytest.mark.asyncio
CATTLE = SpeciesType.CATTLE


async def animal(db, tag, sex=AnimalSex.FEMALE, species=CATTLE, loc=FARM_ID, **kw):
    cat = await category_id(db, species)
    a = Animal(tag_number=tag, species=species, category_id=cat, location_id=loc, sex=sex,
               acquisition_type=AnimalAcquisitionType.BORN, acquisition_date=date(2022, 1, 1),
               status=kw.pop("status", AnimalStatus.ACTIVE), **kw)
    db.add(a)
    await db.commit()
    return a.id


async def cycle(db, animal_id, number=1, **kw):
    c = ReproductiveCycle(animal_id=animal_id, cycle_number=number, **kw)
    db.add(c)
    await db.commit()
    return c.id


async def get(client, url, role="viewer"):
    return await client.get(url, headers=auth(role))


@pytest.mark.parametrize("path", ["/api/reports/calving", "/api/reports/reproductive-status", "/api/reports/abortions"])
async def test_requires_auth(client, path):
    assert (await client.get(path)).status_code == 403
    assert (await client.get(path, headers={"Authorization": "Bearer nope"})).status_code == 401
    for role in ("admin", "data_entry", "viewer"):
        assert (await get(client, path, role)).status_code == 200


async def test_existing_report_routes_not_shadowed(client):
    # sales needs date_from/date_to (422 without) - proves the original route still answers, not ours.
    assert (await get(client, "/api/reports/sales")).status_code == 422
    assert (await get(client, "/api/reports/mortality")).status_code in (200, 422)
    assert (await get(client, "/api/reports/daily")).status_code in (200, 422)


async def test_calving_report(client, db_session):
    other_loc = await make_location(db_session, "Other")
    dam1 = await animal(db_session, "D1")
    dam2 = await animal(db_session, "D2")
    dam_goat = await animal(db_session, "G1", species=SpeciesType.GOAT, loc=other_loc)
    calf = await animal(db_session, "CALF1", sex=AnimalSex.MALE, status=AnimalStatus.DEAD)
    db_session.add_all([
        AnimalIdentifier(animal_id=dam1, id_type=AnimalIdentifierType.EID, id_value="EID-1"),
        AnimalIdentifier(animal_id=dam1, id_type=AnimalIdentifierType.VISUAL_TAG, id_value="OLD", is_active=False),
        AnimalIdentifier(animal_id=calf, id_type=AnimalIdentifierType.UHF_TAG, id_value="UHF-C"),
    ])
    await db_session.commit()
    day = lambda d: dict(actual_calving_date=date(2024, 1, d), status=CS.CALVED)  # noqa: E731
    await cycle(db_session, dam1, 1, calving_outcome=CalvingOutcome.LIVE_CALF, calf_animal_id=calf,
                calf_sex=AnimalSex.MALE, calving_interval_days=380, **day(10))
    await cycle(db_session, dam1, 2, calving_outcome=CalvingOutcome.STILLBIRTH, **day(20))
    await cycle(db_session, dam2, 1, calving_outcome=CalvingOutcome.ASSISTED_LIVE, **day(15))
    await cycle(db_session, dam2, 2, calving_outcome=CalvingOutcome.ASSISTED_DEAD, **day(5))
    await cycle(db_session, dam2, 3, calving_outcome=CalvingOutcome.ABORTION, **day(25))  # excluded
    await cycle(db_session, dam_goat, 1, calving_outcome=CalvingOutcome.LIVE_CALF, **day(12))
    await cycle(db_session, dam1, 3, calving_outcome=CalvingOutcome.LIVE_CALF, status=CS.PREGNANT)  # no date: excluded

    body = (await get(client, "/api/reports/calving")).json()
    assert body["summary"] == {"total": 5, "live": 3, "stillbirths": 1, "assisted": 2}
    assert [r["calved_date"] for r in body["rows"]] == [f"2024-01-{d}" for d in ("20", "15", "12", "10", "05")]
    first_live = next(r for r in body["rows"] if r["calved_date"] == "2024-01-10")
    assert first_live["dam_tag"] == "D1" and first_live["dam_tags"] == [{"id_type": "EID", "id_value": "EID-1"}]
    assert first_live["calf_tag"] == "CALF1" and first_live["calf_tags"] == [{"id_type": "UHF_TAG", "id_value": "UHF-C"}]
    assert first_live["calving_outcome"] == "LIVE_CALF" and first_live["calving_interval_days"] == 380
    assert first_live["calf_sex"] == "male" and first_live["calf_status"] == "dead"
    assert first_live["location_name"] and first_live["species"] == "cattle"

    only_goat = (await get(client, f"/api/reports/calving?location_id={other_loc}")).json()
    assert only_goat["summary"]["total"] == 1 and only_goat["rows"][0]["dam_tag"] == "G1"
    assert (await get(client, "/api/reports/calving?species=goat")).json()["summary"]["total"] == 1
    ranged = (await get(client, "/api/reports/calving?date_from=2024-01-10&date_to=2024-01-15")).json()
    assert ranged["summary"]["total"] == 3
    assert (await get(client, "/api/reports/calving?date_from=2024-02-01&date_to=2024-01-01")).status_code == 400
    assert (await get(client, "/api/reports/calving?species=dragon")).status_code == 422


async def test_reproductive_status_report(client, db_session):
    cows = {t: await animal(db_session, t) for t in ("A", "B", "C", "D")}
    await animal(db_session, "BULL", sex=AnimalSex.MALE)
    db_session.add(AnimalIdentifier(animal_id=cows["A"], id_type=AnimalIdentifierType.BRANDING_MARK, id_value="BR"))
    await db_session.commit()
    t = lambda h: datetime(2024, 1, 1, h, tzinfo=timezone.utc)  # noqa: E731
    # A: older OPEN cycle then newer PREGNANT cycle -> latest wins
    await cycle(db_session, cows["A"], 1, status=CS.OPEN, created_at=t(1))
    await cycle(db_session, cows["A"], 2, status=CS.PREGNANT, created_at=t(2),
                expected_calving_date=date(2024, 9, 1), calving_interval_days=400)
    await cycle(db_session, cows["B"], 1, status=CS.SERVED)
    await cycle(db_session, cows["C"], 1, status=CS.CALVED)
    # D has no cycle -> unknown

    body = (await get(client, "/api/reports/reproductive-status")).json()
    assert body["summary"]["total"] == 4  # females only
    assert body["summary"]["by_status"] == {"OPEN": 0, "SERVED": 1, "PREGNANT": 1, "CALVED": 1, "ABORTED": 0, "unknown": 1}
    assert [r["tag_number"] for r in body["rows"]] == ["A", "B", "C", "D"]
    a = body["rows"][0]
    assert a["cycle_status"] == "PREGNANT" and a["expected_calving_date"] == "2024-09-01"
    assert a["calving_interval_days"] == 400 and a["tags"] == [{"id_type": "BRANDING_MARK", "id_value": "BR"}]
    assert body["rows"][3]["cycle_status"] is None

    filtered = (await get(client, "/api/reports/reproductive-status?status=pregnant, SERVED")).json()
    assert [r["tag_number"] for r in filtered["rows"]] == ["A", "B"]
    assert filtered["summary"]["total"] == 2
    assert (await get(client, "/api/reports/reproductive-status?status=OPEN")).json()["rows"] == []  # A's OPEN is stale
    assert (await get(client, "/api/reports/reproductive-status?status=BOGUS")).status_code == 400


async def test_abortions_report(client, db_session):
    cow = await animal(db_session, "AB1")
    cow2 = await animal(db_session, "AB2", species=SpeciesType.SHEEP)
    db_session.add(AnimalIdentifier(animal_id=cow, id_type=AnimalIdentifierType.EID, id_value="E9"))
    await db_session.commit()
    await cycle(db_session, cow, 1, status=CS.ABORTED, abortion_stage=AbortionStage.EARLY, notes="n1",
                created_at=datetime(2024, 3, 1, 12, tzinfo=timezone.utc))
    await cycle(db_session, cow, 2, status=CS.ABORTED, abortion_stage=AbortionStage.LATE,
                created_at=datetime(2024, 5, 1, 12, tzinfo=timezone.utc))
    await cycle(db_session, cow2, 1, status=CS.ABORTED, created_at=datetime(2024, 4, 1, 12, tzinfo=timezone.utc))
    await cycle(db_session, cow, 3, status=CS.PREGNANT)  # not aborted

    body = (await get(client, "/api/reports/abortions")).json()
    assert body["summary"] == {"total": 3, "by_stage": {"late": 1, "early": 1, "unknown": 1}}
    assert [r["cycle_number"] for r in body["rows"]] == [2, 1, 1]  # newest first
    assert body["rows"][1]["tags"] == [] and body["rows"][2]["tags"] == [{"id_type": "EID", "id_value": "E9"}]
    assert body["rows"][2]["notes"] == "n1" and body["rows"][2]["abortion_stage"] == "early"
    ranged = (await get(client, "/api/reports/abortions?date_from=2024-04-01&date_to=2024-04-30")).json()
    assert ranged["summary"]["total"] == 1 and ranged["rows"][0]["species"] == "sheep"
    assert (await get(client, "/api/reports/abortions?species=cattle")).json()["summary"]["total"] == 2
