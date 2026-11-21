"""Reproductive cycles and the animal reproductive history."""
import logging
from datetime import date, timedelta
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Animal, AnimalSex, BullAssignment, CalvingOutcome, ReproductiveCycle, ReproductiveCycleStatus, User, UserRole
from schemas import AnimalReproductiveSummary, ReproductiveCycleCreate, ReproductiveCycleResponse, ReproductiveCycleUpdate
from sqlalchemy import and_, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import GESTATION_DAYS, _ANY_ROLE, _CYCLE_LOAD, _require_animal, _to_decimal
from services.reproduction import _sync_cycle_calving_status

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------- Reproductive cycles ----------

_CYCLE_NON_NULL = ("service_type", "status")  # an explicit null in a PUT is ignored for these


def _cycle_response(c: ReproductiveCycle) -> ReproductiveCycleResponse:
    resp = ReproductiveCycleResponse.model_validate(c)
    resp.animal_tag_number = c.animal.tag_number if c.animal else None
    resp.location_name = c.animal.location.name if c.animal and c.animal.location else None
    ba = c.bull_assignment
    resp.bull_tag_number = ba.bull.tag_number if ba and ba.bull else None
    return resp


async def _load_cycle(db: AsyncSession, cycle_id: int) -> ReproductiveCycle:
    result = await db.execute(
        select(ReproductiveCycle).options(*_CYCLE_LOAD).where(ReproductiveCycle.id == cycle_id)
    )
    cycle = result.scalar_one_or_none()
    if not cycle:
        raise HTTPException(status_code=404, detail="Reproductive cycle not found")
    return cycle


async def _check_cycle_refs(
    db: AsyncSession, bull_assignment_id: Optional[int], calf_animal_id: Optional[int]
) -> None:
    if bull_assignment_id is not None:
        found = await db.execute(select(BullAssignment.id).where(BullAssignment.id == bull_assignment_id))
        if found.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Bull assignment not found")
    if calf_animal_id is not None:
        await _require_animal(db, calf_animal_id)


async def _recompute_cycle_fields(db: AsyncSession, cycle: ReproductiveCycle) -> None:
    """calving_interval_days / days_to_service from the previous cycle's actual calving date."""
    result = await db.execute(
        select(ReproductiveCycle.actual_calving_date)
        .where(and_(
            ReproductiveCycle.animal_id == cycle.animal_id,
            ReproductiveCycle.cycle_number < cycle.cycle_number,
            ReproductiveCycle.actual_calving_date.isnot(None),
        ))
        .order_by(ReproductiveCycle.cycle_number.desc())
        .limit(1)
    )
    prev = result.scalar_one_or_none()
    cycle.calving_interval_days = (
        (cycle.actual_calving_date - prev).days if prev and cycle.actual_calving_date else None
    )
    cycle.days_to_service = (cycle.service_date - prev).days if prev and cycle.service_date else None


async def _refresh_following_cycles(db: AsyncSession, animal_id: int, after_number: int) -> None:
    result = await db.execute(
        select(ReproductiveCycle)
        .where(and_(ReproductiveCycle.animal_id == animal_id, ReproductiveCycle.cycle_number > after_number))
        .order_by(ReproductiveCycle.cycle_number)
    )
    for later in result.scalars().all():
        await _recompute_cycle_fields(db, later)


async def _sync_lifetime_calvings(animal_id: int, db: AsyncSession) -> None:
    """Recount animals.lifetime_calvings from reproductive_cycles (abortions excluded).

    Best-effort: never raises; failures are logged as warnings. The UPDATE runs in a
    savepoint so a failure cannot poison the caller's transaction.
    """
    try:
        async with db.begin_nested():
            await db.execute(
                text(
                    "UPDATE animals SET lifetime_calvings = ("
                    "SELECT COUNT(*) FROM reproductive_cycles "
                    "WHERE animal_id = :animal_id "
                    "AND calving_outcome IN ('LIVE_CALF','STILLBIRTH','ASSISTED_LIVE','ASSISTED_DEAD')"
                    "), updated_at = CURRENT_TIMESTAMP WHERE id = :animal_id"
                ),
                {"animal_id": animal_id},
            )
        await db.commit()
    except Exception as exc:
        logger.warning("lifetime_calvings sync failed for animal %s: %s", animal_id, exc)


