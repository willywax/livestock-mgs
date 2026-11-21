"""Point-in-time stock snapshot helpers shared by dashboard and reports."""
from datetime import date
from typing import List, Optional

from models import DailyLog, Event, Location, OpeningBalance
from schemas import LocationTotals
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.stock import event_stock_adjustments

async def build_stock_snapshot(
    db: AsyncSession,
    as_of_date: date,
    location_id: Optional[int] = None
) -> dict:
    openings_query = select(OpeningBalance).where(OpeningBalance.period_start <= as_of_date)
    if location_id:
        openings_query = openings_query.where(OpeningBalance.location_id == location_id)
    openings_query = openings_query.order_by(OpeningBalance.period_start.desc())
    result = await db.execute(openings_query)
    openings = result.scalars().all()

    latest_openings = {}
    for opening in openings:
        key = (opening.location_id, opening.species, opening.category_id)
        if key not in latest_openings:
            latest_openings[key] = {"count": opening.count, "start": opening.period_start}

    current = dict(latest_openings)

    events_query = (
        select(Event, DailyLog.log_date, DailyLog.location_id)
        .join(DailyLog)
        .where(DailyLog.log_date <= as_of_date)
        .order_by(DailyLog.log_date.asc(), Event.id.asc())
    )
    if location_id:
        events_query = events_query.where(
            or_(
                DailyLog.location_id == location_id,
                Event.from_location_id == location_id,
                Event.to_location_id == location_id
            )
        )
    result = await db.execute(events_query)
    events = result.all()

    for event, log_date, log_location_id in events:
        for adj_location_id, adj_species, adj_category_id, delta in event_stock_adjustments(event, log_location_id):
            if location_id and adj_location_id != location_id:
                continue
            key = (adj_location_id, adj_species, adj_category_id)
            if key not in current:
                current[key] = {"count": 0, "start": date.min}
            if log_date < current[key]["start"]:
                continue
            current[key]["count"] += delta

    return current

async def build_location_totals_from_snapshot(
    db: AsyncSession,
    snapshot: dict,
    location_id: Optional[int] = None,
    include_zero: bool = False
) -> List[LocationTotals]:
    totals = {}
    for (loc_id, species, _category_id), data in snapshot.items():
        if location_id and loc_id != location_id:
            continue
        if loc_id not in totals:
            totals[loc_id] = {"cattle": 0, "sheep": 0, "goat": 0, "total": 0}
        species_key = species.value
        totals[loc_id][species_key] += data["count"]
        totals[loc_id]["total"] += data["count"]

    if location_id and location_id not in totals:
        totals[location_id] = {"cattle": 0, "sheep": 0, "goat": 0, "total": 0}

    location_ids = list(totals.keys())
    location_names = {}
    if location_ids:
        result = await db.execute(select(Location).where(Location.id.in_(location_ids)))
        location_names = {loc.id: loc.name for loc in result.scalars().all()}

    results = []
    for loc_id, counts in totals.items():
        if not include_zero and counts["total"] <= 0:
            continue
        results.append(LocationTotals(
            location_id=loc_id,
            location_name=location_names.get(loc_id, "Unknown"),
            cattle=counts["cattle"],
            sheep=counts["sheep"],
            goat=counts["goat"],
            total=counts["total"]
        ))

    results.sort(key=lambda lt: lt.total, reverse=True)
    return results
