"""Locations (farms)."""
from typing import List

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Location, User, UserRole
from schemas import LocationCreate, LocationResponse, LocationUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# ==================== LOCATION ROUTES ====================
@router.get("/locations", response_model=List[LocationResponse])
async def list_locations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    result = await db.execute(select(Location).where(Location.is_active == True).order_by(Location.name))
    locations = result.scalars().all()
    return [LocationResponse.model_validate(loc) for loc in locations]

@router.get("/locations/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    result = await db.execute(select(Location).where(Location.id == location_id))
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return LocationResponse.model_validate(location)

@router.post("/locations", response_model=LocationResponse)
async def create_location(
    data: LocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    location = Location(
        name=data.name,
        description=data.description,
        created_by=current_user.id
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return LocationResponse.model_validate(location)

@router.put("/locations/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: int,
    data: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    result = await db.execute(select(Location).where(Location.id == location_id))
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    if data.name is not None:
        location.name = data.name
    if data.description is not None:
        location.description = data.description
    if data.is_active is not None:
        location.is_active = data.is_active
    
    location.updated_by = current_user.id
    await db.commit()
    await db.refresh(location)
    return LocationResponse.model_validate(location)
