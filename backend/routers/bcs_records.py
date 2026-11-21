"""Body-condition-score records."""
from datetime import date
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Animal, BCSRecord, User, UserRole
from schemas import BCSRecordCreate, BCSRecordResponse, BCSRecordUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.common import _ANY_ROLE, _require_animal, _to_decimal

router = APIRouter()

# ---------- BCS records ----------
def _bcs_response(r: BCSRecord) -> BCSRecordResponse:
    resp = BCSRecordResponse.model_validate(r)
    resp.animal_tag_number = r.animal.tag_number if r.animal else None
    return resp


async def _load_bcs(db: AsyncSession, record_id: int) -> BCSRecord:
    result = await db.execute(
        select(BCSRecord).options(selectinload(BCSRecord.animal)).where(BCSRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="BCS record not found")
    return record


@router.get("/bcs-records", response_model=List[BCSRecordResponse])
async def list_bcs_records(
    animal_id: Optional[int] = None,
    location_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    query = select(BCSRecord).join(Animal, Animal.id == BCSRecord.animal_id).options(selectinload(BCSRecord.animal))
    if animal_id:
        query = query.where(BCSRecord.animal_id == animal_id)
    if location_id:
        query = query.where(Animal.location_id == location_id)
    if date_from:
        query = query.where(BCSRecord.score_date >= date_from)
    if date_to:
        query = query.where(BCSRecord.score_date <= date_to)
    result = await db.execute(query.order_by(BCSRecord.score_date.desc(), BCSRecord.id.desc()))
    return [_bcs_response(r) for r in result.scalars().all()]


@router.post("/bcs-records", response_model=BCSRecordResponse)
async def create_bcs_record(
    data: BCSRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(db, data.animal_id)
    values = data.model_dump()
    values["bcs"] = _to_decimal(values["bcs"])
    record = BCSRecord(**values, created_by=current_user.id)
    db.add(record)
    await db.commit()
    return _bcs_response(await _load_bcs(db, record.id))


@router.put("/bcs-records/{record_id}", response_model=BCSRecordResponse)
async def update_bcs_record(
    record_id: int,
    data: BCSRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    record = await _load_bcs(db, record_id)
    for key in data.model_fields_set:
        value = getattr(data, key)
        if value is None and key in ("score_date", "bcs"):
            continue
        setattr(record, key, _to_decimal(value) if key == "bcs" else value)
    await db.commit()
    return _bcs_response(await _load_bcs(db, record_id))


@router.delete("/bcs-records/{record_id}")
async def delete_bcs_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    await db.delete(await _load_bcs(db, record_id))
    await db.commit()
    return {"message": "BCS record deleted"}
