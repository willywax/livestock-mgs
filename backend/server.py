from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import os
import logging
import csv
import io
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date, timezone, timedelta

from database import get_db, init_db, engine, Base
from models import (
    User, Location, Category, OpeningBalance, DailyLog, Event, StockLevel,
    UserRole, EventType, SpeciesType, Disease, AbortionStage
)
from schemas import (
    UserLogin, UserCreate, UserUpdate, UserResponse, TokenResponse,
    LocationCreate, LocationUpdate, LocationResponse,
    CategoryResponse,
    OpeningBalanceCreate, OpeningBalanceUpdate, OpeningBalanceResponse,
    DailyLogCreate, DailyLogResponse, EventCreate, EventResponse,
    StockLevelResponse, DashboardResponse, SpeciesTotals, LocationTotals, EventSummary,
    DateRangeReport, EventUpdate, SpeciesCategoryTotals, CategoryTotal,
    AnalyticsResponse, SpeciesRates, HerdPerformance, NetChange,
    DeathAnalysis, DeathBySpecies, DeathByCategory, DeathByCause, DeathByDisease,
    DiseaseCreate, DiseaseResponse,
    AbortionAnalysis, AbortionBySpecies, AbortionByStage,
    SalesAnalysis, SalesBySpecies, SalesByBuyer
)
from auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, require_roles
)
from seed_data import get_seed_categories, get_default_admin, get_sample_locations

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI(title="ShambaManager API", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Seed initial data
    async for db in get_db():
        # Check if categories exist
        result = await db.execute(select(func.count(Category.id)))
        count = result.scalar()
        if count == 0:
            categories = get_seed_categories()
            db.add_all(categories)
            await db.commit()
            logger.info("Seeded categories")
        
        # Check if admin exists
        result = await db.execute(select(func.count(User.id)))
        count = result.scalar()
        if count == 0:
            admin = get_default_admin()
            db.add(admin)
            await db.commit()
            logger.info("Created default admin user")
        break

@api_router.get("/")
async def root():
    return {"message": "ShambaManager API", "version": "1.0.0"}

# ==================== AUTH ROUTES ====================
@api_router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is disabled")
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user)
    )

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)

# ==================== USER ROUTES ====================
@api_router.get("/users", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    result = await db.execute(select(User).order_by(User.name))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]

@api_router.post("/users", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    # Check if phone exists
    result = await db.execute(select(User).where(User.phone == data.phone))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Phone number already registered")
    
    user = User(
        phone=data.phone,
        password_hash=get_password_hash(data.password),
        name=data.name,
        role=data.role
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)

@api_router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if data.name is not None:
        user.name = data.name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)

@api_router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.delete(user)
    await db.commit()
    return {"message": "User deleted"}

# ==================== LOCATION ROUTES ====================
@api_router.get("/locations", response_model=List[LocationResponse])
async def list_locations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Location).where(Location.is_active == True).order_by(Location.name))
    locations = result.scalars().all()
    return [LocationResponse.model_validate(loc) for loc in locations]

@api_router.get("/locations/{location_id}", response_model=LocationResponse)
async def get_location(location_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Location).where(Location.id == location_id))
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return LocationResponse.model_validate(location)

@api_router.post("/locations", response_model=LocationResponse)
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

@api_router.put("/locations/{location_id}", response_model=LocationResponse)
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

# ==================== IMPORT/EXPORT ROUTES ====================
@api_router.get("/templates/locations")
async def download_locations_template():
    """Download CSV template for importing locations"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'description'])
    writer.writerow(['Shamba Kuu', 'Main farm headquarters'])
    writer.writerow(['Shamba Kaskazini', 'Northern branch'])
    writer.writerow(['Shamba Kusini', 'Southern branch'])
    
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=locations_template.csv'}
    )

@api_router.get("/templates/opening-balances")
async def download_opening_balances_template(db: AsyncSession = Depends(get_db)):
    """Download CSV template for importing opening balances"""
    # Get all locations and categories for reference
    loc_result = await db.execute(select(Location).where(Location.is_active == True))
    locations = loc_result.scalars().all()
    
    cat_result = await db.execute(select(Category).where(Category.is_active == True).order_by(Category.species, Category.sort_order))
    categories = cat_result.scalars().all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['location_name', 'species', 'category_name_sw', 'count', 'period_start'])
    
    # Sample rows for each species
    sample_location = locations[0].name if locations else 'Shamba Kuu'
    writer.writerow([sample_location, 'cattle', 'Koo', '100', '2026-01-01'])
    writer.writerow([sample_location, 'cattle', 'Mitamba', '50', '2026-01-01'])
    writer.writerow([sample_location, 'cattle', 'Ndama Dume', '20', '2026-01-01'])
    writer.writerow([sample_location, 'sheep', 'Koo', '80', '2026-01-01'])
    writer.writerow([sample_location, 'goat', 'Koo', '60', '2026-01-01'])
    
    # Add reference sheet
    writer.writerow([])
    writer.writerow(['# REFERENCE - Available Locations:'])
    for loc in locations:
        writer.writerow([f'# {loc.name}'])
    
    writer.writerow([])
    writer.writerow(['# REFERENCE - Available Categories by Species:'])
    current_species = None
    for cat in categories:
        if cat.species != current_species:
            current_species = cat.species
            writer.writerow([f'# {cat.species.value.upper()}:'])
        writer.writerow([f'#   {cat.name_sw} ({cat.name_en})'])
    
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=opening_balances_template.csv'}
    )

@api_router.post("/import/locations")
async def import_locations(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    """Import locations from CSV file"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))
    
    created = 0
    skipped = 0
    errors = []
    
    for row_num, row in enumerate(reader, start=2):
        try:
            name = row.get('name', '').strip()
            description = row.get('description', '').strip()
            
            if not name:
                errors.append(f"Row {row_num}: Name is required")
                continue
            
            # Check if location exists
            result = await db.execute(select(Location).where(Location.name == name))
            existing = result.scalar_one_or_none()
            
            if existing:
                skipped += 1
                continue
            
            location = Location(
                name=name,
                description=description or None,
                created_by=current_user.id
            )
            db.add(location)
            created += 1
            
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    await db.commit()
    
    return {
        "message": f"Import complete. Created: {created}, Skipped (duplicates): {skipped}",
        "created": created,
        "skipped": skipped,
        "errors": errors
    }