@router.get("/reproductive-cycles", response_model=List[ReproductiveCycleResponse])
async def list_reproductive_cycles(
    animal_id: Optional[int] = None,
    location_id: Optional[int] = None,
    status: Optional[ReproductiveCycleStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    """date_from/date_to filter on the cycle's first set date (service, PD check or calving)."""
    query = select(ReproductiveCycle).join(Animal, Animal.id == ReproductiveCycle.animal_id).options(*_CYCLE_LOAD)
    if animal_id:
        query = query.where(ReproductiveCycle.animal_id == animal_id)
    if location_id:
        query = query.where(Animal.location_id == location_id)
    if status:
        query = query.where(ReproductiveCycle.status == status)
    if date_from or date_to:
        cycle_date = func.coalesce(
            ReproductiveCycle.service_date, ReproductiveCycle.pd_check_date, ReproductiveCycle.actual_calving_date
        )
        if date_from:
            query = query.where(cycle_date >= date_from)
        if date_to:
            query = query.where(cycle_date <= date_to)
    query = query.order_by(ReproductiveCycle.animal_id, ReproductiveCycle.cycle_number)
    result = await db.execute(query)
    return [_cycle_response(c) for c in result.scalars().all()]


@router.post("/reproductive-cycles", response_model=ReproductiveCycleResponse)
async def create_reproductive_cycle(
    data: ReproductiveCycleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(
        db, data.animal_id, AnimalSex.FEMALE, "Reproductive cycles can only be recorded for female animals"
    )
    await _check_cycle_refs(db, data.bull_assignment_id, data.calf_animal_id)
    max_number = (await db.execute(
        select(func.max(ReproductiveCycle.cycle_number)).where(ReproductiveCycle.animal_id == data.animal_id)
    )).scalar()
    values = data.model_dump()
    values["bcs_at_service"] = _to_decimal(values["bcs_at_service"])
    values["bcs_at_calving"] = _to_decimal(values["bcs_at_calving"])
    if values["service_date"] and not values["expected_calving_date"]:
        values["expected_calving_date"] = values["service_date"] + timedelta(days=GESTATION_DAYS)
    cycle = ReproductiveCycle(**values, cycle_number=(max_number or 0) + 1, created_by=current_user.id)
    db.add(cycle)
    await db.flush()
    await _recompute_cycle_fields(db, cycle)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cycle number conflict, please retry")
    if cycle.actual_calving_date:
        await _sync_cycle_calving_status(db, cycle)
        await db.commit()
    if cycle.calving_outcome is not None:
        await _sync_lifetime_calvings(cycle.animal_id, db)
    return _cycle_response(await _load_cycle(db, cycle.id))


@router.get("/reproductive-cycles/{cycle_id}", response_model=ReproductiveCycleResponse)
async def get_reproductive_cycle(
    cycle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return _cycle_response(await _load_cycle(db, cycle_id))


@router.put("/reproductive-cycles/{cycle_id}", response_model=ReproductiveCycleResponse)
async def update_reproductive_cycle(
    cycle_id: int,
    data: ReproductiveCycleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    cycle = await _load_cycle(db, cycle_id)
    changes = {k: getattr(data, k) for k in data.model_fields_set}
    for key in _CYCLE_NON_NULL:
        if changes.get(key, 0) is None:
            changes.pop(key)
    await _check_cycle_refs(db, changes.get("bull_assignment_id"), changes.get("calf_animal_id"))
    for key in ("bcs_at_service", "bcs_at_calving"):
        if key in changes:
            changes[key] = _to_decimal(changes[key])
    for key, value in changes.items():
        setattr(cycle, key, value)
    if "service_date" in changes and "expected_calving_date" not in changes and cycle.service_date:
        cycle.expected_calving_date = cycle.service_date + timedelta(days=GESTATION_DAYS)
    if "service_date" in changes or "actual_calving_date" in changes:
        await _recompute_cycle_fields(db, cycle)
        await _refresh_following_cycles(db, cycle.animal_id, cycle.cycle_number)
    await db.commit()
    if changes.get("actual_calving_date"):
        await _sync_cycle_calving_status(db, cycle)
        await db.commit()
    if "calving_outcome" in changes:
        await _sync_lifetime_calvings(cycle.animal_id, db)
    return _cycle_response(await _load_cycle(db, cycle_id))


@router.delete("/reproductive-cycles/{cycle_id}")
async def delete_reproductive_cycle(
    cycle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    cycle = await _load_cycle(db, cycle_id)
    animal_id, number = cycle.animal_id, cycle.cycle_number
    await db.delete(cycle)
    await db.flush()
    await _refresh_following_cycles(db, animal_id, number)
    await db.commit()
    await _sync_lifetime_calvings(animal_id, db)
    return {"message": "Reproductive cycle deleted"}


@router.get("/animals/{animal_id}/reproductive-history", response_model=AnimalReproductiveSummary)
async def get_animal_reproductive_history(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    animal = await _require_animal(db, animal_id)
    result = await db.execute(
        select(ReproductiveCycle).options(*_CYCLE_LOAD)
        .where(ReproductiveCycle.animal_id == animal_id)
        .order_by(ReproductiveCycle.cycle_number)
    )
    cycles = result.scalars().all()
    calved = [c for c in cycles if c.actual_calving_date and c.calving_outcome != CalvingOutcome.ABORTION]
    intervals = [c.calving_interval_days for c in calved if c.calving_interval_days is not None]
    return AnimalReproductiveSummary(
        animal_id=animal.id,
        tag_number=animal.tag_number,
        total_calvings=len(calved),
        avg_interval_days=round(sum(intervals) / len(intervals), 1) if intervals else None,
        last_calving_date=max((c.actual_calving_date for c in calved), default=None),
        current_status=cycles[-1].status if cycles else None,
        cycles=[_cycle_response(c) for c in cycles],
    )
