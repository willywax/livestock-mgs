"""Opening balances."""
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import OpeningBalance, SpeciesType, User, UserRole
from schemas import OpeningBalanceCreate, OpeningBalanceResponse, OpeningBalanceUpdate
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.stock import update_stock_level

router = APIRouter()

# ==================== OPENING BALANCE ROUTES ====================
@router.get("/opening-balances", response_model=List[OpeningBalanceResponse])
async def list_opening_balances(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    query = select(OpeningBalance).options(
        selectinload(OpeningBalance.location),
        selectinload(OpeningBalance.category)
    )
    
    if location_id:
        query = query.where(OpeningBalance.location_id == location_id)
    if species:
        query = query.where(OpeningBalance.species == species)
    
    result = await db.execute(query)
    balances = result.scalars().all()
    
    return [
        OpeningBalanceResponse(
            id=b.id,
            location_id=b.location_id,
            species=b.species,
            category_id=b.category_id,
            count=b.count,
            period_start=b.period_start,
            location_name=b.location.name if b.location else None,
            category_name_sw=b.category.name_sw if b.category else None
        )
        for b in balances
    ]

@router.post("/opening-balances", response_model=OpeningBalanceResponse)
async def create_opening_balance(
    data: OpeningBalanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    # Check if already exists
    result = await db.execute(
        select(OpeningBalance).where(
            and_(
                OpeningBalance.location_id == data.location_id,
                OpeningBalance.species == data.species,
                OpeningBalance.category_id == data.category_id,
                OpeningBalance.period_start == data.period_start
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Opening balance already exists for this combination")
    
    balance = OpeningBalance(
        location_id=data.location_id,
        species=data.species,
        category_id=data.category_id,
        count=data.count,
        period_start=data.period_start,
        created_by=current_user.id
    )
    db.add(balance)
    await db.flush()
    
    # Also create/update stock level
    await update_stock_level(db, data.location_id, data.species, data.category_id)
    
    await db.commit()
    await db.refresh(balance)
    
    return OpeningBalanceResponse(
        id=balance.id,
        location_id=balance.location_id,
        species=balance.species,
        category_id=balance.category_id,
        count=balance.count,
        period_start=balance.period_start
    )

@router.put("/opening-balances/{balance_id}", response_model=OpeningBalanceResponse)
async def update_opening_balance(
    balance_id: int,
    data: OpeningBalanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    result = await db.execute(select(OpeningBalance).where(OpeningBalance.id == balance_id))
    balance = result.scalar_one_or_none()
    if not balance:
        raise HTTPException(status_code=404, detail="Opening balance not found")
    
    balance.count = data.count
    balance.updated_by = current_user.id
    
    # Recalculate stock level
    await update_stock_level(db, balance.location_id, balance.species, balance.category_id)
    
    await db.commit()
    await db.refresh(balance)
    
    return OpeningBalanceResponse(
        id=balance.id,
        location_id=balance.location_id,
        species=balance.species,
        category_id=balance.category_id,
        count=balance.count,
        period_start=balance.period_start
    )
