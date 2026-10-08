from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.orm import selectinload
import os
import logging
import csv
import io
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date, timezone, timedelta

from database import get_db, init_db, engine, Base
from models import (
    User, Location, Category, OpeningBalance, DailyLog, Event, StockLevel,
    UserRole, EventType, SpeciesType, Disease, AbortionStage,
    Animal, AnimalSex, AnimalAcquisitionType, AnimalStatus,
    HealthEventType, CategoryScope, HealthInterval, FarmHealthEvent as FarmHealthEventModel,
    VaccineType, RegistrySyncState,
)
from registry_client import RegistryClient, RegistryUnavailable
import registry_sync
import registry_report
from registry_sync import drain_outbox
from registry_auth import require_cloud_run_service_account
from schemas import (
    UserLogin, UserCreate, UserUpdate, UserResponse, TokenResponse,
    LocationCreate, LocationUpdate, LocationResponse,
    CategoryResponse,
    OpeningBalanceCreate, OpeningBalanceUpdate, OpeningBalanceResponse,
    DailyLogCreate, DailyLogUpdate, DailyLogResponse, EventCreate, EventResponse,
    StockLevelResponse, DashboardResponse, SpeciesTotals, LocationTotals, EventSummary,
    DateRangeReport, DetailedReportResponse, DetailedReportEvent, EventUpdate, SpeciesCategoryTotals, CategoryTotal,
    AnalyticsResponse, SpeciesRates, HerdPerformance, NetChange,
    DeathAnalysis, DeathBySpecies, DeathByCategory, DeathByCause, DeathByDisease, DeathByLocation,
    DiseaseCreate, DiseaseResponse,
    AbortionAnalysis, AbortionBySpecies, AbortionByStage,
    SalesAnalysis, SalesBySpecies, SalesByBuyer,
    AnimalCreate, AnimalUpdate, AnimalTransfer, AnimalResponse, BulkImportResult,
    AnimalAssignRegistryTag, UntaggedCalfResponse,
    HealthIntervalCreate, HealthIntervalUpdate, HealthIntervalResponse,
    FarmHealthEventCreate, FarmHealthEventUpdate, FarmHealthEventResponse,
    CategoryInfo, LastEventSummary,
    VaccineTypeCreate, VaccineTypeUpdate, VaccineTypeResponse,
    LastVaccinationSummary,
    SyncDrainResult, SyncReportResponse, OutboxIssueResponse,
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

def parse_cors_origins(raw_origins: Optional[str]) -> List[str]:
    if not raw_origins:
        return [
            "https://stocks.serengeti-ranching.com",
            "https://serengeti-ranching.com",
        ]

    origins = [
        origin.strip().strip('"').strip("'")
        for origin in raw_origins.split(',')
        if origin.strip().strip('"').strip("'")
    ]

    return origins or [
        "https://stocks.serengeti-ranching.com",
        "https://serengeti-ranching.com",
    ]

# CORS
allowed_origins = parse_cors_origins(os.environ.get('CORS_ORIGINS'))
logger.info("CORS allowed origins: %s", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add vaccine_type_id to farm_health_events if not already present.
        # IF NOT EXISTS makes this idempotent on every restart.
        await conn.execute(text(
            "ALTER TABLE farm_health_events "
            "ADD COLUMN IF NOT EXISTS vaccine_type_id INTEGER "
            "REFERENCES vaccine_types(id)"
        ))
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS gift_party_name VARCHAR(255)"
        ))
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS gift_party_phone VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS gift_reason TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE animals ADD COLUMN IF NOT EXISTS registry_tag_id VARCHAR(100)"
        ))
        # create_all() only creates brand-new tables, so the Column(index=True) above never
        # applies retroactively to the pre-existing animals table — done explicitly here.
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_animals_registry_tag_id ON animals (registry_tag_id)"
        ))

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

        # Seed vaccine types if table is empty
        vt_count_result = await db.execute(select(func.count(VaccineType.id)))
        if vt_count_result.scalar() == 0:
            seed_vaccines = [
                VaccineType(name="FMD",               species_applicability=["CATTLE", "GOAT"],            default_interval_days=180),
                VaccineType(name="Blackleg",           species_applicability=["CATTLE"],                    default_interval_days=365),
                VaccineType(name="Anthrax",            species_applicability=["CATTLE", "SHEEP", "GOAT"],   default_interval_days=365),
                VaccineType(name="Brucellosis",        species_applicability=["CATTLE", "SHEEP", "GOAT"],   default_interval_days=None),
                VaccineType(name="CBPP",               species_applicability=["CATTLE"],                    default_interval_days=365),
                VaccineType(name="PPR",                species_applicability=["SHEEP", "GOAT"],             default_interval_days=1095),
                VaccineType(name="Lumpy Skin Disease", species_applicability=["CATTLE"],                    default_interval_days=365),
                VaccineType(name="ECF",                species_applicability=["CATTLE"],                    default_interval_days=None),
            ]
            db.add_all(seed_vaccines)
            await db.commit()
            logger.info("Seeded vaccine types")

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
    recompute_keys = set()
    
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

                created += 1

            recompute_keys.add((location.id, species, category.id))
                
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    await db.flush()
    for key_location_id, key_species, key_category_id in recompute_keys:
        await update_stock_level(db, key_location_id, key_species, key_category_id)

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
    created_events = []
    pending_outbox_rows = []  # [(event, outbox_row), ...] — sent after the whole log commits
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
        await db.flush()  # populate event.id for the outbox row's source_event_id

        outbox_row = registry_sync.build_outbox_row_for_event(
            event_type=event.event_type,
            event_id=event.id,
            log_date=daily_log.log_date,
            note=event.notes,
            animal_tags=event.animal_tags,
            mother_tag=event.mother_tag,
            registry_previous_status=event_data.registry_previous_status,
        )
        if outbox_row is not None:
            db.add(outbox_row)
            pending_outbox_rows.append((event, outbox_row))

        created_events.append(event)

        # Update stock levels
        if event_data.is_stock_event:
            await apply_event_to_stock(db, data.location_id, event_data)

    await db.commit()
    await db.refresh(daily_log)

    # Attempt Registry delivery now that the domain events are durably committed.
    warnings_by_event_id = {}
    for event, outbox_row in pending_outbox_rows:
        await registry_sync.enqueue_and_send(db, outbox_row)
        if outbox_row.state == RegistrySyncState.CONFLICT:
            warnings_by_event_id[event.id] = registry_sync.conflict_warning_message(outbox_row)

    event_responses = [
        EventResponse(
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
            disease_id=event.disease_id,
            days_sick=event.days_sick,
            attending_vet=event.attending_vet,
            abortion_stage=event.abortion_stage,
            mother_tag=event.mother_tag,
            offspring_tags=event.offspring_tags,
            buyer_name=event.buyer_name,
            buyer_phone=event.buyer_phone,
            buyer_address=event.buyer_address,
            sale_price=event.sale_price,
            registry_sync_warning=warnings_by_event_id.get(event.id),
        )
        for event in created_events
    ]

    return DailyLogResponse(
        id=daily_log.id,
        location_id=daily_log.location_id,
        log_date=daily_log.log_date,
        has_events=daily_log.has_events,
        notes=daily_log.notes,
        is_locked=daily_log.is_locked,
        created_at=daily_log.created_at,
        events=event_responses
    )

