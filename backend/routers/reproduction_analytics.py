"""Reproduction KPIs."""
from datetime import date
from typing import Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models import Animal, AnimalSex, AnimalStatus, BCSRecord, CalvingOutcome, Category, DailyLog, Event, EventAnimalLink, EventType, Location, OpeningBalance, PDResult, ReproductiveCycle, ReproductiveCycleStatus, SpeciesType, StockLevel, User
from schemas import LocationReproductionMetrics, ReproductionAnalyticsResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import _ANY_ROLE

router = APIRouter()

# ---------- Reproduction analytics ----------
def _bcs_band(score: float) -> str:
    if score < 2.0:
        return "1.0-1.5"
    if score < 3.0:
        return "2.0-2.5"
    if score < 4.0:
        return "3.0-3.5"
    return "4.0+"


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


async def _repro_metrics(db: AsyncSession, start: date, end: date, location_id: Optional[int],
                         species: Optional[SpeciesType] = None) -> dict:
    """Reproduction metrics for a date range (and optionally one location, by the animal's current location).

    Reproduction is recorded in several places, so the metrics combine them: daily-log BIRTH events
    (offspring count) and PD_TEST events (tested count by result) plus reproductive_cycles, with a
    cycle calving/PD skipped when a linked daily-log event already covers the same animal and date.
    Pregnant/open counts use animals.reproductive_status (cycles only fill in animals still 'unknown').
    `species` optionally limits everything to one species.

    koo_count: latest OpeningBalance per (location, species, category) for Koo categories with
    period_start <= the range start, summed over species; falls back to current StockLevel when
    there is no opening balance. Calvings/PD checks are bucketed by their own dates; open/pregnant
    counts are a current snapshot of active animals.
    """
    koo_ids = list((await db.execute(select(Category.id).where(Category.name_sw == "Koo"))).scalars().all())

    koo_count = 0
    if koo_ids:
        ob_query = select(OpeningBalance).where(and_(
            OpeningBalance.category_id.in_(koo_ids), OpeningBalance.period_start <= start))
        if location_id:
            ob_query = ob_query.where(OpeningBalance.location_id == location_id)
        if species:
            ob_query = ob_query.where(OpeningBalance.species == species)
        latest: dict = {}
        for ob in (await db.execute(ob_query)).scalars().all():
            key = (ob.location_id, ob.species, ob.category_id)
            if key not in latest or ob.period_start > latest[key].period_start:
                latest[key] = ob
        if latest:
            koo_count = sum(ob.count for ob in latest.values())
        else:
            sl_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                StockLevel.category_id.in_(koo_ids))
            if location_id:
                sl_query = sl_query.where(StockLevel.location_id == location_id)
            if species:
                sl_query = sl_query.where(StockLevel.species == species)
            koo_count = (await db.execute(sl_query)).scalar() or 0

    cyc_query = select(ReproductiveCycle).join(Animal, Animal.id == ReproductiveCycle.animal_id)
    if location_id:
        cyc_query = cyc_query.where(Animal.location_id == location_id)
    if species:
        cyc_query = cyc_query.where(Animal.species == species)
    cycles = (await db.execute(cyc_query)).scalars().all()

    # Daily-log events (where most ranch reproduction is actually recorded).
    def log_events(*columns, event_type):
        query = (select(*columns).select_from(Event).join(DailyLog, DailyLog.id == Event.daily_log_id)
                 .where(Event.event_type == event_type, DailyLog.log_date >= start, DailyLog.log_date <= end))
        if location_id:
            query = query.where(DailyLog.location_id == location_id)
        if species:
            query = query.where(Event.species == species)
        return query

    async def linked_animal_dates(event_type, roles):
        rows = await db.execute(
            log_events(EventAnimalLink.animal_id, DailyLog.log_date, event_type=event_type)
            .join(EventAnimalLink, EventAnimalLink.event_id == Event.id)
            .where(EventAnimalLink.is_active.is_(True), EventAnimalLink.role.in_(roles)))
        return {(animal_id, log_date) for animal_id, log_date in rows.all()}

    log_births = int((await db.execute(
        log_events(func.coalesce(func.sum(Event.count), 0), event_type=EventType.BIRTH))).scalar() or 0)
    pd_counts = {result: int(total or 0) for result, total in (await db.execute(
        log_events(Event.pd_result, func.sum(Event.count), event_type=EventType.PD_TEST)
        .where(Event.pd_result.in_(("pregnant", "open"))).group_by(Event.pd_result))).all()}
    birth_dates = await linked_animal_dates(EventType.BIRTH, ("mother", "subject"))
    pd_dates = await linked_animal_dates(EventType.PD_TEST, ("subject",))

    def in_range(d: Optional[date]) -> bool:
        return d is not None and start <= d <= end

    calved = [c for c in cycles if in_range(c.actual_calving_date)]
    cycle_live = sum(1 for c in calved
                     if c.calving_outcome in (CalvingOutcome.LIVE_CALF, CalvingOutcome.ASSISTED_LIVE)
                     and (c.animal_id, c.actual_calving_date) not in birth_dates)
    live = log_births + cycle_live
    pd_done = [c for c in cycles if c.pd_result is not None and in_range(c.pd_check_date)
               and (c.animal_id, c.pd_check_date) not in pd_dates]
    pd_total = len(pd_done) + sum(pd_counts.values())
    pd_pregnant = sum(1 for c in pd_done if c.pd_result == PDResult.PREGNANT) + pd_counts.get("pregnant", 0)
    confirmed = [c for c in cycles if c.pd_result == PDResult.PREGNANT
                 and in_range(c.actual_calving_date or c.pd_check_date or c.service_date)]
    aborted = sum(1 for c in confirmed
                  if c.status == ReproductiveCycleStatus.ABORTED or c.calving_outcome == CalvingOutcome.ABORTION)
    intervals = [c.calving_interval_days for c in calved if c.calving_interval_days is not None]

    animal_query = select(Animal.id, Animal.category_id, Animal.reproductive_status).where(
        and_(Animal.status == AnimalStatus.ACTIVE, Animal.sex == AnimalSex.FEMALE))
    if location_id:
        animal_query = animal_query.where(Animal.location_id == location_id)
    if species:
        animal_query = animal_query.where(Animal.species == species)
    female_rows = (await db.execute(animal_query)).all()
    active_females = {row[0]: row[1] for row in female_rows}
    status_of = {row[0]: row[2] for row in female_rows}
    pregnant_ids = {aid for aid, state in status_of.items() if state == "pregnant"}
    pregnant_ids |= {
        c.animal_id for c in cycles
        if c.pd_result == PDResult.PREGNANT and c.actual_calving_date is None
        and c.status != ReproductiveCycleStatus.ABORTED and c.calving_outcome != CalvingOutcome.ABORTION
        and c.animal_id in active_females and status_of.get(c.animal_id) in (None, "unknown")
    }
    open_cows = sum(1 for aid, cat in active_females.items() if cat in koo_ids and aid not in pregnant_ids)

    bcs_query = (
        select(BCSRecord).join(Animal, Animal.id == BCSRecord.animal_id)
        .where(and_(Animal.status == AnimalStatus.ACTIVE, BCSRecord.score_date <= end))
        .order_by(BCSRecord.score_date, BCSRecord.id)
    )
    if location_id:
        bcs_query = bcs_query.where(Animal.location_id == location_id)
    latest_bcs = {r.animal_id: float(r.bcs) for r in (await db.execute(bcs_query)).scalars().all()}
    distribution = {"1.0-1.5": 0, "2.0-2.5": 0, "3.0-3.5": 0, "4.0+": 0}
    for score in latest_bcs.values():
        distribution[_bcs_band(score)] += 1

    return {
        "koo_count": int(koo_count),
        "live_calvings": live,
        "calving_rate": _ratio(live, int(koo_count)),
        "conception_rate": _ratio(pd_pregnant, pd_total),
        "abortion_rate": _ratio(aborted, len(confirmed)),
        "avg_calving_interval_days": round(sum(intervals) / len(intervals), 1) if intervals else None,
        "open_cows": open_cows,
        "pregnant_cows": len(pregnant_ids),
        "bcs_distribution": distribution,
    }


@router.get("/analytics/reproduction", response_model=ReproductionAnalyticsResponse)
async def get_reproduction_analytics(
    location_id: Optional[int] = None,
    year: Optional[int] = Query(None, ge=2000, le=2100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    # Explicit dates override year; with neither, the current calendar year is used (unchanged).
    if date_from or date_to:
        if not (date_from and date_to):
            raise HTTPException(status_code=400, detail="date_from and date_to must be provided together")
        if date_to < date_from:
            raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
        start, end = date_from, date_to
        year = date_to.year
    else:
        year = year or date.today().year
        start, end = date(year, 1, 1), date(year, 12, 31)
    overall = await _repro_metrics(db, start, end, location_id, species)
    loc_query = select(Location).where(Location.is_active == True)  # noqa: E712
    if location_id:
        loc_query = loc_query.where(Location.id == location_id)
    by_location = []
    for loc in (await db.execute(loc_query.order_by(Location.name))).scalars().all():
        by_location.append(LocationReproductionMetrics(
            location_id=loc.id, location_name=loc.name, **(await _repro_metrics(db, start, end, loc.id, species))))
    return ReproductionAnalyticsResponse(year=year, location_id=location_id, by_location=by_location, **overall)