@api_router.post("/import/opening-balances")
async def import_opening_balances(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    """Import opening balances from CSV file"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))
    
    # Pre-load locations and categories for lookup
    loc_result = await db.execute(select(Location))
    locations = {loc.name.lower(): loc for loc in loc_result.scalars().all()}
    
    cat_result = await db.execute(select(Category))
    categories = {}
    for cat in cat_result.scalars().all():
        key = (cat.species.value, cat.name_sw.lower())
        categories[key] = cat
    
    created = 0
    updated = 0
    errors = []
    
    for row_num, row in enumerate(reader, start=2):
        try:
            # Skip comment/reference rows
            location_name = row.get('location_name', '').strip()
            if location_name.startswith('#') or not location_name:
                continue
            
            species_str = row.get('species', '').strip().lower()
            category_name = row.get('category_name_sw', '').strip()
            count_str = row.get('count', '0').strip()
            period_start_str = row.get('period_start', '').strip()
            
            # Validate location
            location = locations.get(location_name.lower())
            if not location:
                errors.append(f"Row {row_num}: Location '{location_name}' not found")
                continue
            
            # Validate species
            try:
                species = SpeciesType(species_str)
            except ValueError:
                errors.append(f"Row {row_num}: Invalid species '{species_str}'. Use: cattle, sheep, goat")
                continue
            
            # Validate category
            cat_key = (species_str, category_name.lower())
            category = categories.get(cat_key)
            if not category:
                errors.append(f"Row {row_num}: Category '{category_name}' not found for {species_str}")
                continue
            
            # Parse count
            try:
                count = int(count_str)
            except ValueError:
                errors.append(f"Row {row_num}: Invalid count '{count_str}'")
                continue
            
            # Parse date
            try:
                period_start = datetime.strptime(period_start_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append(f"Row {row_num}: Invalid date format '{period_start_str}'. Use YYYY-MM-DD")
                continue
            
            # Check if balance exists
            result = await db.execute(
                select(OpeningBalance).where(
                    and_(
                        OpeningBalance.location_id == location.id,
                        OpeningBalance.species == species,
                        OpeningBalance.category_id == category.id,
                        OpeningBalance.period_start == period_start
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.count = count
                existing.updated_by = current_user.id
                updated += 1
            else:
                balance = OpeningBalance(
                    location_id=location.id,
                    species=species,
                    category_id=category.id,
                    count=count,
                    period_start=period_start,
                    created_by=current_user.id
                )
                db.add(balance)
                
                # Also create/update stock level
                stock_result = await db.execute(
                    select(StockLevel).where(
                        and_(
                            StockLevel.location_id == location.id,
                            StockLevel.species == species,
                            StockLevel.category_id == category.id
                        )
                    )
                )
                stock = stock_result.scalar_one_or_none()
                if stock:
                    stock.current_count = count
                else:
                    stock = StockLevel(
                        location_id=location.id,
                        species=species,
                        category_id=category.id,
                        current_count=count
                    )
                    db.add(stock)
                
                created += 1
                
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    await db.commit()
    
    return {
        "message": f"Import complete. Created: {created}, Updated: {updated}",
        "created": created,
        "updated": updated,
        "errors": errors
    }

# ==================== CATEGORY ROUTES ====================
@api_router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Category).where(Category.is_active == True)
    if species:
        query = query.where(Category.species == species)
    query = query.order_by(Category.species, Category.sort_order)
    
    result = await db.execute(query)
    categories = result.scalars().all()
    return [CategoryResponse.model_validate(cat) for cat in categories]

# ==================== DISEASE ROUTES ====================
@api_router.get("/diseases", response_model=List[DiseaseResponse])
async def list_diseases(
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all diseases, optionally filtered by species"""
    query = select(Disease).where(Disease.is_active == True)
    if species:
        query = query.where(or_(Disease.species == species, Disease.species == None))
    query = query.order_by(Disease.name)
    
    result = await db.execute(query)
    diseases = result.scalars().all()
    return [DiseaseResponse.model_validate(d) for d in diseases]

@api_router.post("/diseases", response_model=DiseaseResponse)
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

@api_router.delete("/diseases/{disease_id}")
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

@api_router.put("/diseases/{disease_id}", response_model=DiseaseResponse)
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

# ==================== OPENING BALANCE ROUTES ====================
@api_router.get("/opening-balances", response_model=List[OpeningBalanceResponse])
async def list_opening_balances(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db)
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

@api_router.post("/opening-balances", response_model=OpeningBalanceResponse)
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

@api_router.put("/opening-balances/{balance_id}", response_model=OpeningBalanceResponse)
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

# ==================== DAILY LOG ROUTES ====================
@api_router.get("/daily-logs", response_model=List[DailyLogResponse])
async def list_daily_logs(
    location_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(DailyLog).options(
        selectinload(DailyLog.location),
        selectinload(DailyLog.events)
    )
    
    if location_id:
        query = query.where(DailyLog.location_id == location_id)
    if start_date:
        query = query.where(DailyLog.log_date >= start_date)
    if end_date:
        query = query.where(DailyLog.log_date <= end_date)
    
    query = query.order_by(DailyLog.log_date.desc())
    result = await db.execute(query)
    logs = result.scalars().all()
    
    response = []
    for log in logs:
        events = []
        for e in log.events:
            events.append(EventResponse(
                id=e.id,
                event_type=e.event_type,
                species=e.species,
                category_id=e.category_id,
                count=e.count,
                from_location_id=e.from_location_id,
                to_location_id=e.to_location_id,
                from_category_id=e.from_category_id,
                to_category_id=e.to_category_id,
                notes=e.notes,
                is_stock_event=e.is_stock_event,
                created_at=e.created_at
            ))
        
        response.append(DailyLogResponse(
            id=log.id,
            location_id=log.location_id,
            log_date=log.log_date,
            has_events=log.has_events,
            notes=log.notes,
            is_locked=log.is_locked,
            created_at=log.created_at,
            location_name=log.location.name if log.location else None,
            events=events
        ))
    
    return response

@api_router.get("/daily-logs/{log_id}", response_model=DailyLogResponse)
async def get_daily_log(log_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DailyLog)
        .options(selectinload(DailyLog.location), selectinload(DailyLog.events))
        .where(DailyLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Daily log not found")
    
    # Get category and location names for events
    events = []
    for e in log.events:
        # Fetch related names
        cat_name = None
        from_cat_name = None
        to_cat_name = None
        from_loc_name = None
        to_loc_name = None
        
        if e.category_id:
            cat_result = await db.execute(select(Category).where(Category.id == e.category_id))
            cat = cat_result.scalar_one_or_none()
            cat_name = cat.name_sw if cat else None
        
        if e.from_category_id:
            cat_result = await db.execute(select(Category).where(Category.id == e.from_category_id))
            cat = cat_result.scalar_one_or_none()
            from_cat_name = cat.name_sw if cat else None
        
        if e.to_category_id:
            cat_result = await db.execute(select(Category).where(Category.id == e.to_category_id))
            cat = cat_result.scalar_one_or_none()
            to_cat_name = cat.name_sw if cat else None
        
        if e.from_location_id:
            loc_result = await db.execute(select(Location).where(Location.id == e.from_location_id))
            loc = loc_result.scalar_one_or_none()
            from_loc_name = loc.name if loc else None
        
        if e.to_location_id:
            loc_result = await db.execute(select(Location).where(Location.id == e.to_location_id))
            loc = loc_result.scalar_one_or_none()
            to_loc_name = loc.name if loc else None
        
        # Get disease name if disease_id exists
        disease_name = None
        if e.disease_id:
            disease_result = await db.execute(select(Disease).where(Disease.id == e.disease_id))
            disease = disease_result.scalar_one_or_none()
            disease_name = disease.name if disease else None
        
        events.append(EventResponse(
            id=e.id,
            event_type=e.event_type,
            species=e.species,
            category_id=e.category_id,
            count=e.count,
            from_location_id=e.from_location_id,
            to_location_id=e.to_location_id,
            from_category_id=e.from_category_id,
            to_category_id=e.to_category_id,
            notes=e.notes,
            is_stock_event=e.is_stock_event,
            created_at=e.created_at,
            category_name_sw=cat_name,
            from_category_name_sw=from_cat_name,
            to_category_name_sw=to_cat_name,
            from_location_name=from_loc_name,
            to_location_name=to_loc_name,
            animal_tags=e.animal_tags,
            cause_of_death=e.cause_of_death,
            disease_id=e.disease_id,
            disease_name=disease_name,
            days_sick=e.days_sick,
            attending_vet=e.attending_vet,
            abortion_stage=e.abortion_stage,
            mother_tag=e.mother_tag,
            offspring_tags=e.offspring_tags,
            buyer_name=e.buyer_name,
            buyer_phone=e.buyer_phone,
            buyer_address=e.buyer_address,
            sale_price=e.sale_price
        ))
    
    return DailyLogResponse(
        id=log.id,
        location_id=log.location_id,
        log_date=log.log_date,
        has_events=log.has_events,
        notes=log.notes,
        is_locked=log.is_locked,
        created_at=log.created_at,
        location_name=log.location.name if log.location else None,
        events=events
    )

@api_router.post("/daily-logs", response_model=DailyLogResponse)
async def create_daily_log(
    data: DailyLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY))
):
    # Check if log exists for this date/location
    result = await db.execute(
        select(DailyLog).where(
            and_(
                DailyLog.location_id == data.location_id,
                DailyLog.log_date == data.log_date
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="A daily log already exists for this date and location")
    
    # Create the daily log
    daily_log = DailyLog(
        location_id=data.location_id,
        log_date=data.log_date,
        has_events=len(data.events) > 0,
        notes=data.notes,
        created_by=current_user.id
    )
    db.add(daily_log)
    await db.flush()
    
    # Process events
    for event_data in data.events:
        # Validate stock before creating event
        if event_data.is_stock_event and event_data.event_type not in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
            # Check if we have enough stock
            can_proceed, message = await check_stock_availability(
                db, data.location_id, event_data, current_user.role == UserRole.ADMIN
            )
            if not can_proceed:
                raise HTTPException(status_code=400, detail=message)
        
        event = Event(
            daily_log_id=daily_log.id,
            event_type=event_data.event_type,
            species=event_data.species,
            category_id=event_data.category_id,
            count=event_data.count,
            from_location_id=event_data.from_location_id,
            to_location_id=event_data.to_location_id,
            from_category_id=event_data.from_category_id,
            to_category_id=event_data.to_category_id,
            notes=event_data.notes,
            is_stock_event=event_data.is_stock_event,
            # New fields
            animal_tags=event_data.animal_tags,
            cause_of_death=event_data.cause_of_death,
            disease_id=event_data.disease_id,
            days_sick=event_data.days_sick,
            attending_vet=event_data.attending_vet,
            abortion_stage=event_data.abortion_stage,
            mother_tag=event_data.mother_tag,
            offspring_tags=event_data.offspring_tags,
            buyer_name=event_data.buyer_name,
            buyer_phone=event_data.buyer_phone,
            buyer_address=event_data.buyer_address,
            sale_price=event_data.sale_price,
            created_by=current_user.id
        )
        db.add(event)
        
        # Update stock levels
        if event_data.is_stock_event:
            await apply_event_to_stock(db, data.location_id, event_data)
    
    await db.commit()
    await db.refresh(daily_log)
    
    return DailyLogResponse(
        id=daily_log.id,
        location_id=daily_log.location_id,
        log_date=daily_log.log_date,
        has_events=daily_log.has_events,
        notes=daily_log.notes,
        is_locked=daily_log.is_locked,
        created_at=daily_log.created_at,
        events=[]
    )

@api_router.post("/daily-logs/{log_id}/lock")
async def lock_daily_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.VIEWER))
):
    result = await db.execute(select(DailyLog).where(DailyLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Daily log not found")
    
    log.is_locked = True
    log.locked_by = current_user.id
    log.locked_at = datetime.now(timezone.utc)
    
    await db.commit()
    return {"message": "Daily log locked"}

# ==================== EVENT ROUTES (Admin Only) ====================
@api_router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int,
    data: EventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    """Update an event - Admin only. Reverses old stock changes and applies new ones."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.daily_log))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Admin can edit even locked logs
    location_id = event.daily_log.location_id
    
    # Reverse the old stock changes if it was a stock event
    if event.is_stock_event:
        old_event_data = EventCreate(
            event_type=event.event_type,
            species=event.species,
            category_id=event.category_id,
            count=event.count,
            from_location_id=event.from_location_id,
            to_location_id=event.to_location_id,
            from_category_id=event.from_category_id,
            to_category_id=event.to_category_id,
            is_stock_event=True
        )
        await reverse_event_stock(db, location_id, old_event_data)
    
    # Update event fields
    if data.event_type is not None:
        event.event_type = data.event_type
    if data.species is not None:
        event.species = data.species
    if data.category_id is not None:
        event.category_id = data.category_id
    if data.count is not None:
        event.count = data.count
    if data.from_location_id is not None:
        event.from_location_id = data.from_location_id
    if data.to_location_id is not None:
        event.to_location_id = data.to_location_id
    if data.from_category_id is not None:
        event.from_category_id = data.from_category_id
    if data.to_category_id is not None:
        event.to_category_id = data.to_category_id
    if data.notes is not None:
        event.notes = data.notes
    # New fields
    if data.animal_tags is not None:
        event.animal_tags = data.animal_tags
    if data.cause_of_death is not None:
        event.cause_of_death = data.cause_of_death
    if data.days_sick is not None:
        event.days_sick = data.days_sick
    if data.attending_vet is not None:
        event.attending_vet = data.attending_vet
    if data.mother_tag is not None:
        event.mother_tag = data.mother_tag
    if data.offspring_tags is not None:
        event.offspring_tags = data.offspring_tags
    if data.buyer_name is not None:
        event.buyer_name = data.buyer_name
    if data.buyer_phone is not None:
        event.buyer_phone = data.buyer_phone
    if data.buyer_address is not None:
        event.buyer_address = data.buyer_address
    if data.sale_price is not None:
        event.sale_price = data.sale_price
    
    # Apply new stock changes
    if event.is_stock_event:
        new_event_data = EventCreate(
            event_type=event.event_type,
            species=event.species,
            category_id=event.category_id,
            count=event.count,
            from_location_id=event.from_location_id,
            to_location_id=event.to_location_id,
            from_category_id=event.from_category_id,
            to_category_id=event.to_category_id,
            is_stock_event=True
        )
        await apply_event_to_stock(db, location_id, new_event_data)
    
    await db.commit()
    await db.refresh(event)
    
    return EventResponse(
        id=event.id,
        event_type=event.event_type,
        species=event.species,
        category_id=event.category_id,
        count=event.count,
        from_location_id=event.from_location_id,
        to_location_id=event.to_location_id,
        from_category_id=event.from_category_id,
        to_category_id=event.to_category_id,
        notes=event.notes,
        is_stock_event=event.is_stock_event,
        created_at=event.created_at,
        animal_tags=event.animal_tags,
        cause_of_death=event.cause_of_death,
        days_sick=event.days_sick,
        attending_vet=event.attending_vet,
        mother_tag=event.mother_tag,
        offspring_tags=event.offspring_tags,
        buyer_name=event.buyer_name,
        buyer_phone=event.buyer_phone,
        buyer_address=event.buyer_address,
        sale_price=event.sale_price
    )

@api_router.delete("/events/{event_id}")
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    """Delete an event - Admin only. Reverses stock changes."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.daily_log))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Admin can delete even from locked logs
    location_id = event.daily_log.location_id
    daily_log = event.daily_log
    
    # Reverse the stock changes if it was a stock event
    if event.is_stock_event:
        event_data = EventCreate(
            event_type=event.event_type,
            species=event.species,
            category_id=event.category_id,
            count=event.count,
            from_location_id=event.from_location_id,
            to_location_id=event.to_location_id,
            from_category_id=event.from_category_id,
            to_category_id=event.to_category_id,
            is_stock_event=True
        )
        await reverse_event_stock(db, location_id, event_data)
    
    await db.delete(event)
    
    # Update daily log has_events flag
    result = await db.execute(
        select(func.count(Event.id)).where(Event.daily_log_id == daily_log.id)
    )
    remaining_events = result.scalar()
    if remaining_events == 0:
        daily_log.has_events = False
    
    await db.commit()
    return {"message": "Event deleted successfully"}

# ==================== STOCK LEVEL ROUTES ====================
@api_router.get("/stock-levels", response_model=List[StockLevelResponse])
async def list_stock_levels(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db)
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

# ==================== DASHBOARD ROUTES ====================
@api_router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)
    
    # Get location info if filtered
    selected_location = None
    selected_location_name = None
    if location_id:
        loc_result = await db.execute(select(Location).where(Location.id == location_id))
        selected_location = loc_result.scalar_one_or_none()
        if selected_location:
            selected_location_name = selected_location.name
    
    # Get species totals
    species_totals = []
    species_colors = {
        SpeciesType.CATTLE: "#2D5A27",
        SpeciesType.GOAT: "#D97706",
        SpeciesType.SHEEP: "#0284C7"
    }
    
    for sp in SpeciesType:
        query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(StockLevel.species == sp)
        if location_id:
            query = query.where(StockLevel.location_id == location_id)
        result = await db.execute(query)
        total = result.scalar() or 0
        species_totals.append(SpeciesTotals(
            species=sp,
            total=total,
            color=species_colors.get(sp, "#666666")
        ))
    
    # Get location totals (only if not filtering by location)
    result = await db.execute(select(Location).where(Location.is_active == True))
    locations = result.scalars().all()
    
    location_totals = []
    for loc in locations:
        # Skip if filtering by a different location
        if location_id and loc.id != location_id:
            continue
            
        cattle_total = 0
        sheep_total = 0
        goat_total = 0
        
        for sp in SpeciesType:
            result = await db.execute(
                select(func.coalesce(func.sum(StockLevel.current_count), 0))
                .where(and_(
                    StockLevel.location_id == loc.id,
                    StockLevel.species == sp
                ))
            )
            total = result.scalar() or 0
            
            if sp == SpeciesType.CATTLE:
                cattle_total = total
            elif sp == SpeciesType.SHEEP:
                sheep_total = total
            elif sp == SpeciesType.GOAT:
                goat_total = total
        
        location_totals.append(LocationTotals(
            location_id=loc.id,
            location_name=loc.name,
            cattle=cattle_total,
            sheep=sheep_total,
            goat=goat_total,
            total=cattle_total + sheep_total + goat_total
        ))
    
    # Get today's events
    events_query = select(DailyLog).options(selectinload(DailyLog.events)).where(DailyLog.log_date == today)
    if location_id:
        events_query = events_query.where(DailyLog.location_id == location_id)
    result = await db.execute(events_query)
    today_logs = result.scalars().all()
    
    events_summary = {}
    for log in today_logs:
        for event in log.events:
            if event.event_type not in events_summary:
                events_summary[event.event_type] = {"count": 0, "stock_change": 0}
            events_summary[event.event_type]["count"] += 1
            
            if event.is_stock_event:
                if event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
                    events_summary[event.event_type]["stock_change"] += event.count
                elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
                    events_summary[event.event_type]["stock_change"] -= event.count
    
    today_events = [
        EventSummary(event_type=et, count=data["count"], stock_change=data["stock_change"])
        for et, data in events_summary.items()
    ]
    
    # Get category totals per species
    species_category_totals = []
    for sp in SpeciesType:
        # Get all stock levels for this species with category info
        cat_query = select(StockLevel).options(selectinload(StockLevel.category)).where(StockLevel.species == sp)
        if location_id:
            cat_query = cat_query.where(StockLevel.location_id == location_id)
        result = await db.execute(cat_query)
        stock_levels = result.scalars().all()
        
        # Aggregate by category
        category_counts = {}
        for sl in stock_levels:
            if sl.category_id not in category_counts:
                category_counts[sl.category_id] = {
                    "name_sw": sl.category.name_sw if sl.category else "Unknown",
                    "count": 0
                }
            category_counts[sl.category_id]["count"] += sl.current_count
        
        categories_list = [
            CategoryTotal(
                category_id=cat_id,
                category_name_sw=data["name_sw"],
                count=data["count"]
            )
            for cat_id, data in category_counts.items()
            if data["count"] > 0
        ]
        
        species_total = sum(c.count for c in categories_list)
        
        species_category_totals.append(SpeciesCategoryTotals(
            species=sp,
            categories=categories_list,
            total=species_total
        ))
    
    # Calculate herd performance indicators (last 30 days)
    herd_performance = []
    
    # Get events from last 30 days
    perf_query = select(Event).join(DailyLog).where(DailyLog.log_date >= thirty_days_ago)
    if location_id:
        perf_query = perf_query.where(DailyLog.location_id == location_id)
    result = await db.execute(perf_query)
    recent_events = result.scalars().all()
    
    for sp in SpeciesType:
        # Get total stock for this species
        stock_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(StockLevel.species == sp)
        if location_id:
            stock_query = stock_query.where(StockLevel.location_id == location_id)
        result = await db.execute(stock_query)
        total_stock = result.scalar() or 0
        
        # Get breeding females (Koo category)
        koo_result = await db.execute(
            select(Category).where(and_(Category.species == sp, Category.name_sw == "Koo"))
        )
        koo_category = koo_result.scalar_one_or_none()
        
        breeding_females = 0
        if koo_category:
            bf_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                and_(StockLevel.species == sp, StockLevel.category_id == koo_category.id)
            )
            if location_id:
                bf_query = bf_query.where(StockLevel.location_id == location_id)
            result = await db.execute(bf_query)
            breeding_females = result.scalar() or 0
        
        # Count events for this species
        births_30d = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.BIRTH)
        deaths_30d = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.DEATH)
        
        # Calculate rates
        mortality_rate = (deaths_30d / total_stock * 100) if total_stock > 0 else 0
        calving_rate = (births_30d / breeding_females * 100) if breeding_females > 0 else 0
        
        herd_performance.append(HerdPerformance(
            species=sp,
            total_stock=total_stock,
            breeding_females=breeding_females,
            births_30d=births_30d,
            deaths_30d=deaths_30d,
            calving_rate=round(calving_rate, 1),
            mortality_rate=round(mortality_rate, 1),
            color=species_colors.get(sp, "#666666")
        ))
    
    # Calculate net changes (last 30 days)
    net_changes = []
    for sp in SpeciesType:
        births = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.BIRTH)
        deaths = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.DEATH)
        bought = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.BOUGHT)
        sold = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.SOLD)
        gift_in = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.GIFT_IN)
        gift_out = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.GIFT_OUT)
        missing = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.MISSING)
        weaned = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.WEANING)
        
        net_change = births + bought + gift_in - deaths - sold - gift_out - missing
        
        net_changes.append(NetChange(
            species=sp,
            births=births,
            deaths=deaths,
            bought=bought,
            sold=sold,
            gift_in=gift_in,
            gift_out=gift_out,
            missing=missing,
            weaned=weaned,
            net_change=net_change
        ))
    
    # Calculate totals
    total_animals = sum(st.total for st in species_totals)
    total_locations = len(locations)
    
    # Pending logs (locations without a log today)
    pending_query = select(func.count(DailyLog.id)).where(DailyLog.log_date == today)
    if location_id:
        pending_query = pending_query.where(DailyLog.location_id == location_id)
    result = await db.execute(pending_query)
    logs_today = result.scalar() or 0
    pending_logs_today = (1 if location_id else total_locations) - logs_today
    
    return DashboardResponse(
        species_totals=species_totals,
        species_category_totals=species_category_totals,
        location_totals=location_totals,
        today_events=today_events,
        total_animals=total_animals,
        total_locations=total_locations,
        pending_logs_today=max(0, pending_logs_today),
        herd_performance=herd_performance,
        net_changes=net_changes,
        selected_location_id=location_id,
        selected_location_name=selected_location_name
    )

