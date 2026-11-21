"""Categories and diseases."""
from typing import List, Optional

from auth import get_current_user, require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Category, Disease, SpeciesType, User, UserRole
from schemas import CategoryResponse, DiseaseCreate, DiseaseResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# ==================== CATEGORY ROUTES ====================
@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    query = select(Category).where(Category.is_active == True)
    if species:
        query = query.where(Category.species == species)
    query = query.order_by(Category.species, Category.sort_order)
    
    result = await db.execute(query)
    categories = result.scalars().all()
    return [CategoryResponse.model_validate(cat) for cat in categories]

# ==================== DISEASE ROUTES ====================
@router.get("/diseases", response_model=List[DiseaseResponse])
async def list_diseases(
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    """List all diseases, optionally filtered by species"""
    query = select(Disease).where(Disease.is_active == True)
    if species:
        query = query.where(or_(Disease.species == species, Disease.species == None))
    query = query.order_by(Disease.name)
    
    result = await db.execute(query)
    diseases = result.scalars().all()
    return [DiseaseResponse.model_validate(d) for d in diseases]

@router.post("/diseases", response_model=DiseaseResponse)
async def create_disease(
    disease: DiseaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new disease (admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if disease already exists
    result = await db.execute(select(Disease).where(Disease.name == disease.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Disease already exists")
    
    db_disease = Disease(
        name=disease.name,
        description=disease.description,
        species=disease.species
    )
    db.add(db_disease)
    await db.commit()
    await db.refresh(db_disease)
    return DiseaseResponse.model_validate(db_disease)

@router.delete("/diseases/{disease_id}")
async def delete_disease(
    disease_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a disease (admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.execute(select(Disease).where(Disease.id == disease_id))
    disease = result.scalar_one_or_none()
    if not disease:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    disease.is_active = False
    await db.commit()
    return {"message": "Disease deleted"}

@router.put("/diseases/{disease_id}", response_model=DiseaseResponse)
async def update_disease(
    disease_id: int,
    data: DiseaseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a disease (admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.execute(select(Disease).where(Disease.id == disease_id))
    disease = result.scalar_one_or_none()
    if not disease:
        raise HTTPException(status_code=404, detail="Disease not found")
    
    disease.name = data.name
    disease.description = data.description
    disease.species = data.species
    
    await db.commit()
    await db.refresh(disease)
    return DiseaseResponse.model_validate(disease)
