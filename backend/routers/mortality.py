"""Death causes, mortality thresholds and the mortality report."""
from datetime import date
from decimal import Decimal
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import DailyLog, DeathCause, Event, EventType, Location, MortalityThreshold, SpeciesType, User, UserRole
from schemas import DeathCauseCreate, DeathCauseResponse, DeathCauseUpdate, MortalityReportResponse, MortalityThresholdResponse, MortalityThresholdUpdate
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import _ANY_ROLE
from services.stock_snapshot import build_stock_snapshot

router = APIRouter()

# ---------- Structured mortality ----------

async def _get_death_cause(db, cause_id):
    cause = await db.get(DeathCause, cause_id)
    if cause is None:
        raise HTTPException(status_code=404, detail="Death cause not found")
    return cause


async def _save_death_cause(db, cause):
    try:
        db.add(cause)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A death cause with this name already exists")
    await db.refresh(cause)
    return cause


@router.get("/death-causes", response_model=List[DeathCauseResponse])
async def list_death_causes(
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return (await db.execute(select(DeathCause).where(DeathCause.is_active == is_active)
                            .order_by(DeathCause.sort_order, DeathCause.name))).scalars().all()


@router.post("/death-causes", response_model=DeathCauseResponse)
async def create_death_cause(
    data: DeathCauseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    return await _save_death_cause(db, DeathCause(**data.model_dump()))


@router.put("/death-causes/{cause_id}", response_model=DeathCauseResponse)
async def update_death_cause(
    cause_id: int, data: DeathCauseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    cause = await _get_death_cause(db, cause_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(cause, key, value)
    return await _save_death_cause(db, cause)


@router.delete("/death-causes/{cause_id}")
async def deactivate_death_cause(
    cause_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    cause = await _get_death_cause(db, cause_id)
    cause.is_active = False
    await db.commit()
    return {"message": "Death cause deactivated"}


@router.get("/settings/mortality-thresholds", response_model=List[MortalityThresholdResponse])
async def get_mortality_thresholds(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return (await db.execute(select(MortalityThreshold).order_by(MortalityThreshold.species))).scalars().all()


@router.put("/settings/mortality-thresholds", response_model=List[MortalityThresholdResponse])
async def update_mortality_thresholds(
    data: List[MortalityThresholdUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if len({item.species for item in data}) != len(data):
        raise HTTPException(status_code=400, detail="Each species may appear only once")
    # Dialect-specific ON CONFLICT keeps first-time concurrent upserts atomic.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as threshold_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as threshold_insert
    try:
        for item in sorted(data, key=lambda item: item.species.value):
            statement = threshold_insert(MortalityThreshold).values(
                species=item.species, threshold=item.threshold, updated_by=current_user.id,
            )
            await db.execute(statement.on_conflict_do_update(
                index_elements=[MortalityThreshold.species],
                set_={"threshold": item.threshold, "updated_by": current_user.id, "updated_at": func.now()},
            ))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return (await db.execute(select(MortalityThreshold).order_by(MortalityThreshold.species)
                            .execution_options(populate_existing=True))).scalars().all()


@router.get("/reports/mortality", response_model=MortalityReportResponse)
async def mortality_report(
    date_from: date, date_to: date,
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    opening = await build_stock_snapshot(db, date_from, location_id)
    closing = await build_stock_snapshot(db, date_to, location_id)
    stocks = {}
    for snapshot, boundary in ((opening, 0), (closing, 1)):
        for (loc, sp, _category), value in snapshot.items():
            if location_id is not None and loc != location_id:
                continue
            if species is not None and species != sp:
                continue
            stocks.setdefault((loc, sp), [0, 0])[boundary] += value["count"]
    query = (select(Event, DailyLog.log_date, DailyLog.location_id, DeathCause.name)
             .join(DailyLog, Event.daily_log_id == DailyLog.id)
             .outerjoin(DeathCause, Event.cause_of_death_id == DeathCause.id)
             .where(Event.event_type == EventType.DEATH,
                    DailyLog.log_date >= date_from, DailyLog.log_date <= date_to))
    if location_id is not None:
        query = query.where(DailyLog.location_id == location_id)
    if species is not None:
        query = query.where(Event.species == species)
    events = (await db.execute(query)).all()
    deaths, causes = {}, {}
    total = 0
    # Twelve calendar months ending in date_to's month, clipped to the range.
    end_month = (date_to.year - 1) * 12 + date_to.month - 1
    start_month = max((date_from.year - 1) * 12 + date_from.month - 1, end_month - 11)
    months = {}
    for index in range(start_month, end_month + 1):
        key = f"{index // 12 + 1:04d}-{index % 12 + 1:02d}"
        months[key] = {"month": key, "deaths": 0, "by_species": {sp.value: 0 for sp in SpeciesType}}
    for event, day, loc, cause in events:
        key = (loc, event.species)
        deaths[key] = deaths.get(key, 0) + event.count
        stocks.setdefault(key, [0, 0])
        total += event.count
        if cause is not None:
            causes[cause] = causes.get(cause, 0) + event.count
        month = day.strftime("%Y-%m")
        if month in months:
            months[month]["deaths"] += event.count
            months[month]["by_species"][event.species.value] += event.count
    thresholds = {row.species: row.threshold for row in
                  (await db.execute(select(MortalityThreshold))).scalars().all()}
    locations = {row.id: row.name for row in (await db.execute(select(Location))).scalars().all()}

    def metrics(sp, count, bounds):
        average = Decimal(bounds[0] + bounds[1]) / 2
        rate = Decimal(count) / average * 100 if average > 0 else None
        threshold = thresholds.get(sp)
        return dict(species=sp, deaths=count, avg_stock=float(average),
                    mortality_rate_pct=round(float(rate), 2) if rate is not None else None,
                    threshold_pct=float(threshold) if threshold is not None else None,
                    is_alert=rate is not None and threshold is not None and rate > threshold)

    farms, aggregate = [], {}
    for (loc, sp), bounds in stocks.items():
        count = deaths.get((loc, sp), 0)
        if not count and not any(bounds):
            continue
        farms.append(dict(farm=locations.get(loc, "Unknown"), location_id=loc, **metrics(sp, count, bounds)))
        combined = aggregate.setdefault(sp, [0, 0, 0])
        combined[0] += bounds[0]
        combined[1] += bounds[1]
        combined[2] += count
    farms.sort(key=lambda row: (not row["is_alert"], -(row["mortality_rate_pct"] or 0), row["farm"], row["species"].value))
    return MortalityReportResponse(
        summary={"total_deaths": total, "period": {"from": date_from, "to": date_to}},
        by_species=[metrics(sp, values[2], values[:2]) for sp, values in sorted(aggregate.items(), key=lambda pair: pair[0].value)],
        by_farm=farms,
        by_cause=[dict(cause_name=name, count=count, pct_of_total=round(count / total * 100, 2) if total else 0)
                  for name, count in sorted(causes.items(), key=lambda pair: (pair[0].lower() == "unknown", -pair[1], pair[0]))],
        by_month=list(months.values()), flagged=[row for row in farms if row["is_alert"]],
    )
