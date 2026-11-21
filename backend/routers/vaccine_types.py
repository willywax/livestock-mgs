"""Vaccine types and last-vaccination summary."""
from datetime import date, datetime, timezone
from typing import List, Optional

from auth import get_current_user, require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models import FarmHealthEvent as FarmHealthEventModel, HealthEventType, User, UserRole, VaccineType
from schemas import LastVaccinationSummary, VaccineTypeCreate, VaccineTypeResponse, VaccineTypeUpdate
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()

# ==================== VACCINE TYPE ROUTES ====================

@router.get("/vaccine-types", response_model=List[VaccineTypeResponse])
async def list_vaccine_types(
    species: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(VaccineType).where(VaccineType.is_active == True).order_by(VaccineType.name)
    )
    vts = result.scalars().all()
    if species:
        su = species.upper()
        vts = [vt for vt in vts if vt.species_applicability is None or su in vt.species_applicability]
    return vts

@router.post("/vaccine-types", response_model=VaccineTypeResponse)
async def create_vaccine_type(
    data: VaccineTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = await db.execute(select(VaccineType).where(VaccineType.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Vaccine type '{data.name}' already exists")
    vt = VaccineType(
        name=data.name,
        description=data.description,
        species_applicability=data.species_applicability,
        default_interval_days=data.default_interval_days,
        created_by=current_user.id,
    )
    db.add(vt)
    await db.commit()
    await db.refresh(vt)
    return vt

@router.put("/vaccine-types/{vt_id}", response_model=VaccineTypeResponse)
async def update_vaccine_type(
    vt_id: int,
    data: VaccineTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(VaccineType).where(VaccineType.id == vt_id))
    vt = result.scalar_one_or_none()
    if not vt:
        raise HTTPException(status_code=404, detail="Vaccine type not found")
    if data.name is not None:
        vt.name = data.name
    if data.description is not None:
        vt.description = data.description
    if data.species_applicability is not None:
        vt.species_applicability = data.species_applicability
    if data.default_interval_days is not None:
        vt.default_interval_days = data.default_interval_days
    if data.is_active is not None:
        vt.is_active = data.is_active
    vt.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(vt)
    return vt

@router.delete("/vaccine-types/{vt_id}")
async def delete_vaccine_type(
    vt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(VaccineType).where(VaccineType.id == vt_id))
    vt = result.scalar_one_or_none()
    if not vt:
        raise HTTPException(status_code=404, detail="Vaccine type not found")
    in_use = await db.execute(
        select(func.count(FarmHealthEventModel.id)).where(FarmHealthEventModel.vaccine_type_id == vt_id)
    )
    if in_use.scalar() > 0:
        raise HTTPException(status_code=409, detail="Cannot delete: vaccine type is used in existing health events")
    vt.is_active = False
    vt.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Vaccine type deactivated"}

# Literal path — must be before any parameterised /farm-health/{id} routes
@router.get("/farm-health-events/last-vaccinations", response_model=List[LastVaccinationSummary])
async def get_last_vaccinations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get the most recent vaccination event ID per (location, species, vaccine_type)
    latest_ids_sq = (
        select(func.max(FarmHealthEventModel.id).label("max_id"))
        .where(
            and_(
                FarmHealthEventModel.event_type == HealthEventType.VACCINATION,
                FarmHealthEventModel.vaccine_type_id.isnot(None),
            )
        )
        .group_by(
            FarmHealthEventModel.location_id,
            FarmHealthEventModel.species,
            FarmHealthEventModel.vaccine_type_id,
        )
        .subquery()
    )

    result = await db.execute(
        select(FarmHealthEventModel)
        .options(
            selectinload(FarmHealthEventModel.location),
            selectinload(FarmHealthEventModel.vaccine_type),
        )
        .join(latest_ids_sq, FarmHealthEventModel.id == latest_ids_sq.c.max_id)
    )
    events = result.scalars().all()

    today = date.today()
    summaries = []
    for ev in events:
        days_since = (today - ev.event_date).days if ev.event_date else None
        is_overdue = bool(ev.next_due_date and today > ev.next_due_date)
        summaries.append(LastVaccinationSummary(
            location_id=ev.location_id,
            location_name=ev.location.name if ev.location else "",
            species=ev.species,
            vaccine_type_id=ev.vaccine_type_id,
            vaccine_type_name=ev.vaccine_type.name if ev.vaccine_type else "",
            last_event_date=ev.event_date,
            days_since=days_since,
            next_due_date=ev.next_due_date,
            is_overdue=is_overdue,
        ))

    def _sort_key(s):
        if s.is_overdue:
            return (0, s.next_due_date or date.min)
        if s.next_due_date:
            return (1, s.next_due_date)
        return (2, date.max)

    summaries.sort(key=_sort_key)
    return summaries
