"""Bull assignments."""
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import AnimalSex, BullAssignment, ReproductiveCycle, User, UserRole
from schemas import BullAssignmentCreate, BullAssignmentResponse, BullAssignmentUpdate
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.common import _ANY_ROLE, _require_animal, _require_location

router = APIRouter()

# ---------- Bull assignments ----------
_BA_LOAD = (selectinload(BullAssignment.bull), selectinload(BullAssignment.location))


def _ba_response(ba: BullAssignment) -> BullAssignmentResponse:
    return BullAssignmentResponse(
        id=ba.id, bull_animal_id=ba.bull_animal_id, location_id=ba.location_id,
        assigned_date=ba.assigned_date, removed_date=ba.removed_date, notes=ba.notes,
        created_at=ba.created_at,
        bull_tag_number=ba.bull.tag_number if ba.bull else None,
        bull_name=ba.bull.name if ba.bull else None,
        location_name=ba.location.name if ba.location else None,
    )


async def _load_bull_assignment(db: AsyncSession, ba_id: int) -> BullAssignment:
    result = await db.execute(
        select(BullAssignment).options(*_BA_LOAD).where(BullAssignment.id == ba_id)
    )
    ba = result.scalar_one_or_none()
    if not ba:
        raise HTTPException(status_code=404, detail="Bull assignment not found")
    return ba


@router.get("/bull-assignments", response_model=List[BullAssignmentResponse])
async def list_bull_assignments(
    location_id: Optional[int] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    query = select(BullAssignment).options(*_BA_LOAD)
    if location_id:
        query = query.where(BullAssignment.location_id == location_id)
    if active_only:
        query = query.where(BullAssignment.removed_date.is_(None))
    query = query.order_by(BullAssignment.assigned_date.desc(), BullAssignment.id.desc())
    result = await db.execute(query)
    return [_ba_response(ba) for ba in result.scalars().all()]


@router.post("/bull-assignments", response_model=BullAssignmentResponse)
async def create_bull_assignment(
    data: BullAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(db, data.bull_animal_id, AnimalSex.MALE, "Bull must be a male animal")
    await _require_location(db, data.location_id)
    if data.removed_date and data.removed_date < data.assigned_date:
        raise HTTPException(status_code=400, detail="removed_date cannot be before assigned_date")
    ba = BullAssignment(**data.model_dump(), created_by=current_user.id)
    db.add(ba)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This bull is already assigned to this location on that date")
    return _ba_response(await _load_bull_assignment(db, ba.id))


@router.put("/bull-assignments/{assignment_id}", response_model=BullAssignmentResponse)
async def update_bull_assignment(
    assignment_id: int,
    data: BullAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    ba = await _load_bull_assignment(db, assignment_id)
    changes = {k: getattr(data, k) for k in data.model_fields_set}
    for non_null in ("location_id", "assigned_date"):
        if changes.get(non_null, 0) is None:
            changes.pop(non_null)
    if "location_id" in changes:
        await _require_location(db, changes["location_id"])
    new_assigned = changes.get("assigned_date", ba.assigned_date)
    new_removed = changes.get("removed_date", ba.removed_date)
    if new_removed and new_removed < new_assigned:
        raise HTTPException(status_code=400, detail="removed_date cannot be before assigned_date")
    for key, value in changes.items():
        setattr(ba, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This bull is already assigned to this location on that date")
    return _ba_response(await _load_bull_assignment(db, assignment_id))


@router.delete("/bull-assignments/{assignment_id}")
async def delete_bull_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    ba = await _load_bull_assignment(db, assignment_id)
    refs = await db.execute(
        select(func.count(ReproductiveCycle.id)).where(ReproductiveCycle.bull_assignment_id == assignment_id)
    )
    if refs.scalar() > 0:
        raise HTTPException(status_code=409, detail="Bull assignment is referenced by reproductive cycles")
    await db.delete(ba)
    await db.commit()
    return {"message": "Bull assignment deleted"}
