"""Shared constants and lookup helpers used by several routers."""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from models import Animal, AnimalSex, BullAssignment, Location, ReproductiveCycle, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

_ANY_ROLE = (UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)
GESTATION_DAYS = 283
BREEDING_AGE_MONTHS = {"cattle": 24, "sheep": 18, "goats": 18}
REPEAT_BREEDER_THRESHOLD = 3

def _to_decimal(value: Optional[float]) -> Optional[Decimal]:
    return None if value is None else Decimal(str(round(value, 1)))


async def _require_animal(
    db: AsyncSession, animal_id: int, sex: Optional[AnimalSex] = None, sex_detail: str = ""
) -> Animal:
    result = await db.execute(select(Animal).where(Animal.id == animal_id))
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    if sex is not None and animal.sex != sex:
        raise HTTPException(status_code=400, detail=sex_detail or f"Animal must be {sex.value}")
    return animal


async def _require_location(db: AsyncSession, location_id: int) -> None:
    result = await db.execute(select(Location.id).where(Location.id == location_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Location not found")


_CYCLE_LOAD = (
    selectinload(ReproductiveCycle.animal).selectinload(Animal.location),
    selectinload(ReproductiveCycle.bull_assignment).selectinload(BullAssignment.bull),
)
