"""Stock level listing and recompute."""
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends
from models import SpeciesType, StockLevel, User, UserRole
from schemas import StockLevelResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.stock import recompute_stock_levels

router = APIRouter()

# ==================== STOCK LEVEL ROUTES ====================
@router.get("/stock-levels", response_model=List[StockLevelResponse])
async def list_stock_levels(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    query = select(StockLevel).options(
        selectinload(StockLevel.location),
        selectinload(StockLevel.category)
    )
    
    if location_id:
        query = query.where(StockLevel.location_id == location_id)
    if species:
        query = query.where(StockLevel.species == species)
    
    result = await db.execute(query)
    levels = result.scalars().all()
    
    return [
        StockLevelResponse(
            id=sl.id,
            location_id=sl.location_id,
            species=sl.species,
            category_id=sl.category_id,
            current_count=sl.current_count,
            last_updated=sl.last_updated,
            location_name=sl.location.name if sl.location else None,
            category_name_sw=sl.category.name_sw if sl.category else None
        )
        for sl in levels
    ]

@router.post("/stock-levels/recompute")
async def recompute_stock_levels_endpoint(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    updated = await recompute_stock_levels(db, location_id=location_id, species=species)
    await db.commit()
    return {"message": "Stock levels recomputed", "updated": updated}
