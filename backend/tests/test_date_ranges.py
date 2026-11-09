"""date_from/date_to on /dashboard and /analytics/reproduction (SQLite, no server)."""
from datetime import date

import pytest

from conftest import FARM_ID, auth, category_id, make_daily_log
from models import Event, EventType, SpeciesType
from test_reproduction import CATTLE, cycle, make_animal

pytestmark = pytest.mark.asyncio


async def add_deaths(db, day, count):
    log = await make_daily_log(db, FARM_ID, day)
    db.add(Event(daily_log_id=log, event_type=EventType.DEATH, species=SpeciesType.CATTLE,
                 category_id=await category_id(db, CATTLE), count=count, is_stock_event=True))
    await db.commit()


def cattle(body):
    return next(row for row in body["herd_performance"] if row["species"] == "cattle")


async def test_dashboard_date_range_filters_events(client, db_session):
    await add_deaths(db_session, date(2026, 1, 10), 2)
    await add_deaths(db_session, date(2026, 3, 10), 5)
    get = lambda q: client.get(f"/api/dashboard?{q}", headers=auth("viewer"))  # noqa: E731
    both = (await get("date_from=2026-01-01&date_to=2026-12-31")).json()
    assert cattle(both)["deaths_30d"] == 7
    jan = (await get("date_from=2026-01-01&date_to=2026-01-31")).json()
    assert cattle(jan)["deaths_30d"] == 2
    march = (await get("date_from=2026-02-01&date_to=2026-03-31")).json()
    assert cattle(march)["deaths_30d"] == 5
    assert next(n for n in march["net_changes"] if n["species"] == "cattle")["deaths"] == 5
    assert (await get("date_from=2026-03-01&date_to=2026-01-01")).status_code == 400
    # Without dates the old period_days behaviour is unchanged and still succeeds.
    assert (await get("period_days=30")).status_code == 200


async def test_reproduction_date_range(client, db_session):
    koo = await category_id(db_session, CATTLE)
    cow = await make_animal(db_session, "R1", cat=koo)
    await cycle(client, cow, pd_check_date="2025-02-10", pd_result="pregnant",
                actual_calving_date="2025-11-20", calving_outcome="live_calf", status="calved")
    get = lambda q: client.get(f"/api/analytics/reproduction?{q}", headers=auth("viewer"))  # noqa: E731
    late = (await get("date_from=2025-06-01&date_to=2025-12-31")).json()
    assert late["live_calvings"] == 1
    early = (await get("date_from=2025-01-01&date_to=2025-06-30")).json()
    assert early["live_calvings"] == 0
    # A full-year range matches the year parameter.
    by_year = (await get("year=2025")).json()
    by_range = (await get("date_from=2025-01-01&date_to=2025-12-31")).json()
    for key in ("koo_count", "live_calvings", "conception_rate", "calving_rate"):
        assert by_year[key] == by_range[key]
    assert (await get("date_from=2025-01-01")).status_code == 400
    assert (await get("date_from=2025-12-31&date_to=2025-01-01")).status_code == 400
