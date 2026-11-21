"""Farm-health events and intervals (dipping, vaccination, deworming)."""
from datetime import date, timedelta
from typing import List, Optional

from auth import get_current_user, require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models import Category, CategoryScope, FarmHealthEvent as FarmHealthEventModel, HealthEventType, HealthInterval, Location, SpeciesType, User, UserRole, VaccineType
from schemas import CategoryInfo, FarmHealthEventCreate, FarmHealthEventResponse, FarmHealthEventUpdate, HealthIntervalCreate, HealthIntervalResponse, HealthIntervalUpdate, LastEventSummary
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()

# ==================== FARM HEALTH ROUTES ====================

async def _resolve_categories_for_event(db: AsyncSession, category_ids):
    if not category_ids:
        return []
    result = await db.execute(select(Category).where(Category.id.in_(category_ids)))
    return [CategoryInfo(id=c.id, name_sw=c.name_sw, name_en=c.name_en) for c in result.scalars().all()]

async def _compute_next_due(db: AsyncSession, location_id: int, species, event_type, event_date: date):
    if species is None:
        return None
    interval_result = await db.execute(
        select(HealthInterval).where(
            and_(
                HealthInterval.location_id == location_id,
                HealthInterval.species == species,
                HealthInterval.event_type == event_type,
            )
        )
    )
    interval = interval_result.scalar_one_or_none()
    if interval:
        return event_date + timedelta(days=interval.interval_days)
    return None

def _health_event_response(ev: FarmHealthEventModel, resolved_categories=None, vaccine_type_name=None) -> FarmHealthEventResponse:
    return FarmHealthEventResponse(
        id=ev.id,
        location_id=ev.location_id,
        event_type=ev.event_type,
        event_date=ev.event_date,
        species=ev.species,
        category_scope=ev.category_scope,
        category_ids=ev.category_ids,
        product_name=ev.product_name,
        dosage=ev.dosage,
        cost_per_head=ev.cost_per_head,
        total_cost=ev.total_cost,
        head_count=ev.head_count,
        next_due_date=ev.next_due_date,
        notes=ev.notes,
        created_at=ev.created_at,
        location_name=ev.location.name if ev.location else None,
        resolved_categories=resolved_categories or [],
        created_by_name=ev.creator.name if ev.creator else None,
        vaccine_type_id=ev.vaccine_type_id,
        vaccine_type_name=vaccine_type_name,
    )