@api_router.post("/daily-logs/{log_id}/events", response_model=EventResponse)
async def add_event_to_daily_log(
    log_id: int,
    event_data: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    """Add a new event to an existing daily log - Admin only."""
    result = await db.execute(
        select(DailyLog).where(DailyLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Daily log not found")

    # Validate stock availability for stock-reducing events
    if event_data.is_stock_event and event_data.event_type not in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
        can_proceed, message = await check_stock_availability(
            db, log.location_id, event_data, True  # Admin bypasses strict checks
        )
        if not can_proceed:
            raise HTTPException(status_code=400, detail=message)

    event = Event(
        daily_log_id=log.id,
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
    await db.flush()  # populate event.id for the outbox row's source_event_id

    outbox_row = registry_sync.build_outbox_row_for_event(
        event_type=event.event_type,
        event_id=event.id,
        log_date=log.log_date,
        note=event.notes,
        animal_tags=event.animal_tags,
        mother_tag=event.mother_tag,
        registry_previous_status=event_data.registry_previous_status,
    )
    if outbox_row is not None:
        db.add(outbox_row)

    # Update stock levels
    if event_data.is_stock_event:
        await apply_event_to_stock(db, log.location_id, event_data)

    # Mark log as having events
    log.has_events = True

    await db.commit()
    await db.refresh(event)

    registry_sync_warning = None
    if outbox_row is not None:
        await registry_sync.enqueue_and_send(db, outbox_row)
        if outbox_row.state == RegistrySyncState.CONFLICT:
            registry_sync_warning = registry_sync.conflict_warning_message(outbox_row)

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
        disease_id=event.disease_id,
        days_sick=event.days_sick,
        attending_vet=event.attending_vet,
        abortion_stage=event.abortion_stage,
        mother_tag=event.mother_tag,
        offspring_tags=event.offspring_tags,
        buyer_name=event.buyer_name,
        buyer_phone=event.buyer_phone,
        buyer_address=event.buyer_address,
        sale_price=event.sale_price,
        registry_sync_warning=registry_sync_warning,
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

@api_router.put("/daily-logs/{log_id}", response_model=DailyLogResponse)
async def update_daily_log(
    log_id: int,
    data: DailyLogUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    """Update a daily log's location, date, or notes - Admin only."""
    result = await db.execute(
        select(DailyLog)
        .options(selectinload(DailyLog.location), selectinload(DailyLog.events))
        .where(DailyLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Daily log not found")

    # If changing location or date, check for conflicts
    new_location_id = data.location_id if data.location_id is not None else log.location_id
    new_log_date = data.log_date if data.log_date is not None else log.log_date

    if data.location_id is not None or data.log_date is not None:
        conflict_result = await db.execute(
            select(DailyLog).where(
                and_(
                    DailyLog.location_id == new_location_id,
                    DailyLog.log_date == new_log_date,
                    DailyLog.id != log_id
                )
            )
        )
        if conflict_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="A daily log already exists for this date and location"
            )

    if data.location_id is not None:
        log.location_id = data.location_id
    if data.log_date is not None:
        log.log_date = data.log_date
    # Always update notes (allows clearing by sending null)
    if 'notes' in data.model_fields_set:
        log.notes = data.notes

    await db.commit()
    await db.refresh(log)

    # Reload with relationships for the response
    result = await db.execute(
        select(DailyLog)
        .options(selectinload(DailyLog.location), selectinload(DailyLog.events))
        .where(DailyLog.id == log_id)
    )
    log = result.scalar_one_or_none()

    return DailyLogResponse(
        id=log.id,
        location_id=log.location_id,
        log_date=log.log_date,
        has_events=log.has_events,
        notes=log.notes,
        is_locked=log.is_locked,
        created_at=log.created_at,
        location_name=log.location.name if log.location else None,
        events=[]
    )

# ==================== EVENT ROUTES ====================
@api_router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: int,
    data: EventUpdate,
    db: AsyncSession = Depends(get_db),
    # CHANGED: was require_roles(UserRole.ADMIN) — DATA_ENTRY now allowed
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY))
):
    """Update an event. Reverses old stock changes and applies new ones."""
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.daily_log))
        .where(Event.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ADDED: Lock check — DATA_ENTRY cannot edit events in a locked log
    if event.daily_log.is_locked and current_user.role == UserRole.DATA_ENTRY:
        raise HTTPException(
            status_code=403,
            detail="This log is locked. Only an admin can edit events in a locked log."
        )

    location_id = event.daily_log.location_id

    # ADDED: Type-specific field guard — reject fields that don't apply to event_type
    _type_fields: dict = {
        EventType.DEATH:    {"cause_of_death", "disease_id", "days_sick", "attending_vet"},
        EventType.BIRTH:    {"mother_tag", "offspring_tags"},
        EventType.SOLD:     {"buyer_name", "buyer_phone", "buyer_address", "sale_price"},
        EventType.GIFT_IN:  {"gift_party_name", "gift_party_phone", "gift_reason"},
        EventType.GIFT_OUT: {"gift_party_name", "gift_party_phone", "gift_reason"},
    }
    _all_typed = {f for fields in _type_fields.values() for f in fields}
    _allowed   = _type_fields.get(event.event_type, set())
    _sent      = {k for k, v in data.model_dump(exclude_none=True).items() if k in _all_typed}
    _rejected  = _sent - _allowed
    if _rejected:
        raise HTTPException(
            status_code=400,
            detail=f"Fields not applicable to {event.event_type.value} event: {', '.join(sorted(_rejected))}"
        )

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
    if data.animal_tags is not None:
        event.animal_tags = data.animal_tags
    if data.cause_of_death is not None:
        event.cause_of_death = data.cause_of_death
    if data.disease_id is not None:
        event.disease_id = data.disease_id
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
    # ADDED: Gift-specific fields
    if data.gift_party_name is not None:
        event.gift_party_name = data.gift_party_name
    if data.gift_party_phone is not None:
        event.gift_party_phone = data.gift_party_phone
    if data.gift_reason is not None:
        event.gift_reason = data.gift_reason

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

    # ADDED: link/correct a Registry tag on this event (e.g. via RegistryTagPicker during
    # edit). Upserts rather than always inserting, since a row may already exist from
    # when this event was first created.
    outbox_row = None
    if data.registry_previous_status:
        built = registry_sync.build_outbox_row_for_event(
            event_type=event.event_type,
            event_id=event.id,
            log_date=event.daily_log.log_date,
            note=event.notes,
            animal_tags=event.animal_tags,
            mother_tag=event.mother_tag,
            registry_previous_status=data.registry_previous_status,
        )
        if built is not None:
            outbox_row = await registry_sync.upsert_outbox_row(db, built)

    await db.commit()
    await db.refresh(event)

    registry_sync_warning = None
    if outbox_row is not None:
        await registry_sync.enqueue_and_send(db, outbox_row)
        if outbox_row.state == RegistrySyncState.CONFLICT:
            registry_sync_warning = registry_sync.conflict_warning_message(outbox_row)

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
        sale_price=event.sale_price,
        # ADDED: Gift-specific fields
        gift_party_name=event.gift_party_name,
        gift_party_phone=event.gift_party_phone,
        gift_reason=event.gift_reason,
        registry_sync_warning=registry_sync_warning,
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

@api_router.post("/stock-levels/recompute")
async def recompute_stock_levels_endpoint(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    updated = await recompute_stock_levels(db, location_id=location_id, species=species)
    await db.commit()
    return {"message": "Stock levels recomputed", "updated": updated}

# ==================== DASHBOARD ROUTES ====================
@api_router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    location_id: Optional[int] = None,
    period_days: int = Query(30, ge=1, le=3650),
    db: AsyncSession = Depends(get_db)
):
    today = date.today()
    period_start = today - timedelta(days=period_days)
    
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

    location_totals = [lt for lt in location_totals if lt.total > 0]
    location_totals.sort(key=lambda lt: lt.total, reverse=True)
    
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
    
    # Calculate herd performance indicators (selected period)
    herd_performance = []
    
    # Get events from selected period
    perf_query = select(Event).join(DailyLog).where(DailyLog.log_date >= period_start)
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
        births_period = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.BIRTH)
        deaths_period = sum(e.count for e in recent_events if e.species == sp and e.event_type == EventType.DEATH)
        
        # Calculate rates
        mortality_rate = (deaths_period / total_stock * 100) if total_stock > 0 else 0
        calving_rate = (births_period / breeding_females * 100) if breeding_females > 0 else 0
        
        herd_performance.append(HerdPerformance(
            species=sp,
            total_stock=total_stock,
            breeding_females=breeding_females,
            births_30d=births_period,
            deaths_30d=deaths_period,
            calving_rate=round(calving_rate, 1),
            mortality_rate=round(mortality_rate, 1),
            color=species_colors.get(sp, "#666666")
        ))
    
    # Calculate net changes (selected period)
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
async def build_stock_snapshot(
    db: AsyncSession,
    as_of_date: date,
    location_id: Optional[int] = None
) -> dict:
    openings_query = select(OpeningBalance).where(OpeningBalance.period_start <= as_of_date)
    if location_id:
        openings_query = openings_query.where(OpeningBalance.location_id == location_id)
    openings_query = openings_query.order_by(OpeningBalance.period_start.desc())
    result = await db.execute(openings_query)
    openings = result.scalars().all()

    latest_openings = {}
    for opening in openings:
        key = (opening.location_id, opening.species, opening.category_id)
        if key not in latest_openings:
            latest_openings[key] = {"count": opening.count, "start": opening.period_start}

    current = dict(latest_openings)

    events_query = (
        select(Event, DailyLog.log_date, DailyLog.location_id)
        .join(DailyLog)
        .where(DailyLog.log_date <= as_of_date)
        .order_by(DailyLog.log_date.asc(), Event.id.asc())
    )
    if location_id:
        events_query = events_query.where(
            or_(
                DailyLog.location_id == location_id,
                Event.from_location_id == location_id,
                Event.to_location_id == location_id
            )
        )
    result = await db.execute(events_query)
    events = result.all()

    for event, log_date, log_location_id in events:
        for adj_location_id, adj_species, adj_category_id, delta in event_stock_adjustments(event, log_location_id):
            if location_id and adj_location_id != location_id:
                continue
            key = (adj_location_id, adj_species, adj_category_id)
            if key not in current:
                current[key] = {"count": 0, "start": date.min}
            if log_date < current[key]["start"]:
                continue
            current[key]["count"] += delta

    return current

async def build_location_totals_from_snapshot(
    db: AsyncSession,
    snapshot: dict,
    location_id: Optional[int] = None,
    include_zero: bool = False
) -> List[LocationTotals]:
    totals = {}
    for (loc_id, species, _category_id), data in snapshot.items():
        if location_id and loc_id != location_id:
            continue
        if loc_id not in totals:
            totals[loc_id] = {"cattle": 0, "sheep": 0, "goat": 0, "total": 0}
        species_key = species.value
        totals[loc_id][species_key] += data["count"]
        totals[loc_id]["total"] += data["count"]

    if location_id and location_id not in totals:
        totals[location_id] = {"cattle": 0, "sheep": 0, "goat": 0, "total": 0}

    location_ids = list(totals.keys())
    location_names = {}
    if location_ids:
        result = await db.execute(select(Location).where(Location.id.in_(location_ids)))
        location_names = {loc.id: loc.name for loc in result.scalars().all()}

    results = []
    for loc_id, counts in totals.items():
        if not include_zero and counts["total"] <= 0:
            continue
        results.append(LocationTotals(
            location_id=loc_id,
            location_name=location_names.get(loc_id, "Unknown"),
            cattle=counts["cattle"],
            sheep=counts["sheep"],
            goat=counts["goat"],
            total=counts["total"]
        ))

    results.sort(key=lambda lt: lt.total, reverse=True)
    return results

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
        query = query.where(
            or_(
                DailyLog.location_id == location_id,
                Event.from_location_id == location_id,
                Event.to_location_id == location_id
            )
        )
    
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
        .options(selectinload(Event.category), selectinload(Event.disease), selectinload(Event.daily_log))
        .join(DailyLog)
        .where(and_(DailyLog.log_date >= start_date, DailyLog.log_date <= end_date))
    )
    if location_id:
        events_query = events_query.where(
            or_(
                DailyLog.location_id == location_id,
                Event.from_location_id == location_id,
                Event.to_location_id == location_id
            )
        )
    result = await db.execute(events_query)
    events = result.scalars().all()

    category_result = await db.execute(
        select(Category).where(Category.name_sw.in_(["Koo", "Dume Mbegu"]))
    )
    categories = category_result.scalars().all()
    category_ids = {(cat.species, cat.name_sw): cat.id for cat in categories}

    def category_net_change(species: SpeciesType, category_id: Optional[int]) -> int:
        if not category_id:
            return 0
        change = 0
        for event in events:
            if event.species != species or not event.is_stock_event:
                continue
            if event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
                if event.category_id == category_id:
                    change += event.count
            elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
                if event.category_id == category_id:
                    change -= event.count
            elif event.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
                if event.from_category_id == category_id:
                    change -= event.count
                if event.to_category_id == category_id:
                    change += event.count
        return change
    
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
        birth_events = [e for e in events if e.species == sp and e.event_type == EventType.BIRTH]
        births = sum(e.count for e in birth_events)
        births_male = sum(
            e.count for e in birth_events
            if e.category and e.category.name_sw.strip().lower().endswith(" dume")
        )
        births_female = sum(
            e.count for e in birth_events
            if e.category and e.category.name_sw.strip().lower().endswith(" jike")
        )
        deaths = sum(e.count for e in events if e.species == sp and e.event_type == EventType.DEATH)
        weaned = sum(e.count for e in events if e.species == sp and e.event_type == EventType.WEANING)
        sold = sum(e.count for e in events if e.species == sp and e.event_type == EventType.SOLD)
        bought = sum(e.count for e in events if e.species == sp and e.event_type == EventType.BOUGHT)
        gift_in = sum(e.count for e in events if e.species == sp and e.event_type == EventType.GIFT_IN)
        gift_out = sum(e.count for e in events if e.species == sp and e.event_type == EventType.GIFT_OUT)
        missing = sum(e.count for e in events if e.species == sp and e.event_type == EventType.MISSING)
        
        breeding_female_category_id = category_ids.get((sp, "Koo"))
        breeding_male_category_id = category_ids.get((sp, "Dume Mbegu"))

        # Get breeding female count (Koo category) for calving rate
        breeding_females = 0
        if breeding_female_category_id:
            bf_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                and_(StockLevel.species == sp, StockLevel.category_id == breeding_female_category_id)
            )
            if location_id:
                bf_query = bf_query.where(StockLevel.location_id == location_id)
            result = await db.execute(bf_query)
            breeding_females = result.scalar() or 0

        breeding_males = 0
        if breeding_male_category_id:
            bm_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                and_(StockLevel.species == sp, StockLevel.category_id == breeding_male_category_id)
            )
            if location_id:
                bm_query = bm_query.where(StockLevel.location_id == location_id)
            result = await db.execute(bm_query)
            breeding_males = result.scalar() or 0

        breeding_females_trend = category_net_change(sp, breeding_female_category_id)
        
        # Calculate rates
        mortality_rate = (deaths / total_stock * 100) if total_stock > 0 else 0
        calving_rate = (births / breeding_females * 100) if breeding_females > 0 else 0
        weaning_rate = (weaned / births * 100) if births > 0 else 0
        
        species_data[sp] = SpeciesRates(
            species=sp,
            total_stock=total_stock,
            breeding_females=breeding_females,
            breeding_males=breeding_males,
            breeding_females_trend=breeding_females_trend,
            births=births,
            births_male=births_male,
            births_female=births_female,
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

    # Category breakdown for animal groups
    category_totals = []
    for sp in SpeciesType:
        category_net_changes = {}
        for event in events:
            if event.species != sp or not event.is_stock_event:
                continue
            if event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
                if event.category_id:
                    category_net_changes[event.category_id] = category_net_changes.get(event.category_id, 0) + event.count
            elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
                if event.category_id:
                    category_net_changes[event.category_id] = category_net_changes.get(event.category_id, 0) - event.count
            elif event.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
                if event.from_category_id:
                    category_net_changes[event.from_category_id] = category_net_changes.get(event.from_category_id, 0) - event.count
                if event.to_category_id:
                    category_net_changes[event.to_category_id] = category_net_changes.get(event.to_category_id, 0) + event.count

        cat_query = select(StockLevel).options(selectinload(StockLevel.category)).where(StockLevel.species == sp)
        if location_id:
            cat_query = cat_query.where(StockLevel.location_id == location_id)
        result = await db.execute(cat_query)
        stock_levels = result.scalars().all()

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
                count=data["count"],
                net_change=category_net_changes.get(cat_id, 0)
            )
            for cat_id, data in category_counts.items()
            if data["count"] > 0
        ]

        species_total = sum(c.count for c in categories_list)
        category_totals.append(SpeciesCategoryTotals(
            species=sp,
            categories=categories_list,
            total=species_total
        ))
    
    # ===== DETAILED DEATH ANALYSIS =====
    death_events = [e for e in events if e.event_type == EventType.DEATH]
    total_deaths = sum(e.count for e in death_events)

    location_lookup = {}
    location_result = await db.execute(select(Location))
    for loc in location_result.scalars().all():
        location_lookup[loc.id] = loc.name
    
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

    death_locations = {}
    for event in death_events:
        log = event.daily_log
        if not log:
            continue
        loc_id = log.location_id
        if not loc_id:
            continue
        if loc_id not in death_locations:
            death_locations[loc_id] = {
                "name": location_lookup.get(loc_id, "Unknown"),
                "count": 0
            }
        death_locations[loc_id]["count"] += event.count

    deaths_by_location = []
    for loc_id, data in sorted(death_locations.items(), key=lambda x: x[1]["count"], reverse=True):
        deaths_by_location.append(DeathByLocation(
            location_id=loc_id,
            location_name=data["name"],
            total_deaths=data["count"],
            percentage=round((data["count"] / total_deaths * 100) if total_deaths > 0 else 0, 1)
        ))
    death_analysis = DeathAnalysis(
        total_deaths=total_deaths, by_species=deaths_by_species, top_causes=top_causes,
        top_diseases=top_diseases, vet_attendance_rate=round(vet_attendance_rate, 1),
        by_location=deaths_by_location
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
        species_rates=list(species_data.values()), category_totals=category_totals, death_analysis=death_analysis,
        abortion_analysis=abortion_analysis, sales_analysis=sales_analysis,
        net_changes=net_changes_list, location_id=location_id, location_name=location_name
    )

