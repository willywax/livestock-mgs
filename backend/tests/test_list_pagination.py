"""Opt-in pagination on GET /animals and GET /daily-logs, daily-log event_count, and the SQL-cutoff
equivalence used by the transition queue. SQLite in-memory: Postgres behaviour is read-verified only."""
from datetime import date, timedelta

import pytest

import server
from conftest import FARM_ID, auth, category_id, make_daily_log, post_event
from models import Animal, AnimalAcquisitionType, AnimalSex, SpeciesType

pytestmark = pytest.mark.asyncio
CATTLE = SpeciesType.CATTLE


async def _animals(db, n):
    cat = await category_id(db, CATTLE)
    for i in range(n):
        db.add(Animal(tag_number=f"P-{i:03d}", species=CATTLE, category_id=cat, location_id=FARM_ID,
                      sex=AnimalSex.FEMALE, acquisition_type=AnimalAcquisitionType.BORN,
                      acquisition_date=date(2024, 1, 1), notes=f"note {i}"))
    await db.commit()


async def test_animals_default_is_bare_list(client, db_session):
    await _animals(db_session, 5)
    r = await client.get("/api/animals", headers=auth("viewer"))
    body = r.json()
    assert r.status_code == 200 and isinstance(body, list) and len(body) == 5
    assert body[0]["notes"] == "note 0" and body[0]["category_name_sw"] and body[0]["location_name"]


async def test_animals_paged_envelope(client, db_session):
    await _animals(db_session, 5)
    r = await client.get("/api/animals?page=2&page_size=2", headers=auth("viewer"))
    body = r.json()
    assert r.status_code == 200
    assert [a["tag_number"] for a in body["items"]] == ["P-002", "P-003"]
    assert (body["total"], body["page"], body["page_size"], body["pages"]) == (5, 2, 2, 3)
    last = (await client.get("/api/animals?page=3&page_size=2", headers=auth("viewer"))).json()
    assert [a["tag_number"] for a in last["items"]] == ["P-004"]
    beyond = (await client.get("/api/animals?page=9&page_size=2", headers=auth("viewer"))).json()
    assert beyond["items"] == [] and beyond["total"] == 5


async def test_animals_paged_respects_filters_in_total(client, db_session):
    await _animals(db_session, 4)
    body = (await client.get("/api/animals?page_size=10&search=P-001", headers=auth("viewer"))).json()
    assert body["total"] == 1 and len(body["items"]) == 1 and body["pages"] == 1


async def test_animals_export_ignores_paging_and_validation(client, db_session):
    await _animals(db_session, 5)
    r = await client.get("/api/animals?export=true&page=1&page_size=2", headers=auth("viewer"))
    assert isinstance(r.json(), list) and len(r.json()) == 5
    for bad in ("page=0", "page_size=0", "page_size=201"):
        assert (await client.get(f"/api/animals?{bad}", headers=auth("viewer"))).status_code == 422


async def test_daily_logs_bare_list_has_event_count(client, db_session):
    log = await make_daily_log(db_session, FARM_ID, date(2024, 5, 1))
    koo = await category_id(db_session, CATTLE)
    for _ in range(2):
        assert (await post_event(client, log, event_type="birth", species="cattle",
                                 category_id=koo, count=1)).status_code == 200
    empty = await make_daily_log(db_session, FARM_ID, date(2024, 5, 2))
    body = (await client.get("/api/daily-logs", headers=auth("viewer"))).json()
    assert isinstance(body, list)
    by_id = {entry["id"]: entry for entry in body}
    assert by_id[log]["event_count"] == 2 and len(by_id[log]["events"]) == 2
    assert by_id[empty]["event_count"] == 0 and by_id[empty]["events"] == []
    assert by_id[log]["location_name"] and by_id[log]["events"][0]["event_type"] == "birth"
    assert [entry["id"] for entry in body] == [empty, log]  # newest log_date first


async def test_daily_logs_paged_envelope(client, db_session):
    for day in range(1, 6):
        await make_daily_log(db_session, FARM_ID, date(2024, 6, day))
    body = (await client.get("/api/daily-logs?page=2&page_size=2", headers=auth("viewer"))).json()
    assert [entry["log_date"] for entry in body["items"]] == ["2024-06-03", "2024-06-02"]
    assert (body["total"], body["pages"]) == (5, 3)
    filtered = (await client.get("/api/daily-logs?page=1&start_date=2024-06-04", headers=auth("viewer"))).json()
    assert filtered["total"] == 2 and filtered["page_size"] == 50


async def test_months_ago_cutoff_matches_age_in_months():
    """birth <= _months_ago(today, n)  <=>  _age_in_months(birth, today) >= n, including month-end clamping."""
    for today in (date(2026, 3, 31), date(2026, 3, 30), date(2024, 3, 29), date(2026, 1, 31), date(2026, 12, 31),
                  date(2026, 2, 28), date(2026, 5, 1)):
        for months in (0, 1, 2, 7, 12, 18, 25):
            cutoff = server._months_ago(today, months)
            for offset in range(0, 900):
                birth = today - timedelta(days=offset)
                assert (birth <= cutoff) == (server._age_in_months(birth, today) >= months), (today, months, birth)