# ==================== REPORTS ROUTES ====================
@api_router.get("/reports/daily")
async def get_daily_report(
    report_date: date = None,
    db: AsyncSession = Depends(get_db)
):
    if not report_date:
        report_date = date.today()
    
    # Get all logs for the date
    result = await db.execute(
        select(DailyLog)
        .options(selectinload(DailyLog.location), selectinload(DailyLog.events))
        .where(DailyLog.log_date == report_date)
    )
    logs = result.scalars().all()
    
    # Get current stock levels
    result = await db.execute(
        select(StockLevel)
        .options(selectinload(StockLevel.location), selectinload(StockLevel.category))
    )
    stock_levels = result.scalars().all()
    
    # Organize stock by location and species
    stock_by_location = {}
    for sl in stock_levels:
        loc_name = sl.location.name if sl.location else "Unknown"
        if loc_name not in stock_by_location:
            stock_by_location[loc_name] = {"cattle": 0, "sheep": 0, "goat": 0}
        stock_by_location[loc_name][sl.species.value] += sl.current_count
    
    # Organize events
    events_by_location = {}
    for log in logs:
        loc_name = log.location.name if log.location else "Unknown"
        if loc_name not in events_by_location:
            events_by_location[loc_name] = []
        
        for event in log.events:
            events_by_location[loc_name].append({
                "type": event.event_type.value,
                "species": event.species.value,
                "count": event.count,
                "notes": event.notes
            })
    
    return {
        "date": report_date.isoformat(),
        "stock_by_location": stock_by_location,
        "events_by_location": events_by_location,
        "total_logs": len(logs)
    }