@api_router.get("/reports/detailed", response_model=DetailedReportResponse)
async def get_detailed_report(
    start_date: date,
    end_date: date,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    selected_location_name = None
    if location_id:
        loc_result = await db.execute(select(Location).where(Location.id == location_id))
        loc = loc_result.scalar_one_or_none()
        if loc:
            selected_location_name = loc.name

    opening_date = start_date - timedelta(days=1)
    opening_snapshot = await build_stock_snapshot(db, opening_date, location_id=location_id)
    closing_snapshot = await build_stock_snapshot(db, end_date, location_id=location_id)

    include_zero = bool(location_id)
    opening_totals = await build_location_totals_from_snapshot(
        db, opening_snapshot, location_id=location_id, include_zero=include_zero
    )
    closing_totals = await build_location_totals_from_snapshot(
        db, closing_snapshot, location_id=location_id, include_zero=include_zero
    )

    events_query = (
        select(Event, DailyLog.log_date, DailyLog.location_id)
        .join(DailyLog)
        .options(
            selectinload(Event.daily_log).selectinload(DailyLog.location),
            selectinload(Event.category),
            selectinload(Event.from_location),
            selectinload(Event.to_location),
            selectinload(Event.from_category),
            selectinload(Event.to_category)
        )
        .where(and_(DailyLog.log_date >= start_date, DailyLog.log_date <= end_date))
        .order_by(DailyLog.log_date.asc(), Event.id.asc())
    )
    if location_id:
        events_query = events_query.where(DailyLog.location_id == location_id)
    result = await db.execute(events_query)
    event_rows = result.all()

    events = []
    for event, log_date, log_location_id in event_rows:
        log_location_name = "Unknown"
        if event.daily_log and event.daily_log.location:
            log_location_name = event.daily_log.location.name

        events.append(DetailedReportEvent(
            id=event.id,
            log_date=log_date,
            location_id=log_location_id,
            location_name=log_location_name,
            event_type=event.event_type,
            species=event.species,
            count=event.count,
            category_name_sw=event.category.name_sw if event.category else None,
            from_location_name=event.from_location.name if event.from_location else None,
            to_location_name=event.to_location.name if event.to_location else None,
            from_category_name_sw=event.from_category.name_sw if event.from_category else None,
            to_category_name_sw=event.to_category.name_sw if event.to_category else None,
            notes=event.notes
        ))

    return DetailedReportResponse(
        start_date=start_date,
        end_date=end_date,
        location_id=location_id,
        location_name=selected_location_name,
        opening_totals=opening_totals,
        closing_totals=closing_totals,
        events=events
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
    
    elif event_data.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
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
    
    elif event_data.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
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
    
    elif event_data.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
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

def event_stock_adjustments(
    event: Event,
    log_location_id: int
) -> List[tuple[int, SpeciesType, int, int]]:
    adjustments = []
    if not event.is_stock_event:
        return adjustments

    if event.event_type == EventType.TRANSFER:
        if event.from_location_id and event.category_id:
            adjustments.append((event.from_location_id, event.species, event.category_id, -event.count))
        if event.to_location_id and event.category_id:
            adjustments.append((event.to_location_id, event.species, event.category_id, event.count))
    elif event.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
        if event.from_category_id:
            adjustments.append((log_location_id, event.species, event.from_category_id, -event.count))
        if event.to_category_id:
            adjustments.append((log_location_id, event.species, event.to_category_id, event.count))
    elif event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
        if event.category_id:
            adjustments.append((log_location_id, event.species, event.category_id, event.count))
    elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
        if event.category_id:
            adjustments.append((log_location_id, event.species, event.category_id, -event.count))

    return adjustments

async def recompute_stock_levels(
    db: AsyncSession,
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    category_id: Optional[int] = None
) -> int:
    """Recompute stock levels from opening balances and stock-impacting events."""
    openings_query = select(OpeningBalance)
    if location_id:
        openings_query = openings_query.where(OpeningBalance.location_id == location_id)
    if species:
        openings_query = openings_query.where(OpeningBalance.species == species)
    if category_id:
        openings_query = openings_query.where(OpeningBalance.category_id == category_id)
    openings_query = openings_query.order_by(OpeningBalance.period_start.desc())
    result = await db.execute(openings_query)
    openings = result.scalars().all()

    latest_openings = {}
    for opening in openings:
        key = (opening.location_id, opening.species, opening.category_id)
        if key not in latest_openings:
            latest_openings[key] = {
                "count": opening.count,
                "start": opening.period_start
            }

    levels_query = select(StockLevel)
    if location_id:
        levels_query = levels_query.where(StockLevel.location_id == location_id)
    if species:
        levels_query = levels_query.where(StockLevel.species == species)
    if category_id:
        levels_query = levels_query.where(StockLevel.category_id == category_id)
    result = await db.execute(levels_query)
    existing_levels = result.scalars().all()

    current = dict(latest_openings)
    for level in existing_levels:
        key = (level.location_id, level.species, level.category_id)
        if key not in current:
            current[key] = {"count": 0, "start": date.min}

    events_query = (
        select(Event, DailyLog.log_date, DailyLog.location_id)
        .join(DailyLog)
        .order_by(DailyLog.log_date.asc(), Event.id.asc())
    )
    if species:
        events_query = events_query.where(Event.species == species)
    if location_id:
        events_query = events_query.where(
            or_(
                DailyLog.location_id == location_id,
                Event.from_location_id == location_id,
                Event.to_location_id == location_id
            )
        )
    if category_id:
        events_query = events_query.where(
            or_(
                Event.category_id == category_id,
                Event.from_category_id == category_id,
                Event.to_category_id == category_id
            )
        )

    result = await db.execute(events_query)
    events = result.all()

    for event, log_date, log_location_id in events:
        for adj_location_id, adj_species, adj_category_id, delta in event_stock_adjustments(event, log_location_id):
            if location_id and adj_location_id != location_id:
                continue
            if species and adj_species != species:
                continue
            if category_id and adj_category_id != category_id:
                continue

            key = (adj_location_id, adj_species, adj_category_id)
            if key not in current:
                current[key] = {"count": 0, "start": date.min}
            if log_date < current[key]["start"]:
                continue
            current[key]["count"] += delta

    existing_map = {(sl.location_id, sl.species, sl.category_id): sl for sl in existing_levels}
    updated = 0
    for key, data in current.items():
        if location_id and key[0] != location_id:
            continue
        if species and key[1] != species:
            continue
        if category_id and key[2] != category_id:
            continue

        stock = existing_map.get(key)
        if stock:
            stock.current_count = data["count"]
            stock.last_updated = datetime.now(timezone.utc)
        else:
            stock = StockLevel(
                location_id=key[0],
                species=key[1],
                category_id=key[2],
                current_count=data["count"]
            )
            db.add(stock)
        updated += 1

    return updated

async def update_stock_level(
    db: AsyncSession,
    location_id: int,
    species: SpeciesType,
    category_id: int
):
    """Recalculate stock level from opening balance + events."""
    await recompute_stock_levels(
        db,
        location_id=location_id,
        species=species,
        category_id=category_id
    )

# ==================== ANIMAL ROUTES ====================

def _animal_response(animal: Animal) -> AnimalResponse:
    return AnimalResponse(
        id=animal.id,
        tag_number=animal.tag_number,
        name=animal.name,
        species=animal.species,
        category_id=animal.category_id,
        location_id=animal.location_id,
        sex=animal.sex,
        birth_date=animal.birth_date,
        mother_tag=animal.mother_tag,
        father_tag=animal.father_tag,
        acquisition_type=animal.acquisition_type,
        acquisition_date=animal.acquisition_date,
        status=animal.status,
        status_changed_at=animal.status_changed_at,
        notes=animal.notes,
        created_at=animal.created_at,
        category_name_sw=animal.category.name_sw if animal.category else None,
        category_name_en=animal.category.name_en if animal.category else None,
        location_name=animal.location.name if animal.location else None,
        created_by_name=animal.creator.name if animal.creator else None,
        registry_tag_id=animal.registry_tag_id,
    )

@api_router.get("/templates/animals")
async def download_animals_template(db: AsyncSession = Depends(get_db)):
    """Download CSV template for importing animals"""
    loc_result = await db.execute(select(Location).where(Location.is_active == True))
    locations = loc_result.scalars().all()

    cat_result = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.species, Category.sort_order)
    )
    categories = cat_result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['tag_number', 'name', 'species', 'category', 'location', 'sex', 'birth_date', 'acquisition_type', 'acquisition_date', 'notes'])
    sample_loc = locations[0].name if locations else 'Shamba Kuu'
    writer.writerow(['T-001', 'Bella', 'cattle', 'Koo', sample_loc, 'female', '2023-01-15', 'born', '2023-01-15', 'First calf born this season'])
    writer.writerow(['T-002', '', 'cattle', 'Mitamba', sample_loc, 'female', '', 'bought', '2024-03-01', ''])
    writer.writerow(['G-001', '', 'goat', 'Koo', sample_loc, 'male', '', 'gift_in', '2024-06-01', ''])

    writer.writerow([])
    writer.writerow(['# REFERENCE - species: cattle, sheep, goat'])
    writer.writerow(['# REFERENCE - sex: male, female'])
    writer.writerow(['# REFERENCE - acquisition_type: born, bought, gift_in'])
    writer.writerow(['# REFERENCE - dates: YYYY-MM-DD format (birth_date optional)'])

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
        headers={'Content-Disposition': 'attachment; filename=animals_template.csv'}
    )