@router.get("/health-intervals", response_model=List[HealthIntervalResponse])
async def list_health_intervals(
    location_id: Optional[int] = Query(None),
    species: Optional[SpeciesType] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(HealthInterval).options(selectinload(HealthInterval.location))
    if location_id:
        q = q.where(HealthInterval.location_id == location_id)
    if species:
        q = q.where(HealthInterval.species == species)
    q = q.order_by(HealthInterval.location_id, HealthInterval.species, HealthInterval.event_type)
    result = await db.execute(q)
    return [
        HealthIntervalResponse(
            id=i.id,
            location_id=i.location_id,
            species=i.species,
            event_type=i.event_type,
            interval_days=i.interval_days,
            notes=i.notes,
            location_name=i.location.name if i.location else None,
        )
        for i in result.scalars().all()
    ]

@router.post("/health-intervals", response_model=HealthIntervalResponse)
async def create_health_interval(
    data: HealthIntervalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = await db.execute(
        select(HealthInterval).where(
            and_(
                HealthInterval.location_id == data.location_id,
                HealthInterval.species == data.species,
                HealthInterval.event_type == data.event_type,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Interval already exists for this combination. Use PUT to update.")

    iv = HealthInterval(
        location_id=data.location_id,
        species=data.species,
        event_type=data.event_type,
        interval_days=data.interval_days,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(iv)
    await db.commit()

    result = await db.execute(
        select(HealthInterval).options(selectinload(HealthInterval.location)).where(HealthInterval.id == iv.id)
    )
    i = result.scalar_one()
    return HealthIntervalResponse(
        id=i.id, location_id=i.location_id, species=i.species, event_type=i.event_type,
        interval_days=i.interval_days, notes=i.notes,
        location_name=i.location.name if i.location else None,
    )

@router.put("/health-intervals/{interval_id}", response_model=HealthIntervalResponse)
async def update_health_interval(
    interval_id: int,
    data: HealthIntervalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(
        select(HealthInterval).options(selectinload(HealthInterval.location)).where(HealthInterval.id == interval_id)
    )
    iv = result.scalar_one_or_none()
    if not iv:
        raise HTTPException(status_code=404, detail="Interval not found")
    if data.interval_days is not None:
        iv.interval_days = data.interval_days
    if data.notes is not None:
        iv.notes = data.notes
    await db.commit()
    await db.refresh(iv)
    return HealthIntervalResponse(
        id=iv.id, location_id=iv.location_id, species=iv.species, event_type=iv.event_type,
        interval_days=iv.interval_days, notes=iv.notes,
        location_name=iv.location.name if iv.location else None,
    )

@router.delete("/health-intervals/{interval_id}")
async def delete_health_interval(
    interval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(HealthInterval).where(HealthInterval.id == interval_id))
    iv = result.scalar_one_or_none()
    if not iv:
        raise HTTPException(status_code=404, detail="Interval not found")
    await db.delete(iv)
    await db.commit()
    return {"message": "Interval deleted"}

@router.get("/farm-health/last-events", response_model=List[LastEventSummary])
async def get_last_events(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    loc_q = select(Location).where(Location.is_active == True)
    if location_id:
        loc_q = loc_q.where(Location.id == location_id)
    loc_result = await db.execute(loc_q)
    locations_map = {loc.id: loc for loc in loc_result.scalars().all()}
    if not locations_map:
        return []

    location_ids = list(locations_map.keys())

    interval_result = await db.execute(
        select(HealthInterval).where(HealthInterval.location_id.in_(location_ids))
    )
    intervals_map = {}
    for iv in interval_result.scalars().all():
        intervals_map[(iv.location_id, iv.species, iv.event_type)] = iv

    last_events_result = await db.execute(
        select(
            FarmHealthEventModel.location_id,
            FarmHealthEventModel.event_type,
            FarmHealthEventModel.species,
            func.max(FarmHealthEventModel.event_date).label("last_date"),
        )
        .where(FarmHealthEventModel.location_id.in_(location_ids))
        .group_by(
            FarmHealthEventModel.location_id,
            FarmHealthEventModel.event_type,
            FarmHealthEventModel.species,
        )
    )

    today = date.today()
    summaries = []
    seen = set()

    for row in last_events_result.fetchall():
        loc_id, evt_type, species_val, last_date = row[0], row[1], row[2], row[3]
        seen.add((loc_id, evt_type, species_val))

        iv = intervals_map.get((loc_id, species_val, evt_type))
        next_due = None
        if iv and last_date:
            next_due = last_date + timedelta(days=iv.interval_days)

        is_overdue = bool(next_due and today > next_due)
        days_overdue = (today - next_due).days if is_overdue else None

        summaries.append(LastEventSummary(
            location_id=loc_id,
            location_name=locations_map[loc_id].name,
            species=species_val,
            event_type=evt_type,
            last_date=last_date,
            next_due_date=next_due,
            is_overdue=is_overdue,
            days_overdue=days_overdue,
        ))

    for (loc_id, species_val, evt_type), iv in intervals_map.items():
        if (loc_id, evt_type, species_val) not in seen:
            summaries.append(LastEventSummary(
                location_id=loc_id,
                location_name=locations_map[loc_id].name,
                species=species_val,
                event_type=evt_type,
                last_date=None,
                next_due_date=None,
                is_overdue=True,
                days_overdue=None,
            ))

    return summaries

@router.get("/farm-health/upcoming", response_model=List[FarmHealthEventResponse])
async def get_upcoming_health_events(
    days: int = Query(30),
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    cutoff = today + timedelta(days=days)
    q = (
        select(FarmHealthEventModel)
        .options(selectinload(FarmHealthEventModel.location), selectinload(FarmHealthEventModel.creator))
        .where(and_(FarmHealthEventModel.next_due_date >= today, FarmHealthEventModel.next_due_date <= cutoff))
        .order_by(FarmHealthEventModel.next_due_date)
    )
    if location_id:
        q = q.where(FarmHealthEventModel.location_id == location_id)
    result = await db.execute(q)
    events = result.scalars().all()
    out = []
    for ev in events:
        cats = await _resolve_categories_for_event(db, ev.category_ids)
        out.append(_health_event_response(ev, cats))
    return out

@router.get("/farm-health/product-suggestions")
async def get_product_suggestions(
    event_type: Optional[HealthEventType] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(FarmHealthEventModel.product_name).where(FarmHealthEventModel.product_name.isnot(None))
    if event_type:
        q = q.where(FarmHealthEventModel.event_type == event_type)
    result = await db.execute(q.distinct().order_by(FarmHealthEventModel.product_name))
    return {"suggestions": [row[0] for row in result.fetchall()]}

@router.get("/farm-health", response_model=List[FarmHealthEventResponse])
async def list_farm_health_events(
    location_id: Optional[int] = Query(None),
    event_type: Optional[HealthEventType] = Query(None),
    species: Optional[SpeciesType] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(FarmHealthEventModel)
        .options(selectinload(FarmHealthEventModel.location), selectinload(FarmHealthEventModel.creator))
        .order_by(FarmHealthEventModel.event_date.desc(), FarmHealthEventModel.id.desc())
    )
    if location_id:
        q = q.where(FarmHealthEventModel.location_id == location_id)
    if event_type:
        q = q.where(FarmHealthEventModel.event_type == event_type)
    if species:
        q = q.where(FarmHealthEventModel.species == species)
    if date_from:
        q = q.where(FarmHealthEventModel.event_date >= date_from)
    if date_to:
        q = q.where(FarmHealthEventModel.event_date <= date_to)
    if overdue_only:
        q = q.where(FarmHealthEventModel.next_due_date < date.today())
    result = await db.execute(q.limit(limit).offset(offset))
    events = result.scalars().all()
    out = []
    for ev in events:
        cats = await _resolve_categories_for_event(db, ev.category_ids)
        out.append(_health_event_response(ev, cats))
    return out

@router.post("/farm-health", response_model=FarmHealthEventResponse)
async def create_farm_health_event(
    data: FarmHealthEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    if data.event_type != HealthEventType.LOG:
        if not data.species:
            raise HTTPException(status_code=400, detail="species is required for non-LOG events")
        if not data.product_name:
            raise HTTPException(status_code=400, detail="product_name is required for non-LOG events")
        if not data.category_scope:
            raise HTTPException(status_code=400, detail="category_scope is required for non-LOG events")
        if data.category_scope == CategoryScope.SPECIFIC:
            if not data.category_ids:
                raise HTTPException(status_code=400, detail="category_ids required when category_scope is SPECIFIC")
            bad = await db.execute(
                select(Category).where(
                    and_(Category.id.in_(data.category_ids), Category.species != data.species)
                )
            )
            if bad.scalars().first():
                raise HTTPException(status_code=400, detail="Some category IDs do not belong to the specified species")

    # Compute next_due_date with vaccine-type-aware logic
    if data.next_due_date is not None:
        next_due = data.next_due_date
    elif data.event_type == HealthEventType.VACCINATION and data.vaccine_type_id is not None:
        vt_r = await db.execute(select(VaccineType).where(VaccineType.id == data.vaccine_type_id))
        vt = vt_r.scalar_one_or_none()
        next_due = (data.event_date + timedelta(days=vt.default_interval_days)) if (vt and vt.default_interval_days) else None
    else:
        next_due = await _compute_next_due(db, data.location_id, data.species, data.event_type, data.event_date)

    ev = FarmHealthEventModel(
        location_id=data.location_id,
        event_type=data.event_type,
        event_date=data.event_date,
        species=data.species,
        category_scope=data.category_scope,
        category_ids=data.category_ids,
        product_name=data.product_name,
        dosage=data.dosage,
        cost_per_head=data.cost_per_head,
        total_cost=data.total_cost,
        head_count=data.head_count,
        next_due_date=next_due,
        notes=data.notes,
        created_by=current_user.id,
        vaccine_type_id=data.vaccine_type_id,
    )
    db.add(ev)
    await db.commit()

    result = await db.execute(
        select(FarmHealthEventModel)
        .options(
            selectinload(FarmHealthEventModel.location),
            selectinload(FarmHealthEventModel.creator),
            selectinload(FarmHealthEventModel.vaccine_type),
        )
        .where(FarmHealthEventModel.id == ev.id)
    )
    ev = result.scalar_one()
    cats = await _resolve_categories_for_event(db, ev.category_ids)
    vt_name = ev.vaccine_type.name if ev.vaccine_type else None
    return _health_event_response(ev, cats, vaccine_type_name=vt_name)

@router.get("/farm-health/{event_id}", response_model=FarmHealthEventResponse)
async def get_farm_health_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(FarmHealthEventModel)
        .options(selectinload(FarmHealthEventModel.location), selectinload(FarmHealthEventModel.creator))
        .where(FarmHealthEventModel.id == event_id)
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Health event not found")
    cats = await _resolve_categories_for_event(db, ev.category_ids)
    return _health_event_response(ev, cats)

@router.put("/farm-health/{event_id}", response_model=FarmHealthEventResponse)
async def update_farm_health_event(
    event_id: int,
    data: FarmHealthEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(FarmHealthEventModel).where(FarmHealthEventModel.id == event_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Health event not found")

    if data.event_date is not None:
        ev.event_date = data.event_date
    if data.species is not None:
        ev.species = data.species
    if data.category_scope is not None:
        ev.category_scope = data.category_scope
    if data.category_ids is not None:
        ev.category_ids = data.category_ids
    if data.product_name is not None:
        ev.product_name = data.product_name
    if data.dosage is not None:
        ev.dosage = data.dosage
    if data.cost_per_head is not None:
        ev.cost_per_head = data.cost_per_head
    if data.total_cost is not None:
        ev.total_cost = data.total_cost
    if data.head_count is not None:
        ev.head_count = data.head_count
    if data.notes is not None:
        ev.notes = data.notes
    if data.vaccine_type_id is not None:
        ev.vaccine_type_id = data.vaccine_type_id

    # Compute next_due_date with vaccine-type-aware logic
    if data.next_due_date is not None:
        ev.next_due_date = data.next_due_date
    elif ev.event_type == HealthEventType.VACCINATION and ev.vaccine_type_id is not None:
        vt_r = await db.execute(select(VaccineType).where(VaccineType.id == ev.vaccine_type_id))
        vt = vt_r.scalar_one_or_none()
        ev.next_due_date = (ev.event_date + timedelta(days=vt.default_interval_days)) if (vt and vt.default_interval_days) else None
    else:
        ev.next_due_date = await _compute_next_due(db, ev.location_id, ev.species, ev.event_type, ev.event_date)

    await db.commit()

    result = await db.execute(
        select(FarmHealthEventModel)
        .options(
            selectinload(FarmHealthEventModel.location),
            selectinload(FarmHealthEventModel.creator),
            selectinload(FarmHealthEventModel.vaccine_type),
        )
        .where(FarmHealthEventModel.id == event_id)
    )
    ev = result.scalar_one()
    cats = await _resolve_categories_for_event(db, ev.category_ids)
    vt_name = ev.vaccine_type.name if ev.vaccine_type else None
    return _health_event_response(ev, cats, vaccine_type_name=vt_name)

@router.delete("/farm-health/{event_id}")
async def delete_farm_health_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(FarmHealthEventModel).where(FarmHealthEventModel.id == event_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Health event not found")
    await db.delete(ev)
    await db.commit()
    return {"message": "Health event deleted"}
