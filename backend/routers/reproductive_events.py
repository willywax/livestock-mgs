"""Standalone reproductive events and status sync."""
from datetime import date
from typing import List

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Animal, AnimalSex, PDResult, ReproductiveEvent, ReproductiveEventType, SpeciesType, User, UserRole
from schemas import ReproductiveEventCreate, ReproductiveEventResponse, ReproductiveSummaryResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import BREEDING_AGE_MONTHS, REPEAT_BREEDER_THRESHOLD, _ANY_ROLE
from services.reproduction import _apply_reproductive_status
from services.transitions import _maybe_first_calving_transition

router = APIRouter()

# ---------- Standalone reproductive events ----------


async def _reproductive_animal(db, animal_id):
    animal = (await db.execute(select(Animal).where(Animal.id == animal_id).with_for_update())).scalar_one_or_none()
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    return animal


@router.post("/animals/{animal_id}/reproductive-events", response_model=ReproductiveEventResponse)
async def create_reproductive_event(
    animal_id: int,
    data: ReproductiveEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    # Serialize saves for one animal so concurrent services do not lose increments.
    await _reproductive_animal(db, animal_id)
    if data.event_type == ReproductiveEventType.SERVICE and data.bull_animal_id is not None:
        if await db.get(Animal, data.bull_animal_id) is None:
            raise HTTPException(status_code=404, detail="Bull animal not found")
    values = data.model_dump()
    if data.pd_result is not None:
        values["pd_result"] = PDResult.REPEAT if data.pd_result == "recheck" else PDResult(data.pd_result)
    event = ReproductiveEvent(**values, animal_id=animal_id, recorded_by=current_user.id)
    db.add(event)
    await db.flush()
    await _apply_reproductive_status(db, animal_id, event)
    if event.event_type == ReproductiveEventType.CALVING:
        await _maybe_first_calving_transition(db, animal_id, current_user.id)
    await db.commit()
    await db.refresh(event)
    return ReproductiveEventResponse.model_validate(event)


@router.get("/animals/{animal_id}/reproductive-events", response_model=List[ReproductiveEventResponse])
async def list_reproductive_events(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    if await db.get(Animal, animal_id) is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    events = (await db.execute(select(ReproductiveEvent).where(ReproductiveEvent.animal_id == animal_id)
                              .order_by(ReproductiveEvent.event_date.desc(), ReproductiveEvent.id.desc()))).scalars().all()
    return [ReproductiveEventResponse.model_validate(event) for event in events]


@router.get("/animals/{animal_id}/reproductive-summary", response_model=ReproductiveSummaryResponse)
async def reproductive_summary(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    animal = await db.get(Animal, animal_id)
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    events = (await db.execute(select(ReproductiveEvent).where(ReproductiveEvent.animal_id == animal_id)
                              .order_by(ReproductiveEvent.event_date.desc(), ReproductiveEvent.id.desc())
                              .limit(5))).scalars().all()
    services = animal.services_without_conception or 0
    return ReproductiveSummaryResponse(
        status=animal.reproductive_status or "unknown", last_calving_date=animal.last_calving_date,
        last_pd_date=animal.last_pd_date, months_pregnant=animal.months_pregnant,
        services_without_conception=services, is_repeat_breeder=services >= REPEAT_BREEDER_THRESHOLD,
        events=[ReproductiveEventResponse.model_validate(event) for event in events],
    )


@router.post("/admin/tasks/sync-reproductive-status")
async def sync_reproductive_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    animals = (await db.execute(select(Animal).where(
        Animal.sex == AnimalSex.FEMALE, Animal.reproductive_status == "unknown",
        Animal.birth_date.isnot(None),
    ).with_for_update())).scalars().all()
    today = date.today()
    updated = 0
    for animal in animals:
        born = animal.birth_date
        age_months = (today.year - born.year) * 12 + today.month - born.month - (today.day < born.day)
        species_key = "goats" if animal.species == SpeciesType.GOAT else animal.species.value
        if age_months >= BREEDING_AGE_MONTHS[species_key]:
            animal.reproductive_status = "open"
            updated += 1
    await db.commit()
    return {"updated": updated}