@api_router.get("/reports/range")
async def get_range_report(
    start_date: date,
    end_date: date,
    event_type: Optional[EventType] = None,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Event).join(DailyLog).where(
        and_(
            DailyLog.log_date >= start_date,
            DailyLog.log_date <= end_date
        )
    )
    
    if event_type:
        query = query.where(Event.event_type == event_type)
    if location_id:
        query = query.where(DailyLog.location_id == location_id)
    
    result = await db.execute(query)
    events = result.scalars().all()
    
    # Aggregate by event type
    events_by_type = {}
    net_movements = {"cattle": 0, "sheep": 0, "goat": 0}
    
    for event in events:
        et = event.event_type.value
        if et not in events_by_type:
            events_by_type[et] = {"count": 0, "total_animals": 0}
        events_by_type[et]["count"] += 1
        events_by_type[et]["total_animals"] += event.count
        
        if event.is_stock_event:
            species_key = event.species.value
            if event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
                net_movements[species_key] += event.count
            elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
                net_movements[species_key] -= event.count
    
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "events_by_type": events_by_type,
        "net_movements": net_movements,
        "total_events": len(events)
    }

@api_router.get("/reports/analytics", response_model=AnalyticsResponse)
async def get_analytics_report(
    start_date: date,
    end_date: date,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get mortality rate, calving rate, weaning rate, death/abortion/sales analysis for a date range"""
    
    # Get location info if filtered
    location_name = None
    if location_id:
        loc_result = await db.execute(select(Location).where(Location.id == location_id))
        loc = loc_result.scalar_one_or_none()
        if loc:
            location_name = loc.name
    
    species_colors = {
        SpeciesType.CATTLE: "#2D5A27",
        SpeciesType.GOAT: "#D97706",
        SpeciesType.SHEEP: "#0284C7"
    }
    
    # Get all events in date range with category info
    events_query = (
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.disease))
        .join(DailyLog)
        .where(and_(DailyLog.log_date >= start_date, DailyLog.log_date <= end_date))
    )
    if location_id:
        events_query = events_query.where(DailyLog.location_id == location_id)
    result = await db.execute(events_query)
    events = result.scalars().all()
    
    # Get current stock levels for each species
    species_data = {}
    net_changes_list = []
    
    for sp in SpeciesType:
        # Get total stock
        stock_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(StockLevel.species == sp)
        if location_id:
            stock_query = stock_query.where(StockLevel.location_id == location_id)
        result = await db.execute(stock_query)
        total_stock = result.scalar() or 0
        
        # Count events for this species
        births = sum(e.count for e in events if e.species == sp and e.event_type == EventType.BIRTH)
        deaths = sum(e.count for e in events if e.species == sp and e.event_type == EventType.DEATH)
        weaned = sum(e.count for e in events if e.species == sp and e.event_type == EventType.WEANING)
        sold = sum(e.count for e in events if e.species == sp and e.event_type == EventType.SOLD)
        bought = sum(e.count for e in events if e.species == sp and e.event_type == EventType.BOUGHT)
        gift_in = sum(e.count for e in events if e.species == sp and e.event_type == EventType.GIFT_IN)
        gift_out = sum(e.count for e in events if e.species == sp and e.event_type == EventType.GIFT_OUT)
        missing = sum(e.count for e in events if e.species == sp and e.event_type == EventType.MISSING)
        
        # Get breeding female count (Koo category) for calving rate
        breeding_females = 0
        result = await db.execute(
            select(Category).where(and_(Category.species == sp, Category.name_sw == "Koo"))
        )
        bf_category = result.scalar_one_or_none()
        if bf_category:
            bf_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                and_(StockLevel.species == sp, StockLevel.category_id == bf_category.id)
            )
            if location_id:
                bf_query = bf_query.where(StockLevel.location_id == location_id)
            result = await db.execute(bf_query)
            breeding_females = result.scalar() or 0
        
        # Calculate rates
        mortality_rate = (deaths / total_stock * 100) if total_stock > 0 else 0
        calving_rate = (births / breeding_females * 100) if breeding_females > 0 else 0
        weaning_rate = (weaned / births * 100) if births > 0 else 0
        
        species_data[sp] = SpeciesRates(
            species=sp,
            total_stock=total_stock,
            breeding_females=breeding_females,
            births=births,
            deaths=deaths,
            weaned=weaned,
            sold=sold,
            bought=bought,
            calving_rate=round(calving_rate, 2),
            mortality_rate=round(mortality_rate, 2),
            weaning_rate=round(weaning_rate, 2),
            color=species_colors.get(sp, "#666666")
        )
        
        # Net change calculation
        net_change = births + bought + gift_in - deaths - sold - gift_out - missing
        net_changes_list.append(NetChange(
            species=sp,
            births=births,
            deaths=deaths,
            bought=bought,
            sold=sold,
            gift_in=gift_in,
            gift_out=gift_out,
            missing=missing,
            weaned=weaned,
            net_change=net_change
        ))
    
    # ===== DETAILED DEATH ANALYSIS =====
    death_events = [e for e in events if e.event_type == EventType.DEATH]
    total_deaths = sum(e.count for e in death_events)
    
    # Aggregate death causes
    death_causes_dict = {}
    for event in death_events:
        cause = event.cause_of_death or "Unknown"
        if cause not in death_causes_dict:
            death_causes_dict[cause] = {"count": 0, "days_sick_sum": 0, "days_sick_count": 0}
        death_causes_dict[cause]["count"] += event.count
        if event.days_sick is not None:
            death_causes_dict[cause]["days_sick_sum"] += event.days_sick * event.count
            death_causes_dict[cause]["days_sick_count"] += event.count
    
    top_causes = []
    for cause, data in sorted(death_causes_dict.items(), key=lambda x: x[1]["count"], reverse=True):
        avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
        top_causes.append(DeathByCause(
            cause=cause,
            count=data["count"],
            percentage=round((data["count"] / total_deaths * 100) if total_deaths > 0 else 0, 1),
            avg_days_sick=round(avg_days, 1) if avg_days else None
        ))
    
    # Aggregate diseases
    disease_dict = {}
    for event in death_events:
        if event.disease_id and event.disease:
            d_id = event.disease_id
            if d_id not in disease_dict:
                disease_dict[d_id] = {"name": event.disease.name, "count": 0, "days_sick_sum": 0, "days_sick_count": 0}
            disease_dict[d_id]["count"] += event.count
            if event.days_sick is not None:
                disease_dict[d_id]["days_sick_sum"] += event.days_sick * event.count
                disease_dict[d_id]["days_sick_count"] += event.count
    
    top_diseases = []
    for d_id, data in sorted(disease_dict.items(), key=lambda x: x[1]["count"], reverse=True):
        avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
        top_diseases.append(DeathByDisease(
            disease_id=d_id,
            disease_name=data["name"],
            count=data["count"],
            percentage=round((data["count"] / total_deaths * 100) if total_deaths > 0 else 0, 1),
            avg_days_sick=round(avg_days, 1) if avg_days else None
        ))
    
    # Death analysis by species
    deaths_by_species = []
    total_with_vet = sum(e.count for e in death_events if e.attending_vet)
    
    for sp in SpeciesType:
        sp_deaths = [e for e in death_events if e.species == sp]
        sp_total = sum(e.count for e in sp_deaths)
        
        if sp_total == 0:
            continue
        
        # By category
        cat_deaths = {}
        for e in sp_deaths:
            cat_id = e.category_id or 0
            cat_name = e.category.name_sw if e.category else "Unknown"
            if cat_id not in cat_deaths:
                cat_deaths[cat_id] = {"name_sw": cat_name, "count": 0}
            cat_deaths[cat_id]["count"] += e.count
        
        by_category = [
            DeathByCategory(category_id=cat_id, category_name_sw=data["name_sw"], count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1))
            for cat_id, data in sorted(cat_deaths.items(), key=lambda x: x[1]["count"], reverse=True)
        ]
        
        # By cause
        sp_causes = {}
        for e in sp_deaths:
            cause = e.cause_of_death or "Unknown"
            if cause not in sp_causes:
                sp_causes[cause] = {"count": 0, "days_sick_sum": 0, "days_sick_count": 0}
            sp_causes[cause]["count"] += e.count
            if e.days_sick is not None:
                sp_causes[cause]["days_sick_sum"] += e.days_sick * e.count
                sp_causes[cause]["days_sick_count"] += e.count
        
        by_cause = []
        for cause, data in sorted(sp_causes.items(), key=lambda x: x[1]["count"], reverse=True):
            avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
            by_cause.append(DeathByCause(cause=cause, count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1),
                avg_days_sick=round(avg_days, 1) if avg_days else None))
        
        # By disease for this species
        sp_disease_dict = {}
        for e in sp_deaths:
            if e.disease_id and e.disease:
                d_id = e.disease_id
                if d_id not in sp_disease_dict:
                    sp_disease_dict[d_id] = {"name": e.disease.name, "count": 0, "days_sick_sum": 0, "days_sick_count": 0}
                sp_disease_dict[d_id]["count"] += e.count
                if e.days_sick is not None:
                    sp_disease_dict[d_id]["days_sick_sum"] += e.days_sick * e.count
                    sp_disease_dict[d_id]["days_sick_count"] += e.count
        
        by_disease = []
        for d_id, data in sorted(sp_disease_dict.items(), key=lambda x: x[1]["count"], reverse=True):
            avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
            by_disease.append(DeathByDisease(disease_id=d_id, disease_name=data["name"], count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1),
                avg_days_sick=round(avg_days, 1) if avg_days else None))
        
        sp_with_vet = sum(e.count for e in sp_deaths if e.attending_vet)
        total_days = sum((e.days_sick or 0) * e.count for e in sp_deaths if e.days_sick is not None)
        days_count = sum(e.count for e in sp_deaths if e.days_sick is not None)
        sp_avg_days = (total_days / days_count) if days_count > 0 else None
        
        deaths_by_species.append(DeathBySpecies(
            species=sp, total_deaths=sp_total, by_category=by_category, by_cause=by_cause,
            by_disease=by_disease, with_vet_attendance=sp_with_vet,
            without_vet_attendance=sp_total - sp_with_vet,
            avg_days_sick=round(sp_avg_days, 1) if sp_avg_days else None
        ))
    
    vet_attendance_rate = (total_with_vet / total_deaths * 100) if total_deaths > 0 else 0
    death_analysis = DeathAnalysis(
        total_deaths=total_deaths, by_species=deaths_by_species, top_causes=top_causes,
        top_diseases=top_diseases, vet_attendance_rate=round(vet_attendance_rate, 1)
    )
    
    # ===== ABORTION ANALYSIS =====
    abortion_events = [e for e in events if e.event_type == EventType.ABORTION]
    total_abortions = sum(e.count for e in abortion_events)
    
    # Overall by stage
    stage_counts = {AbortionStage.EARLY: 0, AbortionStage.MID: 0, AbortionStage.LATE: 0}
    for e in abortion_events:
        if e.abortion_stage:
            stage_counts[e.abortion_stage] += e.count
    
    overall_by_stage = [
        AbortionByStage(stage=stage, count=count,
            percentage=round((count / total_abortions * 100) if total_abortions > 0 else 0, 1))
        for stage, count in stage_counts.items()
    ]
    
    # By species
    abortions_by_species = []
    for sp in SpeciesType:
        sp_abortions = [e for e in abortion_events if e.species == sp]
        sp_total = sum(e.count for e in sp_abortions)
        
        if sp_total == 0:
            continue
        
        # By stage for this species
        sp_stage_counts = {AbortionStage.EARLY: 0, AbortionStage.MID: 0, AbortionStage.LATE: 0}
        for e in sp_abortions:
            if e.abortion_stage:
                sp_stage_counts[e.abortion_stage] += e.count
        
        sp_by_stage = [
            AbortionByStage(stage=stage, count=count,
                percentage=round((count / sp_total * 100) if sp_total > 0 else 0, 1))
            for stage, count in sp_stage_counts.items()
        ]
        
        # By category
        cat_abortions = {}
        for e in sp_abortions:
            cat_id = e.category_id or 0
            cat_name = e.category.name_sw if e.category else "Unknown"
            if cat_id not in cat_abortions:
                cat_abortions[cat_id] = {"name_sw": cat_name, "count": 0}
            cat_abortions[cat_id]["count"] += e.count
        
        by_category = [
            DeathByCategory(category_id=cat_id, category_name_sw=data["name_sw"], count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1))
            for cat_id, data in sorted(cat_abortions.items(), key=lambda x: x[1]["count"], reverse=True)
        ]
        
        # Calculate abortion rate (abortions / breeding females)
        breeding_females = species_data[sp].breeding_females
        abortion_rate = (sp_total / breeding_females * 100) if breeding_females > 0 else 0
        
        abortions_by_species.append(AbortionBySpecies(
            species=sp, total_abortions=sp_total, by_stage=sp_by_stage,
            by_category=by_category, abortion_rate=round(abortion_rate, 2)
        ))
    
    abortion_analysis = AbortionAnalysis(
        total_abortions=total_abortions, by_species=abortions_by_species, by_stage=overall_by_stage
    )
    
    # ===== SALES ANALYSIS =====
    sale_events = [e for e in events if e.event_type == EventType.SOLD]
    total_sales_count = sum(e.count for e in sale_events)
    total_sales_value = sum(e.sale_price or 0 for e in sale_events if e.sale_price)
    avg_sale_price = (total_sales_value / total_sales_count) if total_sales_count > 0 else 0
    
    # By species
    sales_by_species = []
    for sp in SpeciesType:
        sp_sales = [e for e in sale_events if e.species == sp]
        sp_count = sum(e.count for e in sp_sales)
        sp_value = sum(e.sale_price or 0 for e in sp_sales if e.sale_price)
        sp_avg = (sp_value / sp_count) if sp_count > 0 else 0
        
        if sp_count == 0:
            continue
        
        # By category
        cat_sales = {}
        for e in sp_sales:
            cat_id = e.category_id or 0
            cat_name = e.category.name_sw if e.category else "Unknown"
            if cat_id not in cat_sales:
                cat_sales[cat_id] = {"category_name_sw": cat_name, "count": 0, "total_value": 0}
            cat_sales[cat_id]["count"] += e.count
            cat_sales[cat_id]["total_value"] += e.sale_price or 0
        
        by_category = []
        for cat_id, data in sorted(cat_sales.items(), key=lambda x: x[1]["count"], reverse=True):
            by_category.append({
                "category_name_sw": data["category_name_sw"],
                "count": data["count"],
                "total_value": data["total_value"],
                "avg_price": round(data["total_value"] / data["count"], 2) if data["count"] > 0 else 0
            })
        
        sales_by_species.append(SalesBySpecies(
            species=sp, count=sp_count, total_value=sp_value,
            average_price=round(sp_avg, 2), by_category=by_category
        ))
    
    # Top buyers
    buyer_dict = {}
    for e in sale_events:
        buyer = e.buyer_name or "Unknown"
        if buyer not in buyer_dict:
            buyer_dict[buyer] = {"count": 0, "total_value": 0, "species": {}}
        buyer_dict[buyer]["count"] += e.count
        buyer_dict[buyer]["total_value"] += e.sale_price or 0
        sp_name = e.species.value
        buyer_dict[buyer]["species"][sp_name] = buyer_dict[buyer]["species"].get(sp_name, 0) + e.count
    
    top_buyers = [
        SalesByBuyer(buyer_name=name, count=data["count"], total_value=data["total_value"],
            species_breakdown=data["species"])
        for name, data in sorted(buyer_dict.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    ]
    
    # Price range
    all_prices = [e.sale_price for e in sale_events if e.sale_price and e.sale_price > 0]
    price_range = {
        "min": min(all_prices) if all_prices else 0,
        "max": max(all_prices) if all_prices else 0,
        "median": sorted(all_prices)[len(all_prices)//2] if all_prices else 0
    }
    
    sales_analysis = SalesAnalysis(
        total_count=total_sales_count, total_value=total_sales_value,
        average_price=round(avg_sale_price, 2), by_species=sales_by_species,
        top_buyers=top_buyers, price_range=price_range
    )
    
    return AnalyticsResponse(
        period_start=start_date, period_end=end_date,
        species_rates=list(species_data.values()), death_analysis=death_analysis,
        abortion_analysis=abortion_analysis, sales_analysis=sales_analysis,
        net_changes=net_changes_list, location_id=location_id, location_name=location_name
    )

# ==================== HELPER FUNCTIONS ====================
async def check_stock_availability(
    db: AsyncSession,
    location_id: int,
    event_data: EventCreate,
    is_admin: bool
) -> tuple[bool, str]:
    """Check if there's enough stock for the operation"""
    
    if event_data.event_type == EventType.TRANSFER:
        # Check from_location stock
        result = await db.execute(
            select(StockLevel).where(
                and_(
                    StockLevel.location_id == event_data.from_location_id,
                    StockLevel.species == event_data.species,
                    StockLevel.category_id == event_data.category_id
                )
            )
        )
        stock = result.scalar_one_or_none()
        current = stock.current_count if stock else 0
        
        if current < event_data.count:
            if is_admin:
                return True, "Warning: Stock will go negative (Admin override)"
            return False, f"Insufficient stock: only {current} available at source location"
    
    elif event_data.event_type == EventType.CATEGORY_CHANGE:
        # Check from_category stock
        result = await db.execute(
            select(StockLevel).where(
                and_(
                    StockLevel.location_id == location_id,
                    StockLevel.species == event_data.species,
                    StockLevel.category_id == event_data.from_category_id
                )
            )
        )
        stock = result.scalar_one_or_none()
        current = stock.current_count if stock else 0
        
        if current < event_data.count:
            if is_admin:
                return True, "Warning: Stock will go negative (Admin override)"
            return False, f"Insufficient stock in source category: only {current} available"
    
    elif event_data.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
        result = await db.execute(
            select(StockLevel).where(
                and_(
                    StockLevel.location_id == location_id,
                    StockLevel.species == event_data.species,
                    StockLevel.category_id == event_data.category_id
                )
            )
        )
        stock = result.scalar_one_or_none()
        current = stock.current_count if stock else 0
        
        if current < event_data.count:
            if is_admin:
                return True, "Warning: Stock will go negative (Admin override)"
            return False, f"Insufficient stock: only {current} available"
    
    return True, ""

async def apply_event_to_stock(
    db: AsyncSession,
    location_id: int,
    event_data: EventCreate
):
    """Apply event changes to stock levels"""
    
    if event_data.event_type == EventType.TRANSFER:
        # Subtract from source location
        await adjust_stock(
            db,
            event_data.from_location_id,
            event_data.species,
            event_data.category_id,
            -event_data.count
        )
        # Add to destination location
        await adjust_stock(
            db,
            event_data.to_location_id,
            event_data.species,
            event_data.category_id,
            event_data.count
        )
    
    elif event_data.event_type == EventType.CATEGORY_CHANGE:
        # Subtract from source category
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.from_category_id,
            -event_data.count
        )
        # Add to destination category
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.to_category_id,
            event_data.count
        )
    
    elif event_data.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
        # Add stock
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.category_id,
            event_data.count
        )
    
    elif event_data.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
        # Remove stock
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.category_id,
            -event_data.count
        )