@api_router.get("/animals", response_model=List[AnimalResponse])
async def list_animals(
    species: Optional[SpeciesType] = None,
    location_id: Optional[int] = None,
    category_id: Optional[int] = None,
    status: Optional[AnimalStatus] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Animal).options(
        selectinload(Animal.category),
        selectinload(Animal.location),
        selectinload(Animal.creator),
    )
    if species:
        query = query.where(Animal.species == species)
    if location_id:
        query = query.where(Animal.location_id == location_id)
    if category_id:
        query = query.where(Animal.category_id == category_id)
    if status:
        query = query.where(Animal.status == status)
    if search:
        query = query.where(
            or_(Animal.tag_number.ilike(f'%{search}%'), Animal.name.ilike(f'%{search}%'))
        )
    query = query.order_by(Animal.species, Animal.tag_number)
    result = await db.execute(query)
    animals = result.scalars().all()
    return [_animal_response(a) for a in animals]

@api_router.post("/animals", response_model=AnimalResponse)
async def create_animal(
    data: AnimalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    dup = await db.execute(
        select(Animal).where(
            and_(
                Animal.tag_number == data.tag_number,
                Animal.species == data.species,
                Animal.location_id == data.location_id,
            )
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Tag '{data.tag_number}' already exists for this species at this location")

    animal = Animal(
        tag_number=data.tag_number,
        name=data.name,
        species=data.species,
        category_id=data.category_id,
        location_id=data.location_id,
        sex=data.sex,
        birth_date=data.birth_date,
        mother_tag=data.mother_tag,
        father_tag=data.father_tag,
        acquisition_type=data.acquisition_type,
        acquisition_date=data.acquisition_date,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(animal)
    await db.flush()
    animal_id = animal.id
    await db.commit()

    result = await db.execute(
        select(Animal).options(
            selectinload(Animal.category),
            selectinload(Animal.location),
            selectinload(Animal.creator),
        ).where(Animal.id == animal_id)
    )
    return _animal_response(result.scalar_one())

@api_router.post("/animals/bulk-import", response_model=BulkImportResult)
async def bulk_import_animals(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))

    loc_result = await db.execute(select(Location))
    locations = {loc.name.lower(): loc for loc in loc_result.scalars().all()}

    cat_result = await db.execute(select(Category))
    categories_lookup = {}
    for cat in cat_result.scalars().all():
        categories_lookup[(cat.species.value, cat.name_sw.lower())] = cat

    created = 0
    skipped = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            tag = row.get('tag_number', '').strip()
            if not tag or tag.startswith('#'):
                continue

            species_str = row.get('species', '').strip().lower()
            category_name = row.get('category', '').strip()
            location_name = row.get('location', '').strip()
            sex_str = row.get('sex', '').strip().lower()
            acq_type_str = row.get('acquisition_type', '').strip().lower().replace(' ', '_')
            acq_date_str = row.get('acquisition_date', '').strip()

            try:
                species = SpeciesType(species_str)
            except ValueError:
                errors.append(f"Row {row_num}: Invalid species '{species_str}'. Use: cattle, sheep, goat")
                continue

            category = categories_lookup.get((species_str, category_name.lower()))
            if not category:
                errors.append(f"Row {row_num}: Category '{category_name}' not found for {species_str}")
                continue

            location = locations.get(location_name.lower())
            if not location:
                errors.append(f"Row {row_num}: Location '{location_name}' not found")
                continue

            sex_map = {'male': 'male', 'm': 'male', 'female': 'female', 'f': 'female'}
            sex_val = sex_map.get(sex_str)
            if not sex_val:
                errors.append(f"Row {row_num}: Invalid sex '{sex_str}'. Use: male, female")
                continue
            sex = AnimalSex(sex_val)

            try:
                acquisition_type = AnimalAcquisitionType(acq_type_str)
            except ValueError:
                errors.append(f"Row {row_num}: Invalid acquisition_type '{acq_type_str}'. Use: born, bought, gift_in")
                continue

            try:
                acquisition_date = datetime.strptime(acq_date_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append(f"Row {row_num}: Invalid acquisition_date '{acq_date_str}'. Use YYYY-MM-DD")
                continue

            birth_date = None
            birth_date_str = row.get('birth_date', '').strip()
            if birth_date_str:
                try:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid birth_date '{birth_date_str}'. Use YYYY-MM-DD")
                    continue

            dup = await db.execute(
                select(Animal).where(
                    and_(
                        Animal.tag_number == tag,
                        Animal.species == species,
                        Animal.location_id == location.id,
                    )
                )
            )
            if dup.scalar_one_or_none():
                skipped += 1
                continue

            db.add(Animal(
                tag_number=tag,
                name=row.get('name', '').strip() or None,
                species=species,
                category_id=category.id,
                location_id=location.id,
                sex=sex,
                birth_date=birth_date,
                acquisition_type=acquisition_type,
                acquisition_date=acquisition_date,
                notes=row.get('notes', '').strip() or None,
                created_by=current_user.id,
            ))
            created += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    await db.commit()
    return BulkImportResult(
        created=created,
        skipped=skipped,
        errors=errors,
        message=f"Import complete. Created: {created}, Skipped (duplicates): {skipped}",
    )

# Literal path — must be before /animals/{animal_id} or FastAPI would try to parse
# "untagged-calves" as an int animal_id.
@api_router.get("/animals/untagged-calves", response_model=List[UntaggedCalfResponse])
async def list_untagged_calves(
    min_age_days: int = Query(30, ge=0, le=3650),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Calves born at least `min_age_days` ago that still have no registry_tag_id —
    for the admin tagging screen (assign one via POST /animals/{id}/assign-registry-tag)."""
    cutoff = date.today() - timedelta(days=min_age_days)
    result = await db.execute(
        select(Animal)
        .options(selectinload(Animal.category), selectinload(Animal.location))
        .where(
            and_(
                Animal.acquisition_type == AnimalAcquisitionType.BORN,
                Animal.status == AnimalStatus.ACTIVE,
                Animal.registry_tag_id.is_(None),
                Animal.birth_date.isnot(None),
                Animal.birth_date <= cutoff,
            )
        )
        .order_by(Animal.birth_date.asc())
    )
    animals = result.scalars().all()
    today = date.today()
    return [
        UntaggedCalfResponse(
            id=a.id,
            tag_number=a.tag_number,
            name=a.name,
            species=a.species,
            birth_date=a.birth_date,
            days_since_birth=(today - a.birth_date).days if a.birth_date else None,
            category_name_sw=a.category.name_sw if a.category else None,
            location_name=a.location.name if a.location else None,
        )
        for a in animals
    ]

@api_router.post("/animals/{animal_id}/assign-registry-tag", response_model=AnimalResponse)
async def assign_registry_tag(
    animal_id: int,
    data: AnimalAssignRegistryTag,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Assigns a Herd Tag Registry tag to a calf once it's been physically tagged."""
    result = await db.execute(select(Animal).where(Animal.id == animal_id))
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    if animal.registry_tag_id:
        raise HTTPException(status_code=400, detail="This animal already has a registry tag assigned")

    animal.registry_tag_id = data.tag_id
    outbox_row = registry_sync.build_outbox_row_for_tag_assignment(animal_id=animal.id, tag_id=data.tag_id)
    db.add(outbox_row)
    await db.commit()

    await registry_sync.enqueue_and_send(db, outbox_row)
    registry_sync_warning = (
        registry_sync.conflict_warning_message(outbox_row)
        if outbox_row.state == RegistrySyncState.CONFLICT
        else None
    )

    result = await db.execute(
        select(Animal).options(
            selectinload(Animal.category),
            selectinload(Animal.location),
            selectinload(Animal.creator),
        ).where(Animal.id == animal_id)
    )
    response = _animal_response(result.scalar_one())
    response.registry_sync_warning = registry_sync_warning
    return response

@api_router.get("/animals/{animal_id}", response_model=AnimalResponse)
async def get_animal(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Animal).options(
            selectinload(Animal.category),
            selectinload(Animal.location),
            selectinload(Animal.creator),
        ).where(Animal.id == animal_id)
    )
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    return _animal_response(animal)

@api_router.put("/animals/{animal_id}", response_model=AnimalResponse)
async def update_animal(
    animal_id: int,
    data: AnimalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    result = await db.execute(select(Animal).where(Animal.id == animal_id))
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")

    if data.tag_number is not None and data.tag_number != animal.tag_number:
        check_loc = data.location_id if data.location_id is not None else animal.location_id
        dup = await db.execute(
            select(Animal).where(
                and_(
                    Animal.tag_number == data.tag_number,
                    Animal.species == animal.species,
                    Animal.location_id == check_loc,
                    Animal.id != animal_id,
                )
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Tag '{data.tag_number}' already exists for this species at this location")

    if data.tag_number is not None:
        animal.tag_number = data.tag_number
    if data.name is not None:
        animal.name = data.name
    if data.category_id is not None:
        animal.category_id = data.category_id
    if data.location_id is not None:
        animal.location_id = data.location_id
    if data.sex is not None:
        animal.sex = data.sex
    if data.birth_date is not None:
        animal.birth_date = data.birth_date
    if data.mother_tag is not None:
        animal.mother_tag = data.mother_tag
    if data.father_tag is not None:
        animal.father_tag = data.father_tag
    if data.notes is not None:
        animal.notes = data.notes
    if data.status is not None:
        animal.status = data.status
        animal.status_changed_at = datetime.now(timezone.utc)

    await db.commit()

    result = await db.execute(
        select(Animal).options(
            selectinload(Animal.category),
            selectinload(Animal.location),
            selectinload(Animal.creator),
        ).where(Animal.id == animal_id)
    )
    return _animal_response(result.scalar_one())

@api_router.post("/animals/{animal_id}/transfer", response_model=AnimalResponse)
async def transfer_animal(
    animal_id: int,
    data: AnimalTransfer,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(Animal).where(Animal.id == animal_id))
    animal = result.scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    if animal.status != AnimalStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Animal is not active (status: {animal.status.value})")
    if animal.location_id == data.to_location_id:
        raise HTTPException(status_code=400, detail="Animal is already at this location")

    dest = await db.execute(select(Location).where(Location.id == data.to_location_id))
    if not dest.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Destination location not found")

    old_location_id = animal.location_id

    # Find or create daily log for the source location on transfer date
    log_result = await db.execute(
        select(DailyLog).where(
            and_(DailyLog.location_id == old_location_id, DailyLog.log_date == data.transfer_date)
        )
    )
    log = log_result.scalar_one_or_none()
    if not log:
        log = DailyLog(
            location_id=old_location_id,
            log_date=data.transfer_date,
            has_events=True,
            created_by=current_user.id,
        )
        db.add(log)
        await db.flush()
    else:
        log.has_events = True

    # Record TRANSFER event in the daily log
    event = Event(
        daily_log_id=log.id,
        event_type=EventType.TRANSFER,
        species=animal.species,
        category_id=animal.category_id,
        count=1,
        from_location_id=old_location_id,
        to_location_id=data.to_location_id,
        notes=data.notes,
        animal_tags=animal.tag_number,
        is_stock_event=True,
        created_by=current_user.id,
    )
    db.add(event)

    # Adjust stock levels via existing helper
    await apply_event_to_stock(
        db,
        old_location_id,
        EventCreate(
            event_type=EventType.TRANSFER,
            species=animal.species,
            category_id=animal.category_id,
            count=1,
            from_location_id=old_location_id,
            to_location_id=data.to_location_id,
            is_stock_event=True,
        ),
    )

    animal.location_id = data.to_location_id
    animal.status_changed_at = datetime.now(timezone.utc)
    await db.commit()

    result = await db.execute(
        select(Animal).options(
            selectinload(Animal.category),
            selectinload(Animal.location),
            selectinload(Animal.creator),
        ).where(Animal.id == animal_id)
    )
    return _animal_response(result.scalar_one())

# ==================== FARM HEALTH ROUTES ====================

async def _resolve_categories_for_event(db: AsyncSession, category_ids):
    if not category_ids:
        return []
    result = await db.execute(select(Category).where(Category.id.in_(category_ids)))
    return [CategoryInfo(id=c.id, name_sw=c.name_sw, name_en=c.name_en) for c in result.scalars().all()]

async def _compute_next_due(db: AsyncSession, location_id: int, species, event_type, event_date: date):
    if species is None:
        return None
    interval_result = await db.execute(
        select(HealthInterval).where(
            and_(
                HealthInterval.location_id == location_id,
                HealthInterval.species == species,
                HealthInterval.event_type == event_type,
            )
        )
    )
    interval = interval_result.scalar_one_or_none()
    if interval:
        return event_date + timedelta(days=interval.interval_days)
    return None

def _health_event_response(ev: FarmHealthEventModel, resolved_categories=None, vaccine_type_name=None) -> FarmHealthEventResponse:
    return FarmHealthEventResponse(
        id=ev.id,
        location_id=ev.location_id,
        event_type=ev.event_type,
        event_date=ev.event_date,
        species=ev.species,
        category_scope=ev.category_scope,
        category_ids=ev.category_ids,
        product_name=ev.product_name,
        dosage=ev.dosage,
        cost_per_head=ev.cost_per_head,
        total_cost=ev.total_cost,
        head_count=ev.head_count,
        next_due_date=ev.next_due_date,
        notes=ev.notes,
        created_at=ev.created_at,
        location_name=ev.location.name if ev.location else None,
        resolved_categories=resolved_categories or [],
        created_by_name=ev.creator.name if ev.creator else None,
        vaccine_type_id=ev.vaccine_type_id,
        vaccine_type_name=vaccine_type_name,
    )

@api_router.get("/health-intervals", response_model=List[HealthIntervalResponse])
async def list_health_intervals(
    location_id: Optional[int] = Query(None),
    species: Optional[SpeciesType] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(HealthInterval).options(selectinload(HealthInterval.location))
    if location_id:
        q = q.where(HealthInterval.location_id == location_id)
    if species:
        q = q.where(HealthInterval.species == species)
    q = q.order_by(HealthInterval.location_id, HealthInterval.species, HealthInterval.event_type)
    result = await db.execute(q)
    return [
        HealthIntervalResponse(
            id=i.id,
            location_id=i.location_id,
            species=i.species,
            event_type=i.event_type,
            interval_days=i.interval_days,
            notes=i.notes,
            location_name=i.location.name if i.location else None,
        )
        for i in result.scalars().all()
    ]

@api_router.post("/health-intervals", response_model=HealthIntervalResponse)
async def create_health_interval(
    data: HealthIntervalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = await db.execute(
        select(HealthInterval).where(
            and_(
                HealthInterval.location_id == data.location_id,
                HealthInterval.species == data.species,
                HealthInterval.event_type == data.event_type,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Interval already exists for this combination. Use PUT to update.")

    iv = HealthInterval(
        location_id=data.location_id,
        species=data.species,
        event_type=data.event_type,
        interval_days=data.interval_days,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(iv)
    await db.commit()

    result = await db.execute(
        select(HealthInterval).options(selectinload(HealthInterval.location)).where(HealthInterval.id == iv.id)
    )
    i = result.scalar_one()
    return HealthIntervalResponse(
        id=i.id, location_id=i.location_id, species=i.species, event_type=i.event_type,
        interval_days=i.interval_days, notes=i.notes,
        location_name=i.location.name if i.location else None,
    )

@api_router.put("/health-intervals/{interval_id}", response_model=HealthIntervalResponse)
async def update_health_interval(
    interval_id: int,
    data: HealthIntervalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(
        select(HealthInterval).options(selectinload(HealthInterval.location)).where(HealthInterval.id == interval_id)
    )
    iv = result.scalar_one_or_none()
    if not iv:
        raise HTTPException(status_code=404, detail="Interval not found")
    if data.interval_days is not None:
        iv.interval_days = data.interval_days
    if data.notes is not None:
        iv.notes = data.notes
    await db.commit()
    await db.refresh(iv)
    return HealthIntervalResponse(
        id=iv.id, location_id=iv.location_id, species=iv.species, event_type=iv.event_type,
        interval_days=iv.interval_days, notes=iv.notes,
        location_name=iv.location.name if iv.location else None,
    )

@api_router.delete("/health-intervals/{interval_id}")
async def delete_health_interval(
    interval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(HealthInterval).where(HealthInterval.id == interval_id))
    iv = result.scalar_one_or_none()
    if not iv:
        raise HTTPException(status_code=404, detail="Interval not found")
    await db.delete(iv)
    await db.commit()
    return {"message": "Interval deleted"}

@api_router.get("/farm-health/last-events", response_model=List[LastEventSummary])
async def get_last_events(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    loc_q = select(Location).where(Location.is_active == True)
    if location_id:
        loc_q = loc_q.where(Location.id == location_id)
    loc_result = await db.execute(loc_q)
    locations_map = {loc.id: loc for loc in loc_result.scalars().all()}
    if not locations_map:
        return []

    location_ids = list(locations_map.keys())

    interval_result = await db.execute(
        select(HealthInterval).where(HealthInterval.location_id.in_(location_ids))
    )
    intervals_map = {}
    for iv in interval_result.scalars().all():
        intervals_map[(iv.location_id, iv.species, iv.event_type)] = iv

    last_events_result = await db.execute(
        select(
            FarmHealthEventModel.location_id,
            FarmHealthEventModel.event_type,
            FarmHealthEventModel.species,
            func.max(FarmHealthEventModel.event_date).label("last_date"),
        )
        .where(FarmHealthEventModel.location_id.in_(location_ids))
        .group_by(
            FarmHealthEventModel.location_id,
            FarmHealthEventModel.event_type,
            FarmHealthEventModel.species,
        )
    )

    today = date.today()
    summaries = []
    seen = set()

    for row in last_events_result.fetchall():
        loc_id, evt_type, species_val, last_date = row[0], row[1], row[2], row[3]
        seen.add((loc_id, evt_type, species_val))

        iv = intervals_map.get((loc_id, species_val, evt_type))
        next_due = None
        if iv and last_date:
            next_due = last_date + timedelta(days=iv.interval_days)

        is_overdue = bool(next_due and today > next_due)
        days_overdue = (today - next_due).days if is_overdue else None

        summaries.append(LastEventSummary(
            location_id=loc_id,
            location_name=locations_map[loc_id].name,
            species=species_val,
            event_type=evt_type,
            last_date=last_date,
            next_due_date=next_due,
            is_overdue=is_overdue,
            days_overdue=days_overdue,
        ))

    for (loc_id, species_val, evt_type), iv in intervals_map.items():
        if (loc_id, evt_type, species_val) not in seen:
            summaries.append(LastEventSummary(
                location_id=loc_id,
                location_name=locations_map[loc_id].name,
                species=species_val,
                event_type=evt_type,
                last_date=None,
                next_due_date=None,
                is_overdue=True,
                days_overdue=None,
            ))

    return summaries

@api_router.get("/farm-health/upcoming", response_model=List[FarmHealthEventResponse])
async def get_upcoming_health_events(
    days: int = Query(30),
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    cutoff = today + timedelta(days=days)
    q = (
        select(FarmHealthEventModel)
        .options(selectinload(FarmHealthEventModel.location), selectinload(FarmHealthEventModel.creator))
        .where(and_(FarmHealthEventModel.next_due_date >= today, FarmHealthEventModel.next_due_date <= cutoff))
        .order_by(FarmHealthEventModel.next_due_date)
    )
    if location_id:
        q = q.where(FarmHealthEventModel.location_id == location_id)
    result = await db.execute(q)
    events = result.scalars().all()
    out = []
    for ev in events:
        cats = await _resolve_categories_for_event(db, ev.category_ids)
        out.append(_health_event_response(ev, cats))
    return out

@api_router.get("/farm-health/product-suggestions")
async def get_product_suggestions(
    event_type: Optional[HealthEventType] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(FarmHealthEventModel.product_name).where(FarmHealthEventModel.product_name.isnot(None))
    if event_type:
        q = q.where(FarmHealthEventModel.event_type == event_type)
    result = await db.execute(q.distinct().order_by(FarmHealthEventModel.product_name))
    return {"suggestions": [row[0] for row in result.fetchall()]}

@api_router.get("/farm-health", response_model=List[FarmHealthEventResponse])
async def list_farm_health_events(
    location_id: Optional[int] = Query(None),
    event_type: Optional[HealthEventType] = Query(None),
    species: Optional[SpeciesType] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(FarmHealthEventModel)
        .options(selectinload(FarmHealthEventModel.location), selectinload(FarmHealthEventModel.creator))
        .order_by(FarmHealthEventModel.event_date.desc(), FarmHealthEventModel.id.desc())
    )
    if location_id:
        q = q.where(FarmHealthEventModel.location_id == location_id)
    if event_type:
        q = q.where(FarmHealthEventModel.event_type == event_type)
    if species:
        q = q.where(FarmHealthEventModel.species == species)
    if date_from:
        q = q.where(FarmHealthEventModel.event_date >= date_from)
    if date_to:
        q = q.where(FarmHealthEventModel.event_date <= date_to)
    if overdue_only:
        q = q.where(FarmHealthEventModel.next_due_date < date.today())
    result = await db.execute(q.limit(limit).offset(offset))
    events = result.scalars().all()
    out = []
    for ev in events:
        cats = await _resolve_categories_for_event(db, ev.category_ids)
        out.append(_health_event_response(ev, cats))
    return out

@api_router.post("/farm-health", response_model=FarmHealthEventResponse)
async def create_farm_health_event(
    data: FarmHealthEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    if data.event_type != HealthEventType.LOG:
        if not data.species:
            raise HTTPException(status_code=400, detail="species is required for non-LOG events")
        if not data.product_name:
            raise HTTPException(status_code=400, detail="product_name is required for non-LOG events")
        if not data.category_scope:
            raise HTTPException(status_code=400, detail="category_scope is required for non-LOG events")
        if data.category_scope == CategoryScope.SPECIFIC:
            if not data.category_ids:
                raise HTTPException(status_code=400, detail="category_ids required when category_scope is SPECIFIC")
            bad = await db.execute(
                select(Category).where(
                    and_(Category.id.in_(data.category_ids), Category.species != data.species)
                )
            )
            if bad.scalars().first():
                raise HTTPException(status_code=400, detail="Some category IDs do not belong to the specified species")

    # Compute next_due_date with vaccine-type-aware logic
    if data.next_due_date is not None:
        next_due = data.next_due_date
    elif data.event_type == HealthEventType.VACCINATION and data.vaccine_type_id is not None:
        vt_r = await db.execute(select(VaccineType).where(VaccineType.id == data.vaccine_type_id))
        vt = vt_r.scalar_one_or_none()
        next_due = (data.event_date + timedelta(days=vt.default_interval_days)) if (vt and vt.default_interval_days) else None
    else:
        next_due = await _compute_next_due(db, data.location_id, data.species, data.event_type, data.event_date)

    ev = FarmHealthEventModel(
        location_id=data.location_id,
        event_type=data.event_type,
        event_date=data.event_date,
        species=data.species,
        category_scope=data.category_scope,
        category_ids=data.category_ids,
        product_name=data.product_name,
        dosage=data.dosage,
        cost_per_head=data.cost_per_head,
        total_cost=data.total_cost,
        head_count=data.head_count,
        next_due_date=next_due,
        notes=data.notes,
        created_by=current_user.id,
        vaccine_type_id=data.vaccine_type_id,
    )
    db.add(ev)
    await db.commit()

    result = await db.execute(
        select(FarmHealthEventModel)
        .options(
            selectinload(FarmHealthEventModel.location),
            selectinload(FarmHealthEventModel.creator),
            selectinload(FarmHealthEventModel.vaccine_type),
        )
        .where(FarmHealthEventModel.id == ev.id)
    )
    ev = result.scalar_one()
    cats = await _resolve_categories_for_event(db, ev.category_ids)
    vt_name = ev.vaccine_type.name if ev.vaccine_type else None
    return _health_event_response(ev, cats, vaccine_type_name=vt_name)

@api_router.get("/farm-health/{event_id}", response_model=FarmHealthEventResponse)
async def get_farm_health_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(FarmHealthEventModel)
        .options(selectinload(FarmHealthEventModel.location), selectinload(FarmHealthEventModel.creator))
        .where(FarmHealthEventModel.id == event_id)
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Health event not found")
    cats = await _resolve_categories_for_event(db, ev.category_ids)
    return _health_event_response(ev, cats)

@api_router.put("/farm-health/{event_id}", response_model=FarmHealthEventResponse)
async def update_farm_health_event(
    event_id: int,
    data: FarmHealthEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(FarmHealthEventModel).where(FarmHealthEventModel.id == event_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Health event not found")

    if data.event_date is not None:
        ev.event_date = data.event_date
    if data.species is not None:
        ev.species = data.species
    if data.category_scope is not None:
        ev.category_scope = data.category_scope
    if data.category_ids is not None:
        ev.category_ids = data.category_ids
    if data.product_name is not None:
        ev.product_name = data.product_name
    if data.dosage is not None:
        ev.dosage = data.dosage
    if data.cost_per_head is not None:
        ev.cost_per_head = data.cost_per_head
    if data.total_cost is not None:
        ev.total_cost = data.total_cost
    if data.head_count is not None:
        ev.head_count = data.head_count
    if data.notes is not None:
        ev.notes = data.notes
    if data.vaccine_type_id is not None:
        ev.vaccine_type_id = data.vaccine_type_id

    # Compute next_due_date with vaccine-type-aware logic
    if data.next_due_date is not None:
        ev.next_due_date = data.next_due_date
    elif ev.event_type == HealthEventType.VACCINATION and ev.vaccine_type_id is not None:
        vt_r = await db.execute(select(VaccineType).where(VaccineType.id == ev.vaccine_type_id))
        vt = vt_r.scalar_one_or_none()
        ev.next_due_date = (ev.event_date + timedelta(days=vt.default_interval_days)) if (vt and vt.default_interval_days) else None
    else:
        ev.next_due_date = await _compute_next_due(db, ev.location_id, ev.species, ev.event_type, ev.event_date)

    await db.commit()

    result = await db.execute(
        select(FarmHealthEventModel)
        .options(
            selectinload(FarmHealthEventModel.location),
            selectinload(FarmHealthEventModel.creator),
            selectinload(FarmHealthEventModel.vaccine_type),
        )
        .where(FarmHealthEventModel.id == event_id)
    )
    ev = result.scalar_one()
    cats = await _resolve_categories_for_event(db, ev.category_ids)
    vt_name = ev.vaccine_type.name if ev.vaccine_type else None
    return _health_event_response(ev, cats, vaccine_type_name=vt_name)

@api_router.delete("/farm-health/{event_id}")
async def delete_farm_health_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(FarmHealthEventModel).where(FarmHealthEventModel.id == event_id))
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Health event not found")
    await db.delete(ev)
    await db.commit()
    return {"message": "Health event deleted"}

# ==================== VACCINE TYPE ROUTES ====================

@api_router.get("/vaccine-types", response_model=List[VaccineTypeResponse])
async def list_vaccine_types(
    species: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(VaccineType).where(VaccineType.is_active == True).order_by(VaccineType.name)
    )
    vts = result.scalars().all()
    if species:
        su = species.upper()
        vts = [vt for vt in vts if vt.species_applicability is None or su in vt.species_applicability]
    return vts

@api_router.post("/vaccine-types", response_model=VaccineTypeResponse)
async def create_vaccine_type(
    data: VaccineTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = await db.execute(select(VaccineType).where(VaccineType.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Vaccine type '{data.name}' already exists")
    vt = VaccineType(
        name=data.name,
        description=data.description,
        species_applicability=data.species_applicability,
        default_interval_days=data.default_interval_days,
        created_by=current_user.id,
    )
    db.add(vt)
    await db.commit()
    await db.refresh(vt)
    return vt

@api_router.put("/vaccine-types/{vt_id}", response_model=VaccineTypeResponse)
async def update_vaccine_type(
    vt_id: int,
    data: VaccineTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(VaccineType).where(VaccineType.id == vt_id))
    vt = result.scalar_one_or_none()
    if not vt:
        raise HTTPException(status_code=404, detail="Vaccine type not found")
    if data.name is not None:
        vt.name = data.name
    if data.description is not None:
        vt.description = data.description
    if data.species_applicability is not None:
        vt.species_applicability = data.species_applicability
    if data.default_interval_days is not None:
        vt.default_interval_days = data.default_interval_days
    if data.is_active is not None:
        vt.is_active = data.is_active
    vt.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(vt)
    return vt

@api_router.delete("/vaccine-types/{vt_id}")
async def delete_vaccine_type(
    vt_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(VaccineType).where(VaccineType.id == vt_id))
    vt = result.scalar_one_or_none()
    if not vt:
        raise HTTPException(status_code=404, detail="Vaccine type not found")
    in_use = await db.execute(
        select(func.count(FarmHealthEventModel.id)).where(FarmHealthEventModel.vaccine_type_id == vt_id)
    )
    if in_use.scalar() > 0:
        raise HTTPException(status_code=409, detail="Cannot delete: vaccine type is used in existing health events")
    vt.is_active = False
    vt.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Vaccine type deactivated"}

# Literal path — must be before any parameterised /farm-health/{id} routes
@api_router.get("/farm-health-events/last-vaccinations", response_model=List[LastVaccinationSummary])
async def get_last_vaccinations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get the most recent vaccination event ID per (location, species, vaccine_type)
    latest_ids_sq = (
        select(func.max(FarmHealthEventModel.id).label("max_id"))
        .where(
            and_(
                FarmHealthEventModel.event_type == HealthEventType.VACCINATION,
                FarmHealthEventModel.vaccine_type_id.isnot(None),
            )
        )
        .group_by(
            FarmHealthEventModel.location_id,
            FarmHealthEventModel.species,
            FarmHealthEventModel.vaccine_type_id,
        )
        .subquery()
    )

    result = await db.execute(
        select(FarmHealthEventModel)
        .options(
            selectinload(FarmHealthEventModel.location),
            selectinload(FarmHealthEventModel.vaccine_type),
        )
        .join(latest_ids_sq, FarmHealthEventModel.id == latest_ids_sq.c.max_id)
    )
    events = result.scalars().all()

    today = date.today()
    summaries = []
    for ev in events:
        days_since = (today - ev.event_date).days if ev.event_date else None
        is_overdue = bool(ev.next_due_date and today > ev.next_due_date)
        summaries.append(LastVaccinationSummary(
            location_id=ev.location_id,
            location_name=ev.location.name if ev.location else "",
            species=ev.species,
            vaccine_type_id=ev.vaccine_type_id,
            vaccine_type_name=ev.vaccine_type.name if ev.vaccine_type else "",
            last_event_date=ev.event_date,
            days_since=days_since,
            next_due_date=ev.next_due_date,
            is_overdue=is_overdue,
        ))

    def _sort_key(s):
        if s.is_overdue:
            return (0, s.next_due_date or date.min)
        if s.next_due_date:
            return (1, s.next_due_date)
        return (2, date.max)

    summaries.sort(key=_sort_key)
    return summaries

# ==================== REGISTRY SYNC ROUTES ====================
@api_router.post("/internal/sync/drain", response_model=SyncDrainResult)
async def drain_registry_sync(
    db: AsyncSession = Depends(get_db),
    caller_service_account: str = Depends(require_cloud_run_service_account),
):
    """Retries queued registry_sync_outbox rows. Called by a Cloud Run scheduler
    (or the Registry itself), not by ShambaManager users — see registry_auth.py."""
    result = await drain_outbox(db)
    return SyncDrainResult(**result)


@api_router.get("/integration/registry/tags")
async def search_registry_tags(
    q: Optional[str] = None,
    species: Optional[str] = None,
    location: Optional[str] = None,
    category: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Thin passthrough to the Registry's tag search, for the frontend animal-tag picker."""
    client = RegistryClient()
    try:
        return await client.search_tags(
            current_user.name,
            q=q,
            species=species,
            location=location,
            category=category,
            status=status_filter,
            limit=limit,
            cursor=cursor,
        )
    except RegistryUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Registry is unreachable: {exc}")


# NOTE: unlike /internal/sync/drain above, the two routes below are viewed and clicked by a
# human admin in the browser (the "Registry Sync" page), so they use normal ShambaManager
# JWT auth (require_roles) rather than the Cloud Run service-account dependency.
@api_router.get("/internal/sync/report", response_model=SyncReportResponse)
async def get_registry_sync_report(
    since: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Outbox rows stuck in CONFLICT/FAILED, plus a cross-check of our death/sale syncs
    against the Registry's own reconcile feed. Powers the admin Registry Sync page."""
    report = await registry_report.build_sync_report(db, since or (date.today() - timedelta(days=90)))
    return SyncReportResponse(
        since=report.since,
        generated_at=report.generated_at,
        outbox_issues=report.outbox_issues,
        reconcile_mismatches=report.reconcile_mismatches,
        reconcile_unavailable=report.reconcile_unavailable,
        reconcile_error=report.reconcile_error,
    )

@api_router.post("/internal/sync/{outbox_id}/retry", response_model=OutboxIssueResponse)
async def retry_registry_sync_row(
    outbox_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Manual retry from the admin Registry Sync page: re-queues one row to PENDING with
    attempts reset. Actual delivery happens on the next /internal/sync/drain cycle."""
    row = await registry_sync.retry_outbox_row(db, outbox_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Outbox row not found")
    return OutboxIssueResponse.model_validate(row)


# Include router
app.include_router(api_router)

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