async def reverse_event_stock(
    db: AsyncSession,
    location_id: int,
    event_data: EventCreate
):
    """Reverse event changes to stock levels (used when editing/deleting events)"""
    
    if event_data.event_type == EventType.TRANSFER:
        # Add back to source location
        await adjust_stock(
            db,
            event_data.from_location_id,
            event_data.species,
            event_data.category_id,
            event_data.count
        )
        # Subtract from destination location
        await adjust_stock(
            db,
            event_data.to_location_id,
            event_data.species,
            event_data.category_id,
            -event_data.count
        )
    
    elif event_data.event_type == EventType.CATEGORY_CHANGE:
        # Add back to source category
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.from_category_id,
            event_data.count
        )
        # Subtract from destination category
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.to_category_id,
            -event_data.count
        )
    
    elif event_data.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
        # Reverse: subtract stock
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.category_id,
            -event_data.count
        )
    
    elif event_data.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
        # Reverse: add stock back
        await adjust_stock(
            db,
            location_id,
            event_data.species,
            event_data.category_id,
            event_data.count
        )

async def adjust_stock(
    db: AsyncSession,
    location_id: int,
    species: SpeciesType,
    category_id: int,
    adjustment: int
):
    """Adjust stock level by the given amount"""
    result = await db.execute(
        select(StockLevel).where(
            and_(
                StockLevel.location_id == location_id,
                StockLevel.species == species,
                StockLevel.category_id == category_id
            )
        )
    )
    stock = result.scalar_one_or_none()
    
    if stock:
        stock.current_count += adjustment
        stock.last_updated = datetime.now(timezone.utc)
    else:
        stock = StockLevel(
            location_id=location_id,
            species=species,
            category_id=category_id,
            current_count=max(0, adjustment)
        )
        db.add(stock)

async def update_stock_level(
    db: AsyncSession,
    location_id: int,
    species: SpeciesType,
    category_id: int
):
    """Recalculate stock level from opening balance + events"""
    # Get opening balance
    result = await db.execute(
        select(OpeningBalance).where(
            and_(
                OpeningBalance.location_id == location_id,
                OpeningBalance.species == species,
                OpeningBalance.category_id == category_id
            )
        ).order_by(OpeningBalance.period_start.desc())
    )
    opening = result.scalar_one_or_none()
    opening_count = opening.count if opening else 0
    
    # Get all events affecting this stock
    # This is simplified - in production you'd calculate from opening date
    result = await db.execute(
        select(StockLevel).where(
            and_(
                StockLevel.location_id == location_id,
                StockLevel.species == species,
                StockLevel.category_id == category_id
            )
        )
    )
    stock = result.scalar_one_or_none()
    
    if stock:
        stock.current_count = opening_count
        stock.last_updated = datetime.now(timezone.utc)
    else:
        stock = StockLevel(
            location_id=location_id,
            species=species,
            category_id=category_id,
            current_count=opening_count
        )
        db.add(stock)

# Include router
app.include_router(api_router)

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
