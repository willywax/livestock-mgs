from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Form
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy.orm import selectinload
import os
import re
import logging
import csv
import io
import uuid
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date, timezone, timedelta

from database import get_db, init_db, engine, Base
from models import (
    User, Location, Category, OpeningBalance, DailyLog, Event, StockLevel,
    UserRole, EventType, SpeciesType, Disease, AbortionStage,
    Animal, AnimalSex, AnimalAcquisitionType, AnimalStatus,
    HealthEventType, CategoryScope, HealthInterval, FarmHealthEvent as FarmHealthEventModel,
    VaccineType,
    BullAssignment, ReproductiveCycle, BCSRecord, AnimalPhoto, AnimalNote,
    ReproductiveCycleStatus, CalvingOutcome, PDResult,
    AnimalLocationHistory,
    AnimalIdentifier, AnimalIdentifierType, ReproductiveEvent, ReproductiveEventType,
    ReconciliationSession, ReconciliationEntry, Customer, SaleDetail, DeathCause, MortalityThreshold,
)
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
    HealthIntervalCreate, HealthIntervalUpdate, HealthIntervalResponse,
    FarmHealthEventCreate, FarmHealthEventUpdate, FarmHealthEventResponse,
    CategoryInfo, LastEventSummary,
    VaccineTypeCreate, VaccineTypeUpdate, VaccineTypeResponse,
    LastVaccinationSummary,
    BullAssignmentCreate, BullAssignmentUpdate, BullAssignmentResponse,
    ReproductiveCycleCreate, ReproductiveCycleUpdate, ReproductiveCycleResponse, AnimalReproductiveSummary,
    BCSRecordCreate, BCSRecordUpdate, BCSRecordResponse,
    AnimalPhotoCreate, AnimalPhotoUpdate, AnimalPhotoResponse,
    AnimalNoteCreate, AnimalNoteUpdate, AnimalNoteResponse,
    TimelineItem, LocationReproductionMetrics, ReproductionAnalyticsResponse,
    AnimalLocationHistoryResponse, ReconciliationRow, ReplaceTagRequest, ReplaceTagResponse,
    AnimalIdentifierCreate, AnimalIdentifierUpdate, AnimalIdentifierResponse, AnimalLookupResponse,
    AnimalIdentifierImportResult,
    ReproductiveEventCreate, ReproductiveEventResponse, ReproductiveSummaryResponse,
    ReconciliationSessionCreate, ReconciliationResultResponse, ReconciliationSessionSummary,
    PDTestImportResult,
    DeathCauseCreate, DeathCauseUpdate, DeathCauseResponse,
    MortalityThresholdUpdate, MortalityThresholdResponse, MortalityReportResponse,
    CustomerCreate, CustomerUpdate, CustomerResponse, CustomerDetailResponse,
    SaleDetailCreate, SaleDetailResponse, SalesLineItem, SalesReportResponse,
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
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS "
            "cause_of_death_id INTEGER REFERENCES death_causes(id)"
        ))
        await _seed_death_causes(conn)
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
        # Temporary tags for untagged newborns (nullable column with default: additive only).
        await conn.execute(text(
            "ALTER TABLE animals ADD COLUMN IF NOT EXISTS is_temp_tag BOOLEAN DEFAULT FALSE"
        ))
        # create_all() does not add columns to existing tables.
        for definition in (
            "reproductive_status VARCHAR(20) DEFAULT 'unknown'",
            "last_calving_date DATE",
            "last_pd_date DATE",
            "months_pregnant INTEGER",
            "services_without_conception INTEGER DEFAULT 0",
        ):
            await conn.execute(text(f"ALTER TABLE animals ADD COLUMN IF NOT EXISTS {definition}"))
        # create_all() does not add indexes to existing tables.
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
async def list_locations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    result = await db.execute(select(Location).where(Location.is_active == True).order_by(Location.name))
    locations = result.scalars().all()
    return [LocationResponse.model_validate(loc) for loc in locations]

@api_router.get("/locations/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
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
@api_router.get("/diseases", response_model=List[DiseaseResponse])
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
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
async def get_daily_log(
    log_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
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
            cause_of_death_id=e.cause_of_death_id,
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

    # Validate all structured causes before any event writes or stock changes.
    for event_data in data.events:
        await _validate_death_cause(db, event_data.event_type, event_data.cause_of_death_id)
    # Process events
    created_events = []
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
            cause_of_death_id=event_data.cause_of_death_id,
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
        await db.flush()  # populate event.id

        created_events.append(event)

        # Update stock levels
        if event_data.is_stock_event:
            await apply_event_to_stock(db, data.location_id, event_data)

    await db.commit()

    # Sync animal register per event, in order (best-effort: never rolls back the stock commit)
    sync_warnings_by_event = {}
    for event in created_events:
        sync_warnings_by_event[event.id] = await _sync_animals_from_event(db, event, daily_log, current_user)
    # A register rollback expires every loaded object, so reload what the response reads
    for event in created_events:
        await db.refresh(event)
    await db.refresh(daily_log)

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
            cause_of_death_id=event.cause_of_death_id,
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
            sync_warnings=sync_warnings_by_event.get(event.id) or None,
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

# ==================== ANIMAL REGISTER SYNC (best-effort) ====================
# Runs AFTER the stock commit. Failures here never roll back stock; they are
# logged and surfaced as sync_warnings on the response. Helpers take plain
# snapshots/values so a rollback (which expires ORM objects) cannot break them.
_FEMALE_CATEGORIES = {"koo", "mitamba", "ndama jike", "achishwa jike", "vichinda jike"}
_MALE_CATEGORIES = {"ndama dume", "achishwa dume", "maksai", "dume mbegu", "dume wadogo", "vichinda dume"}
_SYNC_FAILED_MSG = "Animal register could not be updated automatically (see server logs); stock was saved."


def _split_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    seen, out = set(), []
    for part in raw.split(","):
        tag = part.strip()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _infer_sex(category: Optional[Category]) -> Optional[AnimalSex]:
    """Sex implied by the seeded category name (None when it cannot be told)."""
    if category is None:
        return None
    name = (category.name_sw or "").strip().lower()
    if name in _FEMALE_CATEGORIES:
        return AnimalSex.FEMALE
    if name in _MALE_CATEGORIES:
        return AnimalSex.MALE
    return None


def _event_snapshot(event: Event, location_id: int, log_date: date) -> SimpleNamespace:
    return SimpleNamespace(
        id=event.id, event_type=event.event_type, species=event.species,
        category_id=event.category_id, from_category_id=event.from_category_id,
        to_category_id=event.to_category_id, from_location_id=event.from_location_id,
        to_location_id=event.to_location_id, animal_tags=event.animal_tags,
        offspring_tags=event.offspring_tags, location_id=location_id, log_date=log_date,
    )


async def _find_animal(db: AsyncSession, tag: str, species, prefer_location: Optional[int] = None,
                       prefer_status: Optional[AnimalStatus] = None) -> Optional[Animal]:
    rows = (await db.execute(
        select(Animal).where(and_(Animal.tag_number == tag, Animal.species == species)).order_by(Animal.id)
    )).scalars().all()
    if not rows:
        return None

    def rank(a: Animal):
        return (
            0 if prefer_status is not None and a.status == prefer_status else 1,
            0 if prefer_location is not None and a.location_id == prefer_location else 1,
            0 if a.status == AnimalStatus.ACTIVE else 1,
            a.id,
        )
    return sorted(rows, key=rank)[0]


def _set_status(animal: Animal, status: AnimalStatus) -> None:
    if animal.status != status:
        animal.status = status
        animal.status_changed_at = datetime.now(timezone.utc)


async def _restore_after_rollback(db: AsyncSession, *objs) -> None:
    """rollback() expires ORM objects; reload the ones the caller still uses."""
    for obj in objs:
        try:
            await db.refresh(obj)
        except Exception:
            logger.warning("Could not refresh %r after register-sync rollback", obj, exc_info=True)


_MAX_TEMP_ANIMALS_PER_EVENT = 50
_TEMP_PLACEHOLDERS = {"", "new", "temp"}


def _offspring_entries(raw: Optional[str], count: Optional[int]) -> List[str]:
    """Offspring entries for a birth, empties preserved ('KK-001, , KK-003' -> middle is untagged).

    A blank field means the newborns are untagged: one placeholder entry per head of `count`.
    """
    if raw is None or not raw.strip():
        return [""] * min(max(count or 0, 0), _MAX_TEMP_ANIMALS_PER_EVENT)
    return [part.strip() for part in raw.split(",")]


async def _generate_temp_tag(location_name: Optional[str], log_date: date, db: AsyncSession) -> str:
    """TEMP-<LOC>-<YYYYMMDD>-NNN: next free sequence for this prefix and date.

    Optimistic: the unique constraint (tag, species, location) still arbitrates concurrent writers.
    """
    prefix = re.sub(r"[^A-Za-z0-9]", "", location_name or "")[:3].upper() or "UNK"
    base = f"TEMP-{prefix}-{log_date.strftime('%Y%m%d')}"
    used = (await db.execute(
        select(func.count()).select_from(Animal).where(Animal.tag_number.like(f"{base}-%"))
    )).scalar() or 0
    seq = used + 1
    while True:  # skip past tags that already exist (e.g. after deletions)
        tag = f"{base}-{seq:03d}"
        taken = (await db.execute(select(Animal.id).where(Animal.tag_number == tag).limit(1))).first()
        if taken is None:
            return tag
        seq += 1


async def _sync_animals_from_event(db: AsyncSession, event: Event, daily_log: DailyLog,
                                   current_user: User) -> List[str]:
    """Apply an event to the individual animal register. Never raises; returns warnings."""
    warnings: List[str] = []
    try:
        et = event.event_type
        species = event.species
        event_id = event.id
        category_id = event.category_id
        to_location_id = event.to_location_id
        to_category_id = event.to_category_id
        log_location_id = daily_log.location_id
        log_date = daily_log.log_date
        user_id = current_user.id
        tags = _split_tags(event.animal_tags)
        offspring = _offspring_entries(event.offspring_tags, event.count) if et == EventType.BIRTH else []
        if not tags and not offspring:
            return warnings

        def warn(msg: str) -> None:
            logger.warning("Animal register sync (event %s): %s", event_id, msg)
            warnings.append(msg)

        async def create_animal_row(tag: str, acquisition: AnimalAcquisitionType,
                                    is_temp_tag: bool = False, notes: Optional[str] = None) -> Optional[Animal]:
            if not category_id:
                warn(f"Tag {tag}: no category on event, animal not created")
                return None
            sex = _infer_sex(await db.get(Category, category_id))
            if sex is None:
                warn(f"Tag {tag}: sex cannot be inferred from category, animal not created")
                return None
            animal = Animal(
                tag_number=tag, species=species, category_id=category_id,
                location_id=log_location_id, sex=sex, status=AnimalStatus.ACTIVE,
                acquisition_type=acquisition, acquisition_date=log_date, created_by=user_id,
                is_temp_tag=is_temp_tag, notes=notes,
            )
            db.add(animal)
            await db.flush()
            return animal

        for tag in tags:
            animal = await _find_animal(db, tag, species, prefer_location=log_location_id)
            if animal is None:
                if et in (EventType.BOUGHT, EventType.GIFT_IN):
                    await create_animal_row(tag, AnimalAcquisitionType.BOUGHT)
                else:
                    warn(f"Tag {tag}: not found in the animal register, skipped")
                continue

            if et in (EventType.BOUGHT, EventType.GIFT_IN):
                if animal.status in (AnimalStatus.DEAD, AnimalStatus.SOLD):
                    warn(f"Tag {tag}: register shows it as {animal.status.value}; not reactivated")
                else:
                    _set_status(animal, AnimalStatus.ACTIVE)
            elif et == EventType.DEATH:
                _set_status(animal, AnimalStatus.DEAD)
            elif et in (EventType.SOLD, EventType.GIFT_OUT):
                _set_status(animal, AnimalStatus.SOLD)
            elif et == EventType.MISSING:
                _set_status(animal, AnimalStatus.MISSING)
            elif et in (EventType.TRANSFER, EventType.CATEGORY_CHANGE, EventType.WEANING):
                if animal.status in (AnimalStatus.DEAD, AnimalStatus.SOLD):
                    warn(f"Tag {tag}: register shows it as {animal.status.value}; {et.value} not applied")
                    continue
                _set_status(animal, AnimalStatus.ACTIVE)
                if et == EventType.TRANSFER:
                    if not to_location_id:
                        warn(f"Tag {tag}: transfer has no destination, location unchanged")
                    elif animal.location_id != to_location_id:
                        clash = (await db.execute(select(Animal.id).where(and_(
                            Animal.tag_number == tag, Animal.species == species,
                            Animal.location_id == to_location_id, Animal.id != animal.id,
                        )))).first()
                        if clash:
                            warn(f"Tag {tag}: same tag already registered at the destination, location unchanged")
                        else:
                            db.add(AnimalLocationHistory(
                                animal_id=animal.id, from_location_id=animal.location_id,
                                to_location_id=to_location_id, moved_date=log_date,
                                event_id=event_id, created_by=user_id,
                            ))
                            animal.location_id = to_location_id
                elif to_category_id:
                    animal.category_id = to_category_id
            # BIRTH / ABORTION: nothing to change on the mother's record

        # Placeholders (blank / NEW / TEMP) get generated temp tags. Re-saving the event must not
        # duplicate them, so only the shortfall against temp animals already stamped with this
        # event's marker is created. Typed TEMP-* tags are kept as typed (flagged temp).
        temp_needed = sum(1 for t in offspring if t.lower() in _TEMP_PLACEHOLDERS)
        temp_stamp = f"Auto-created temp tag from birth event #{event_id}"
        temp_missing = temp_needed
        if temp_needed:
            already = (await db.execute(
                select(func.count()).select_from(Animal).where(
                    and_(Animal.is_temp_tag == True, Animal.notes == temp_stamp)  # noqa: E712
                )
            )).scalar() or 0
            temp_missing = max(0, temp_needed - already)
        location_name = None
        if temp_missing:
            location = await db.get(Location, log_location_id)
            location_name = location.name if location else "UNK"

        for tag in offspring:
            if tag.lower() in _TEMP_PLACEHOLDERS:
                if temp_missing <= 0:
                    continue
                temp_missing -= 1
                new_tag = await _generate_temp_tag(location_name, log_date, db)
                await create_animal_row(new_tag, AnimalAcquisitionType.BORN, is_temp_tag=True, notes=temp_stamp)
                continue
            existing = await _find_animal(db, tag, species)
            if existing is not None:
                warn(f"Offspring tag {tag}: already in the animal register, skipped")
                continue
            await create_animal_row(
                tag, AnimalAcquisitionType.BORN, is_temp_tag=tag.upper().startswith("TEMP-")
            )

        await db.commit()
    except Exception:
        logger.exception("Animal register sync failed for event %s", getattr(event, "id", None))
        try:
            await db.rollback()
        except Exception:
            logger.exception("Rollback after animal register sync failure also failed")
        await _restore_after_rollback(db, event, daily_log, current_user)
        warnings.append(_SYNC_FAILED_MSG)
    return warnings


_REVERSIBLE_STATUS = {
    EventType.DEATH: AnimalStatus.DEAD,
    EventType.SOLD: AnimalStatus.SOLD,
    EventType.GIFT_OUT: AnimalStatus.SOLD,
    EventType.MISSING: AnimalStatus.MISSING,
}


async def _reverse_animal_sync(db: AsyncSession, snap: SimpleNamespace, deleting: bool = False,
                               restore: tuple = ()) -> List[str]:
    """Undo an event's register effects (snapshot of the OLD event). Never raises; returns warnings.

    Animals auto-created by bought/gift_in/birth events are never deleted (they may already
    have photos, notes or history); a warning is returned when the event is being deleted.
    """
    warnings: List[str] = []
    try:
        et = snap.event_type
        tags = _split_tags(snap.animal_tags)

        def warn(msg: str) -> None:
            logger.warning("Animal register reverse (event %s): %s", snap.id, msg)
            warnings.append(msg)

        if et == EventType.TRANSFER:
            rows = (await db.execute(
                select(AnimalLocationHistory).where(AnimalLocationHistory.event_id == snap.id)
            )).scalars().all()
            for row in rows:
                animal = await db.get(Animal, row.animal_id)
                if animal is not None and animal.location_id == row.to_location_id and row.from_location_id:
                    clash = (await db.execute(select(Animal.id).where(and_(
                        Animal.tag_number == animal.tag_number, Animal.species == animal.species,
                        Animal.location_id == row.from_location_id, Animal.id != animal.id,
                    )))).first()
                    if clash:
                        warn(f"Tag {animal.tag_number}: same tag exists at the original location, not moved back")
                    else:
                        animal.location_id = row.from_location_id
                elif animal is not None:
                    warn(f"Tag {animal.tag_number}: moved again since this event, location left unchanged")
                await db.delete(row)
        elif et in _REVERSIBLE_STATUS:
            expected = _REVERSIBLE_STATUS[et]
            for tag in tags:
                animal = await _find_animal(db, tag, snap.species, prefer_location=snap.location_id,
                                            prefer_status=expected)
                if animal is None:
                    continue
                if animal.status == expected:
                    _set_status(animal, AnimalStatus.ACTIVE)
                else:
                    warn(f"Tag {tag}: status is {animal.status.value} (changed since this event), left unchanged")
        elif et in (EventType.CATEGORY_CHANGE, EventType.WEANING):
            old_cat = snap.from_category_id or snap.category_id
            for tag in tags:
                animal = await _find_animal(db, tag, snap.species, prefer_location=snap.location_id)
                if animal is not None and old_cat and animal.category_id == snap.to_category_id:
                    animal.category_id = old_cat
        elif deleting and et in (EventType.BOUGHT, EventType.GIFT_IN, EventType.BIRTH):
            if tags or (et == EventType.BIRTH and snap.offspring_tags):
                warn("Animals created by this event were left in the register; remove them manually if wrong")

        await db.commit()
    except Exception:
        logger.exception("Animal register reverse failed for event %s", snap.id)
        try:
            await db.rollback()
        except Exception:
            logger.exception("Rollback after animal register reverse failure also failed")
        await _restore_after_rollback(db, *restore)
        warnings.append(_SYNC_FAILED_MSG)
    return warnings


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

    await _validate_death_cause(db, event_data.event_type, event_data.cause_of_death_id)

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
        cause_of_death_id=event_data.cause_of_death_id,
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
    await db.flush()  # populate event.id

    # Update stock levels
    if event_data.is_stock_event:
        await apply_event_to_stock(db, log.location_id, event_data)

    # Mark log as having events
    log.has_events = True

    await db.commit()

    # Sync animal register (best-effort: never rolls back the stock commit)
    sync_warnings = await _sync_animals_from_event(db, event, log, current_user)
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
        cause_of_death_id=event.cause_of_death_id,
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
        sync_warnings=sync_warnings or None,
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

    effective_type = data.event_type or event.event_type
    if "cause_of_death_id" in data.model_fields_set:
        await _validate_death_cause(db, effective_type, data.cause_of_death_id,
                                    existing_id=event.cause_of_death_id)
    # ADDED: Type-specific field guard — reject fields that don't apply to event_type
    _type_fields: dict = {
        EventType.DEATH:    {"cause_of_death", "disease_id", "days_sick", "attending_vet"},
        EventType.BIRTH:    {"mother_tag", "offspring_tags"},
        EventType.SOLD:     {"buyer_name", "buyer_phone", "buyer_address", "sale_price"},
        EventType.GIFT_IN:  {"gift_party_name", "gift_party_phone", "gift_reason"},
        EventType.GIFT_OUT: {"gift_party_name", "gift_party_phone", "gift_reason"},
        EventType.ABORTION: {"abortion_stage", "mother_tag"},
    }
    _all_typed = {f for fields in _type_fields.values() for f in fields}
    _allowed   = _type_fields.get(effective_type, set())
    _sent      = {k for k, v in data.model_dump(exclude_none=True).items() if k in _all_typed}
    _rejected  = _sent - _allowed
    if _rejected:
        raise HTTPException(
            status_code=400,
            detail=f"Fields not applicable to {effective_type.value} event: {', '.join(sorted(_rejected))}"
        )

    # Undo the OLD event's animal-register effects (best-effort, own commit, before any stock change)
    daily_log = event.daily_log
    sync_warnings: List[str] = await _reverse_animal_sync(
        db, _event_snapshot(event, location_id, daily_log.log_date), restore=(event, daily_log)
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

    # Changing the event type drops the old type's specific fields and resets the stock flag
    # (only ABORTION is a non-stock event), mirroring how the create form sets it.
    if data.event_type is not None and data.event_type != event.event_type:
        for _field in _all_typed - _type_fields.get(effective_type, set()):
            setattr(event, _field, None)
        event.is_stock_event = effective_type != EventType.ABORTION

    # Update event fields
    if "cause_of_death_id" in data.model_fields_set:
        event.cause_of_death_id = data.cause_of_death_id
    if effective_type != EventType.DEATH:
        event.cause_of_death_id = None
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
    if data.abortion_stage is not None:
        event.abortion_stage = data.abortion_stage
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

    await db.commit()

    # Re-apply the NEW event to the animal register (best-effort, after the stock commit)
    sync_warnings += await _sync_animals_from_event(db, event, daily_log, current_user)
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
        cause_of_death_id=event.cause_of_death_id,
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
        # ADDED: Gift-specific fields
        gift_party_name=event.gift_party_name,
        gift_party_phone=event.gift_party_phone,
        gift_reason=event.gift_reason,
        sync_warnings=sync_warnings or None,
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
    
    # Undo the event's animal-register effects first (best-effort, own commit)
    sync_warnings = await _reverse_animal_sync(
        db, _event_snapshot(event, location_id, daily_log.log_date), deleting=True,
        restore=(event, daily_log),
    )
    # Any history row still pointing at this event (e.g. reverse failed) must not block the delete
    await db.execute(
        update(AnimalLocationHistory).where(AnimalLocationHistory.event_id == event.id).values(event_id=None)
    )

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
    return {"message": "Event deleted successfully", "sync_warnings": sync_warnings or None}

# ==================== STOCK LEVEL ROUTES ====================
@api_router.get("/stock-levels", response_model=List[StockLevelResponse])
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
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    today = date.today()
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
    # Explicit dates override period_days; with neither, behaviour is unchanged (last period_days, open-ended).
    period_start = date_from or ((date_to or today) - timedelta(days=period_days))
    
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
    if date_to:
        perf_query = perf_query.where(DailyLog.log_date <= date_to)
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
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
        is_temp_tag=bool(animal.is_temp_tag),
        reproductive_status=animal.reproductive_status or "unknown",
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
    is_temp_tag: Optional[bool] = None,
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
    if is_temp_tag is not None:
        query = query.where(Animal.is_temp_tag == is_temp_tag)
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

@api_router.get("/animals/register-reconciliation", response_model=List[ReconciliationRow])
async def register_reconciliation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    """Per location + species: stock_levels total vs individually registered active animals."""
    stock_rows = (await db.execute(
        select(StockLevel.location_id, StockLevel.species, func.sum(StockLevel.current_count))
        .group_by(StockLevel.location_id, StockLevel.species)
    )).all()
    reg_rows = (await db.execute(
        select(Animal.location_id, Animal.species, func.count(Animal.id))
        .where(Animal.status == AnimalStatus.ACTIVE)
        .group_by(Animal.location_id, Animal.species)
    )).all()
    stock = {(loc, sp): int(total or 0) for loc, sp, total in stock_rows}
    registered = {(loc, sp): int(n) for loc, sp, n in reg_rows}
    names = {loc.id: loc.name for loc in (await db.execute(select(Location))).scalars().all()}

    rows = []
    for key in set(stock) | set(registered):
        loc_id, sp = key
        stock_count = stock.get(key, 0)
        reg = registered.get(key, 0)
        rows.append(ReconciliationRow(
            location_id=loc_id,
            location_name=names.get(loc_id, f"Location {loc_id}"),
            species=sp,
            stock_count=stock_count,
            registered_active=reg,
            registered_pct=round(reg / stock_count * 100, 1) if stock_count else None,
            unregistered=stock_count - reg,
        ))
    rows.sort(key=lambda r: (r.location_name, r.species.value))
    return rows

@api_router.get("/animals/lookup-by-id", response_model=AnimalLookupResponse)
async def lookup_animal_by_id(
    id_type: AnimalIdentifierType,
    id_value: str = Query(min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    result = await db.execute(
        select(Animal, AnimalIdentifier)
        .join(AnimalIdentifier, AnimalIdentifier.animal_id == Animal.id)
        .options(selectinload(Animal.category), selectinload(Animal.location), selectinload(Animal.creator))
        .where(AnimalIdentifier.id_type == id_type, AnimalIdentifier.id_value == id_value,
               AnimalIdentifier.is_active.is_(True))
        .limit(2)
    )
    matches = result.all()
    if not matches:
        raise HTTPException(status_code=404, detail="Identifier not found")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Identifier matches multiple animals")
    animal, identifier = matches[0]
    return AnimalLookupResponse(animal=_animal_response(animal),
                                matched_id=AnimalIdentifierResponse.model_validate(identifier))


@api_router.get("/animals/repeat-breeders")
async def list_repeat_breeders(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    query = select(Animal, Location.name).join(Location, Animal.location_id == Location.id).where(
        Animal.sex == AnimalSex.FEMALE,
        Animal.services_without_conception >= REPEAT_BREEDER_THRESHOLD,
    )
    if location_id is not None:
        query = query.where(Animal.location_id == location_id)
    if species is not None:
        query = query.where(Animal.species == species)
    rows = (await db.execute(query.order_by(Animal.services_without_conception.desc(), Animal.id))).all()
    return [{"tag_number": animal.tag_number, "species": animal.species, "location_name": name,
             "services_without_conception": animal.services_without_conception,
             "last_pd_date": animal.last_pd_date, "reproductive_status": animal.reproductive_status}
            for animal, name in rows]


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

@api_router.get("/animals/{animal_id}/location-history", response_model=List[AnimalLocationHistoryResponse])
async def get_animal_location_history(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    if (await db.execute(select(Animal.id).where(Animal.id == animal_id))).first() is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    rows = (await db.execute(
        select(AnimalLocationHistory)
        .options(selectinload(AnimalLocationHistory.from_location), selectinload(AnimalLocationHistory.to_location))
        .where(AnimalLocationHistory.animal_id == animal_id)
        .order_by(AnimalLocationHistory.moved_date.desc(), AnimalLocationHistory.id.desc())
    )).scalars().all()
    return [
        AnimalLocationHistoryResponse(
            id=r.id, animal_id=r.animal_id,
            from_location_id=r.from_location_id,
            from_location_name=r.from_location.name if r.from_location else None,
            to_location_id=r.to_location_id,
            to_location_name=r.to_location.name if r.to_location else None,
            moved_date=r.moved_date, event_id=r.event_id, notes=r.notes, created_at=r.created_at,
        )
        for r in rows
    ]

@api_router.post("/animals/{animal_id}/replace-tag", response_model=ReplaceTagResponse)
async def replace_animal_tag(
    animal_id: int,
    data: ReplaceTagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    """Replace a temporary tag (TEMP-...) with the real ear-tag number."""
    animal = (await db.execute(select(Animal).where(Animal.id == animal_id))).scalar_one_or_none()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    if not animal.is_temp_tag:
        raise HTTPException(
            status_code=400,
            detail="This animal does not have a temporary tag. Use the edit endpoint to change tags.",
        )
    new_tag = data.new_tag_number.strip()
    old_tag = animal.tag_number
    animal_pk = animal.id
    if not new_tag:
        raise HTTPException(status_code=400, detail="New tag number cannot be blank")
    if new_tag == old_tag:
        raise HTTPException(status_code=400, detail="New tag is the same as the current tag")
    clash = (await db.execute(
        select(func.count()).select_from(Animal).where(and_(
            Animal.tag_number == new_tag,
            Animal.species == animal.species,
            Animal.location_id == animal.location_id,
            Animal.id != animal.id,
        ))
    )).scalar()
    if clash:
        raise HTTPException(status_code=409, detail="Tag already in use at this location")

    animal.tag_number = new_tag
    animal.is_temp_tag = False
    animal.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tag already in use at this location")
    return ReplaceTagResponse(message="Tag replaced", old_tag=old_tag, new_tag=new_tag, animal_id=animal_pk)

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
        if data.location_id != animal.location_id:
            # Movement history (same transaction); manual edit, so no event_id
            db.add(AnimalLocationHistory(
                animal_id=animal.id,
                from_location_id=animal.location_id,
                to_location_id=data.location_id,
                moved_date=datetime.now(timezone.utc).date(),
                notes="Location changed by editing the animal record",
                created_by=current_user.id,
            ))
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

    # Movement history (same transaction as the move; event_id links the TRANSFER event above)
    await db.flush()
    db.add(AnimalLocationHistory(
        animal_id=animal.id,
        from_location_id=old_location_id,
        to_location_id=data.to_location_id,
        moved_date=data.transfer_date,
        event_id=event.id,
        notes=data.notes,
        created_by=current_user.id,
    ))
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

# ==================== REPRODUCTION & ANIMAL PROFILE ====================
# Added with the reproduction schema (docs/decisions/0008). Registered BEFORE
# app.include_router(api_router) below: routes added after that call are not served.
_ANY_ROLE = (UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)
GESTATION_DAYS = 283
BREEDING_AGE_MONTHS = {"cattle": 24, "sheep": 18, "goats": 18}
REPEAT_BREEDER_THRESHOLD = 3
ALLOWED_PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024


class _GCSUnavailable(Exception):
    """GCS_BUCKET_NAME unset or google-cloud-storage not installed."""


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


@api_router.get("/bull-assignments", response_model=List[BullAssignmentResponse])
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


@api_router.post("/bull-assignments", response_model=BullAssignmentResponse)
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


@api_router.put("/bull-assignments/{assignment_id}", response_model=BullAssignmentResponse)
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


@api_router.delete("/bull-assignments/{assignment_id}")
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


# ---------- Reproductive cycles ----------
_CYCLE_LOAD = (
    selectinload(ReproductiveCycle.animal).selectinload(Animal.location),
    selectinload(ReproductiveCycle.bull_assignment).selectinload(BullAssignment.bull),
)
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


@api_router.get("/reproductive-cycles", response_model=List[ReproductiveCycleResponse])
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


@api_router.post("/reproductive-cycles", response_model=ReproductiveCycleResponse)
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
    return _cycle_response(await _load_cycle(db, cycle.id))


@api_router.get("/reproductive-cycles/{cycle_id}", response_model=ReproductiveCycleResponse)
async def get_reproductive_cycle(
    cycle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return _cycle_response(await _load_cycle(db, cycle_id))


@api_router.put("/reproductive-cycles/{cycle_id}", response_model=ReproductiveCycleResponse)
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
    return _cycle_response(await _load_cycle(db, cycle_id))


@api_router.delete("/reproductive-cycles/{cycle_id}")
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
    return {"message": "Reproductive cycle deleted"}


@api_router.get("/animals/{animal_id}/reproductive-history", response_model=AnimalReproductiveSummary)
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


@api_router.get("/bcs-records", response_model=List[BCSRecordResponse])
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


@api_router.post("/bcs-records", response_model=BCSRecordResponse)
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


@api_router.put("/bcs-records/{record_id}", response_model=BCSRecordResponse)
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


@api_router.delete("/bcs-records/{record_id}")
async def delete_bcs_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    await db.delete(await _load_bcs(db, record_id))
    await db.commit()
    return {"message": "BCS record deleted"}


# ---------- Animal photos (Google Cloud Storage) ----------
def _gcs_bucket():
    """Sync (run in a thread). google.cloud.storage is imported lazily on purpose."""
    bucket_name = os.environ.get("GCS_BUCKET_NAME")
    if not bucket_name:
        raise _GCSUnavailable("GCS_BUCKET_NAME is not set")
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise _GCSUnavailable("google-cloud-storage is not installed") from exc
    return storage.Client().bucket(bucket_name)


def _gcs_upload(path: str, data: bytes, content_type: str) -> None:
    _gcs_bucket().blob(path).upload_from_string(data, content_type=content_type)


def _gcs_delete(path: str) -> None:
    bucket = _gcs_bucket()
    from google.api_core.exceptions import NotFound
    try:
        bucket.blob(path).delete()
    except NotFound:
        pass  # already gone: the DB row can still be removed


def _gcs_sign_urls(paths: List[str]) -> dict:
    """1-hour v4 signed GET URLs. Falls back to IAM signing when the credentials have no private key."""
    bucket = _gcs_bucket()
    expiry = timedelta(hours=1)
    iam_args = None
    urls = {}
    for path in paths:
        blob = bucket.blob(path)
        try:
            urls[path] = blob.generate_signed_url(version="v4", expiration=expiry, method="GET")
        except Exception:
            if iam_args is None:
                import google.auth
                from google.auth.transport.requests import Request
                creds, _ = google.auth.default()
                creds.refresh(Request())
                iam_args = {"service_account_email": creds.service_account_email, "access_token": creds.token}
            urls[path] = blob.generate_signed_url(version="v4", expiration=expiry, method="GET", **iam_args)
    return urls


def _sniff_image_ext(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def _photo_responses(photos: List[AnimalPhoto]) -> List[AnimalPhotoResponse]:
    responses = [AnimalPhotoResponse.model_validate(p) for p in photos]
    if not responses:
        return responses
    if not os.environ.get("GCS_BUCKET_NAME"):
        for r in responses:
            r.warning = "GCS_BUCKET_NAME is not set; photo URLs are unavailable"
        return responses
    try:
        urls = await run_in_threadpool(_gcs_sign_urls, [p.gcs_path for p in photos])
    except Exception as exc:
        logger.warning("Photo URL signing failed: %s", type(exc).__name__)
        for r in responses:
            r.warning = "Could not generate photo URLs"
        return responses
    for r in responses:
        r.photo_url = urls.get(r.gcs_path)
    return responses


async def _load_photo(db: AsyncSession, animal_id: int, photo_id: int) -> AnimalPhoto:
    result = await db.execute(
        select(AnimalPhoto).where(and_(AnimalPhoto.id == photo_id, AnimalPhoto.animal_id == animal_id))
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo


@api_router.get("/animals/{animal_id}/photos", response_model=List[AnimalPhotoResponse])
async def list_animal_photos(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _require_animal(db, animal_id)
    result = await db.execute(
        select(AnimalPhoto).where(AnimalPhoto.animal_id == animal_id)
        .order_by(AnimalPhoto.is_primary.desc(), AnimalPhoto.uploaded_at.desc(), AnimalPhoto.id.desc())
    )
    return await _photo_responses(result.scalars().all())


@api_router.post("/animals/{animal_id}/photos", response_model=AnimalPhotoResponse)
async def upload_animal_photo(
    animal_id: int,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    taken_date: Optional[date] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(db, animal_id)
    if not os.environ.get("GCS_BUCKET_NAME"):
        raise HTTPException(status_code=503, detail="Photo storage is not configured")
    content_type = (file.content_type or "").lower()
    declared_ext = ALLOWED_PHOTO_TYPES.get(content_type)
    if declared_ext is None:
        raise HTTPException(status_code=415, detail="Only image/jpeg, image/png and image/webp are accepted")
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo exceeds the 10 MB limit")
    ext = _sniff_image_ext(data)
    if ext is None or ext != declared_ext:
        raise HTTPException(status_code=415, detail="File content does not match an allowed image type")
    try:
        meta = AnimalPhotoCreate(caption=caption, taken_date=taken_date)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False))

    path = f"animals/{animal_id}/{uuid.uuid4()}.{ext}"
    try:
        await run_in_threadpool(_gcs_upload, path, data, content_type)
    except _GCSUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Photo storage is unavailable: {exc}")
    except Exception as exc:
        logger.warning("Photo upload failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Photo upload to storage failed")

    existing = (await db.execute(
        select(func.count(AnimalPhoto.id)).where(AnimalPhoto.animal_id == animal_id)
    )).scalar()
    photo = AnimalPhoto(
        animal_id=animal_id, gcs_path=path, caption=meta.caption, taken_date=meta.taken_date,
        is_primary=(existing == 0), uploaded_by=current_user.id,
    )
    db.add(photo)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            await run_in_threadpool(_gcs_delete, path)  # best effort: avoid an orphaned object
        except Exception:
            logger.warning("Could not remove orphaned photo object after DB failure")
        raise
    return (await _photo_responses([photo]))[0]


@api_router.put("/animals/{animal_id}/photos/{photo_id}", response_model=AnimalPhotoResponse)
async def update_animal_photo(
    animal_id: int,
    photo_id: int,
    data: AnimalPhotoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    photo = await _load_photo(db, animal_id, photo_id)
    if "caption" in data.model_fields_set:
        photo.caption = data.caption
    if "taken_date" in data.model_fields_set:
        photo.taken_date = data.taken_date
    if data.is_primary is not None:
        if data.is_primary:
            await db.execute(
                update(AnimalPhoto)
                .where(and_(AnimalPhoto.animal_id == animal_id, AnimalPhoto.id != photo_id))
                .values(is_primary=False)
            )
        photo.is_primary = data.is_primary
    await db.commit()
    return (await _photo_responses([photo]))[0]


@api_router.delete("/animals/{animal_id}/photos/{photo_id}")
async def delete_animal_photo(
    animal_id: int,
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    photo = await _load_photo(db, animal_id, photo_id)
    try:
        await run_in_threadpool(_gcs_delete, photo.gcs_path)  # object first; keep the row if this fails
    except _GCSUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Photo storage is unavailable: {exc}")
    except Exception as exc:
        logger.warning("Photo delete failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Could not delete the photo from storage")
    await db.delete(photo)
    await db.commit()
    return {"message": "Photo deleted"}


# ---------- Animal notes ----------
async def _load_note(db: AsyncSession, animal_id: int, note_id: int) -> AnimalNote:
    result = await db.execute(
        select(AnimalNote).where(and_(AnimalNote.id == note_id, AnimalNote.animal_id == animal_id))
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@api_router.get("/animals/{animal_id}/notes", response_model=List[AnimalNoteResponse])
async def list_animal_notes(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _require_animal(db, animal_id)
    result = await db.execute(
        select(AnimalNote).where(AnimalNote.animal_id == animal_id)
        .order_by(AnimalNote.note_date.desc(), AnimalNote.id.desc())
    )
    return [AnimalNoteResponse.model_validate(n) for n in result.scalars().all()]


@api_router.post("/animals/{animal_id}/notes", response_model=AnimalNoteResponse)
async def create_animal_note(
    animal_id: int,
    data: AnimalNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(db, animal_id)
    note = AnimalNote(animal_id=animal_id, **data.model_dump(), created_by=current_user.id)
    db.add(note)
    await db.commit()
    return AnimalNoteResponse.model_validate(note)


@api_router.put("/animals/{animal_id}/notes/{note_id}", response_model=AnimalNoteResponse)
async def update_animal_note(
    animal_id: int,
    note_id: int,
    data: AnimalNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    note = await _load_note(db, animal_id, note_id)
    for key in data.model_fields_set:
        value = getattr(data, key)
        if value is not None:  # all three note fields are non-nullable
            setattr(note, key, value)
    await db.commit()
    return AnimalNoteResponse.model_validate(note)


@api_router.delete("/animals/{animal_id}/notes/{note_id}")
async def delete_animal_note(
    animal_id: int,
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    await db.delete(await _load_note(db, animal_id, note_id))
    await db.commit()
    return {"message": "Note deleted"}


@api_router.post("/admin/import/animal-identifiers", response_model=AnimalIdentifierImportResult)
async def import_animal_identifiers(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    result = AnimalIdentifierImportResult(matched=0, identifiers_added=0, already_existed=0,
                                         repro_fields_updated=0, unmatched_eids=[])
    tag_types = {"uhf ear tag": AnimalIdentifierType.UHF_TAG,
                 "ear tag": AnimalIdentifierType.VISUAL_TAG, "other": AnimalIdentifierType.OTHER}
    # Iterate the spooled upload without loading the full CSV into memory.
    stream = io.TextIOWrapper(file.file, encoding="utf-8-sig", newline="")
    try:
        # SQLite's legacy transaction mode does not BEGIN for SELECTs. Ensure
        # releasing an insert savepoint cannot commit before the whole import.
        connection = await db.connection()
        if connection.dialect.name == "sqlite":
            raw = await connection.get_raw_connection()
            if not raw.driver_connection.in_transaction:
                await connection.exec_driver_sql("BEGIN")
        reader = csv.DictReader(stream, strict=True)
        required = {"eid", "eid_short", "reader_code"}
        required.update(f"tag_{i}{suffix}" for i in range(1, 5) for suffix in ("", "_type"))
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise HTTPException(status_code=400, detail="CSV is missing required baseline columns")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise HTTPException(status_code=400, detail=f"CSV row {reader.line_num}: incorrect column count")
            row = {key: value.strip() for key, value in row.items()}
            if not any(row.values()):
                continue
            values = [(AnimalIdentifierType.EID, row["eid"]),
                      (AnimalIdentifierType.READER_CODE, row["reader_code"])]
            for i in range(1, 5):
                kind = tag_types.get(row[f"tag_{i}_type"].lower())
                if kind:
                    values.append((kind, row[f"tag_{i}"]))
            if any(len(value) > 100 for _, value in values):
                raise HTTPException(status_code=400, detail=f"CSV row {reader.line_num}: identifier exceeds 100 characters")
            filters = []
            if row.get("species"):
                try:
                    filters.append(Animal.species == SpeciesType(row["species"].lower()))
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"CSV row {reader.line_num}: invalid species")
            if row.get("farm"):
                filters.append(func.lower(Location.name) == row["farm"].lower())
            animal = None
            for tag in (row["tag_1"], row["tag_2"], row["tag_3"], row["tag_4"]):
                if not tag:
                    continue
                matches = (await db.execute(select(Animal).join(Location, Animal.location_id == Location.id)
                           .where(Animal.tag_number == tag, *filters).limit(2))).scalars().all()
                if len(matches) > 1:
                    break
                if matches:
                    animal = matches[0]
                    break
            if animal is None:
                result.unmatched_eids.append(row["eid_short"])
                continue
            result.matched += 1
            # Optional reproductive baseline columns; identifier-only imports remain valid.
            # A bad reproductive value is skipped; it never fails the row or the import.
            calving = None
            for parse in (date.fromisoformat, lambda s: datetime.strptime(s, "%d/%m/%Y").date()):
                try:
                    calving = parse(row.get("last_calving", ""))
                    break
                except ValueError:
                    continue
            pregnancy = row.get("pregnancy", "").lower()
            repro = {}
            if calving:
                repro["last_calving_date"] = calving
            if pregnancy == "yes":
                repro["reproductive_status"] = "pregnant"
                try:
                    months = int(row.get("months_pregnant", ""))
                except ValueError:
                    months = None
                repro["months_pregnant"] = months if months is not None and months >= 0 else None
            elif pregnancy in ("no", "") and calving:
                repro["reproductive_status"] = "open"
                repro["months_pregnant"] = None
            changed = False
            for field, new_value in repro.items():
                if getattr(animal, field) != new_value:
                    setattr(animal, field, new_value)
                    changed = True
            if changed:
                result.repro_fields_updated += 1
            for kind, value in values:
                if not value or (kind == AnimalIdentifierType.VISUAL_TAG and value == animal.tag_number):
                    continue
                conditions = (AnimalIdentifier.animal_id == animal.id, AnimalIdentifier.id_type == kind,
                              AnimalIdentifier.id_value == value)
                if (await db.execute(select(AnimalIdentifier.id).where(*conditions))).scalar_one_or_none() is not None:
                    result.already_existed += 1
                    continue
                try:
                    async with db.begin_nested():
                        db.add(AnimalIdentifier(animal_id=animal.id, id_type=kind, id_value=value,
                                                created_by=current_user.id))
                        await db.flush()
                except IntegrityError:
                    if (await db.execute(select(AnimalIdentifier.id).where(*conditions))).scalar_one_or_none() is None:
                        raise
                    result.already_existed += 1
                else:
                    result.identifiers_added += 1
        await db.commit()
    except (UnicodeError, csv.Error):
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid CSV; upload a UTF-8 CSV file")
    except Exception:
        await db.rollback()
        raise
    finally:
        stream.detach()  # UploadFile owns the underlying file.
    return result


# ---------- Animal identifiers ----------
async def _load_identifier(db: AsyncSession, animal_id: int, identifier_id: int):
    result = await db.execute(select(AnimalIdentifier).where(
        AnimalIdentifier.id == identifier_id, AnimalIdentifier.animal_id == animal_id,
    ))
    identifier = result.scalar_one_or_none()
    if identifier is None:
        raise HTTPException(status_code=404, detail="Identifier not found")
    return identifier


async def _save_identifier(db: AsyncSession, identifier: AnimalIdentifier):
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Identifier already exists for this animal")
    await db.refresh(identifier)
    return AnimalIdentifierResponse.model_validate(identifier)


@api_router.get("/animals/{animal_id}/identifiers", response_model=List[AnimalIdentifierResponse])
async def list_animal_identifiers(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _require_animal(db, animal_id)
    result = await db.execute(select(AnimalIdentifier).where(AnimalIdentifier.animal_id == animal_id)
                             .order_by(AnimalIdentifier.id_type, AnimalIdentifier.created_at, AnimalIdentifier.id))
    return [AnimalIdentifierResponse.model_validate(item) for item in result.scalars().all()]


@api_router.post("/animals/{animal_id}/identifiers", response_model=AnimalIdentifierResponse)
async def create_animal_identifier(
    animal_id: int,
    data: AnimalIdentifierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(db, animal_id)
    identifier = AnimalIdentifier(animal_id=animal_id, created_by=current_user.id, **data.model_dump())
    db.add(identifier)
    return await _save_identifier(db, identifier)


@api_router.put("/animals/{animal_id}/identifiers/{identifier_id}", response_model=AnimalIdentifierResponse)
async def update_animal_identifier(
    animal_id: int,
    identifier_id: int,
    data: AnimalIdentifierUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    identifier = await _load_identifier(db, animal_id, identifier_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(identifier, key, value)
    return await _save_identifier(db, identifier)


@api_router.delete("/animals/{animal_id}/identifiers/{identifier_id}")
async def delete_animal_identifier(
    animal_id: int,
    identifier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    identifier = await _load_identifier(db, animal_id, identifier_id)
    await db.delete(identifier)
    await db.commit()
    return {"message": "Identifier deleted"}


# ---------- Animal timeline ----------
@api_router.get("/animals/{animal_id}/timeline", response_model=List[TimelineItem])
async def get_animal_timeline(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    animal = await _require_animal(db, animal_id)
    items: List[TimelineItem] = []

    cycles = (await db.execute(
        select(ReproductiveCycle).options(*_CYCLE_LOAD).where(ReproductiveCycle.animal_id == animal_id)
    )).scalars().all()
    for c in cycles:
        label = f"Cycle {c.cycle_number}"
        if c.service_date:
            bull = c.bull_assignment.bull.tag_number if c.bull_assignment and c.bull_assignment.bull else None
            detail = f"{c.service_type.value if c.service_type else 'natural'} service" + (f", bull {bull}" if bull else "")
            items.append(TimelineItem(date=c.service_date, event_category="REPRODUCTION",
                                      title=f"{label}: service", detail=detail,
                                      source_table="reproductive_cycles", source_id=c.id))
        if c.pd_check_date:
            detail = c.pd_result.value if c.pd_result else None
            if detail and c.pd_months_pregnant is not None:
                detail += f", {c.pd_months_pregnant} months"
            items.append(TimelineItem(date=c.pd_check_date, event_category="REPRODUCTION",
                                      title=f"{label}: PD check", detail=detail,
                                      source_table="reproductive_cycles", source_id=c.id))
        if c.actual_calving_date:
            detail = c.calving_outcome.value if c.calving_outcome else None
            items.append(TimelineItem(date=c.actual_calving_date, event_category="REPRODUCTION",
                                      title=f"{label}: calving", detail=detail,
                                      source_table="reproductive_cycles", source_id=c.id))

    health = (await db.execute(
        select(FarmHealthEventModel).where(and_(
            FarmHealthEventModel.location_id == animal.location_id,
            FarmHealthEventModel.species == animal.species,
        ))
    )).scalars().all()
    for h in health:
        # category_ids is a JSON list (not a PG array); null/empty means all categories.
        if h.category_scope == CategoryScope.SPECIFIC and h.category_ids and animal.category_id not in h.category_ids:
            continue
        title = h.event_type.value.title() + (f": {h.product_name}" if h.product_name else "")
        items.append(TimelineItem(date=h.event_date, event_category="HEALTH", title=title,
                                  detail=h.notes or h.dosage, source_table="farm_health_events", source_id=h.id))

    for r in (await db.execute(select(BCSRecord).where(BCSRecord.animal_id == animal_id))).scalars().all():
        items.append(TimelineItem(date=r.score_date, event_category="BCS", title=f"BCS {float(r.bcs):.1f}",
                                  detail=r.notes, source_table="bcs_records", source_id=r.id))

    for n in (await db.execute(select(AnimalNote).where(AnimalNote.animal_id == animal_id))).scalars().all():
        items.append(TimelineItem(date=n.note_date, event_category="NOTE", title=n.note_type.value.title(),
                                  detail=n.content, source_table="animal_notes", source_id=n.id))

    items.sort(key=lambda i: i.date, reverse=True)
    return items


# ---------- Reproduction analytics ----------
def _bcs_band(score: float) -> str:
    if score < 2.0:
        return "1.0-1.5"
    if score < 3.0:
        return "2.0-2.5"
    if score < 4.0:
        return "3.0-3.5"
    return "4.0+"


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


async def _repro_metrics(db: AsyncSession, start: date, end: date, location_id: Optional[int]) -> dict:
    """Reproduction metrics for a date range (and optionally one location, by the animal's current location).

    koo_count: latest OpeningBalance per (location, species, category) for Koo categories with
    period_start <= the range start, summed over species; falls back to current StockLevel when
    there is no opening balance. Calvings/PD checks are bucketed by their own dates; open/pregnant
    counts are a current snapshot of active animals.
    """
    koo_ids = list((await db.execute(select(Category.id).where(Category.name_sw == "Koo"))).scalars().all())

    koo_count = 0
    if koo_ids:
        ob_query = select(OpeningBalance).where(and_(
            OpeningBalance.category_id.in_(koo_ids), OpeningBalance.period_start <= start))
        if location_id:
            ob_query = ob_query.where(OpeningBalance.location_id == location_id)
        latest: dict = {}
        for ob in (await db.execute(ob_query)).scalars().all():
            key = (ob.location_id, ob.species, ob.category_id)
            if key not in latest or ob.period_start > latest[key].period_start:
                latest[key] = ob
        if latest:
            koo_count = sum(ob.count for ob in latest.values())
        else:
            sl_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                StockLevel.category_id.in_(koo_ids))
            if location_id:
                sl_query = sl_query.where(StockLevel.location_id == location_id)
            koo_count = (await db.execute(sl_query)).scalar() or 0

    cyc_query = select(ReproductiveCycle).join(Animal, Animal.id == ReproductiveCycle.animal_id)
    if location_id:
        cyc_query = cyc_query.where(Animal.location_id == location_id)
    cycles = (await db.execute(cyc_query)).scalars().all()

    def in_range(d: Optional[date]) -> bool:
        return d is not None and start <= d <= end

    calved = [c for c in cycles if in_range(c.actual_calving_date)]
    live = sum(1 for c in calved if c.calving_outcome in (CalvingOutcome.LIVE_CALF, CalvingOutcome.ASSISTED_LIVE))
    pd_done = [c for c in cycles if c.pd_result is not None and in_range(c.pd_check_date)]
    pd_pregnant = sum(1 for c in pd_done if c.pd_result == PDResult.PREGNANT)
    confirmed = [c for c in cycles if c.pd_result == PDResult.PREGNANT
                 and in_range(c.actual_calving_date or c.pd_check_date or c.service_date)]
    aborted = sum(1 for c in confirmed
                  if c.status == ReproductiveCycleStatus.ABORTED or c.calving_outcome == CalvingOutcome.ABORTION)
    intervals = [c.calving_interval_days for c in calved if c.calving_interval_days is not None]

    animal_query = select(Animal.id, Animal.category_id).where(
        and_(Animal.status == AnimalStatus.ACTIVE, Animal.sex == AnimalSex.FEMALE))
    if location_id:
        animal_query = animal_query.where(Animal.location_id == location_id)
    active_females = {row[0]: row[1] for row in (await db.execute(animal_query)).all()}
    pregnant_ids = {
        c.animal_id for c in cycles
        if c.pd_result == PDResult.PREGNANT and c.actual_calving_date is None
        and c.status != ReproductiveCycleStatus.ABORTED and c.calving_outcome != CalvingOutcome.ABORTION
        and c.animal_id in active_females
    }
    open_cows = sum(1 for aid, cat in active_females.items() if cat in koo_ids and aid not in pregnant_ids)

    bcs_query = (
        select(BCSRecord).join(Animal, Animal.id == BCSRecord.animal_id)
        .where(and_(Animal.status == AnimalStatus.ACTIVE, BCSRecord.score_date <= end))
        .order_by(BCSRecord.score_date, BCSRecord.id)
    )
    if location_id:
        bcs_query = bcs_query.where(Animal.location_id == location_id)
    latest_bcs = {r.animal_id: float(r.bcs) for r in (await db.execute(bcs_query)).scalars().all()}
    distribution = {"1.0-1.5": 0, "2.0-2.5": 0, "3.0-3.5": 0, "4.0+": 0}
    for score in latest_bcs.values():
        distribution[_bcs_band(score)] += 1

    return {
        "koo_count": int(koo_count),
        "live_calvings": live,
        "calving_rate": _ratio(live, int(koo_count)),
        "conception_rate": _ratio(pd_pregnant, len(pd_done)),
        "abortion_rate": _ratio(aborted, len(confirmed)),
        "avg_calving_interval_days": round(sum(intervals) / len(intervals), 1) if intervals else None,
        "open_cows": open_cows,
        "pregnant_cows": len(pregnant_ids),
        "bcs_distribution": distribution,
    }


@api_router.get("/analytics/reproduction", response_model=ReproductionAnalyticsResponse)
async def get_reproduction_analytics(
    location_id: Optional[int] = None,
    year: Optional[int] = Query(None, ge=2000, le=2100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    # Explicit dates override year; with neither, the current calendar year is used (unchanged).
    if date_from or date_to:
        if not (date_from and date_to):
            raise HTTPException(status_code=400, detail="date_from and date_to must be provided together")
        if date_to < date_from:
            raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
        start, end = date_from, date_to
        year = date_to.year
    else:
        year = year or date.today().year
        start, end = date(year, 1, 1), date(year, 12, 31)
    overall = await _repro_metrics(db, start, end, location_id)
    loc_query = select(Location).where(Location.is_active == True)  # noqa: E712
    if location_id:
        loc_query = loc_query.where(Location.id == location_id)
    by_location = []
    for loc in (await db.execute(loc_query.order_by(Location.name))).scalars().all():
        by_location.append(LocationReproductionMetrics(
            location_id=loc.id, location_name=loc.name, **(await _repro_metrics(db, start, end, loc.id))))
    return ReproductionAnalyticsResponse(year=year, location_id=location_id, by_location=by_location, **overall)


# ---------- Standalone reproductive events ----------
async def _apply_reproductive_status(db, animal_id, event):
    """Update the animal from a saved event; the caller owns the transaction."""
    animal = await db.get(Animal, animal_id)
    if animal is None:
        return
    if event.event_type == ReproductiveEventType.SERVICE:
        animal.services_without_conception = (animal.services_without_conception or 0) + 1
    elif event.event_type == ReproductiveEventType.PD_TEST:
        animal.last_pd_date = event.event_date
        if event.pd_result == PDResult.PREGNANT:
            animal.reproductive_status = "pregnant"
            animal.months_pregnant = event.months_pregnant
            animal.services_without_conception = 0
        else:
            animal.reproductive_status = "open"
            animal.months_pregnant = None
    elif event.event_type == ReproductiveEventType.CALVING:
        animal.reproductive_status = "open"
        animal.last_calving_date = event.event_date
        animal.months_pregnant = None
        animal.services_without_conception = 0
    elif event.event_type == ReproductiveEventType.ABORTION:
        animal.reproductive_status = "open"
        animal.months_pregnant = None
    await db.flush()


async def _sync_cycle_calving_status(db, cycle):
    # Adapt the existing cycle without inserting a duplicate standalone event.
    event_type = (ReproductiveEventType.ABORTION if cycle.calving_outcome == CalvingOutcome.ABORTION
                  else ReproductiveEventType.CALVING)
    await _apply_reproductive_status(db, cycle.animal_id, SimpleNamespace(
        event_type=event_type, event_date=cycle.actual_calving_date,
    ))


async def _reproductive_animal(db, animal_id):
    animal = (await db.execute(select(Animal).where(Animal.id == animal_id).with_for_update())).scalar_one_or_none()
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    return animal


@api_router.post("/animals/{animal_id}/reproductive-events", response_model=ReproductiveEventResponse)
async def create_reproductive_event(
    animal_id: int,
    data: ReproductiveEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    # Serialize saves for one animal so concurrent services do not lose increments.
    await _reproductive_animal(db, animal_id)
    if data.event_type == ReproductiveEventType.SERVICE and data.bull_animal_id is not None:
        if await db.get(Animal, data.bull_animal_id) is None:
            raise HTTPException(status_code=404, detail="Bull animal not found")
    values = data.model_dump()
    if data.pd_result is not None:
        values["pd_result"] = PDResult.REPEAT if data.pd_result == "recheck" else PDResult(data.pd_result)
    event = ReproductiveEvent(**values, animal_id=animal_id, recorded_by=current_user.id)
    db.add(event)
    await db.flush()
    await _apply_reproductive_status(db, animal_id, event)
    await db.commit()
    await db.refresh(event)
    return ReproductiveEventResponse.model_validate(event)


@api_router.get("/animals/{animal_id}/reproductive-events", response_model=List[ReproductiveEventResponse])
async def list_reproductive_events(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    if await db.get(Animal, animal_id) is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    events = (await db.execute(select(ReproductiveEvent).where(ReproductiveEvent.animal_id == animal_id)
                              .order_by(ReproductiveEvent.event_date.desc(), ReproductiveEvent.id.desc()))).scalars().all()
    return [ReproductiveEventResponse.model_validate(event) for event in events]


@api_router.get("/animals/{animal_id}/reproductive-summary", response_model=ReproductiveSummaryResponse)
async def reproductive_summary(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    animal = await db.get(Animal, animal_id)
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    events = (await db.execute(select(ReproductiveEvent).where(ReproductiveEvent.animal_id == animal_id)
                              .order_by(ReproductiveEvent.event_date.desc(), ReproductiveEvent.id.desc())
                              .limit(5))).scalars().all()
    services = animal.services_without_conception or 0
    return ReproductiveSummaryResponse(
        status=animal.reproductive_status or "unknown", last_calving_date=animal.last_calving_date,
        last_pd_date=animal.last_pd_date, months_pregnant=animal.months_pregnant,
        services_without_conception=services, is_repeat_breeder=services >= REPEAT_BREEDER_THRESHOLD,
        events=[ReproductiveEventResponse.model_validate(event) for event in events],
    )


@api_router.post("/admin/tasks/sync-reproductive-status")
async def sync_reproductive_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    animals = (await db.execute(select(Animal).where(
        Animal.sex == AnimalSex.FEMALE, Animal.reproductive_status == "unknown",
        Animal.birth_date.isnot(None),
    ).with_for_update())).scalars().all()
    today = date.today()
    updated = 0
    for animal in animals:
        born = animal.birth_date
        age_months = (today.year - born.year) * 12 + today.month - born.month - (today.day < born.day)
        species_key = "goats" if animal.species == SpeciesType.GOAT else animal.species.value
        if age_months >= BREEDING_AGE_MONTHS[species_key]:
            animal.reproductive_status = "open"
            updated += 1
    await db.commit()
    return {"updated": updated}


# ---------- Physical tag reconciliation ----------
async def _load_reconciliation_session(db, session_id):
    session = await db.get(ReconciliationSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Reconciliation session not found")
    return session


async def _reconciliation_result(db, session):
    entries = (await db.execute(select(ReconciliationEntry).where(
        ReconciliationEntry.session_id == session.id,
    ).order_by(ReconciliationEntry.id))).scalars().all()
    matched_ids = {e.matched_animal_id for e in entries if e.matched_animal_id is not None}
    animals = (await db.execute(select(Animal).where(
        or_(Animal.id.in_(matched_ids), and_(
            Animal.location_id == session.location_id, Animal.status == AnimalStatus.ACTIVE,
        )),
    ).options(selectinload(Animal.category)).order_by(Animal.id))).scalars().all()
    # The entry schema stores the match, but not its provenance. Infer the
    # displayed match method from the currently active identifiers.
    identifiers = (await db.execute(select(AnimalIdentifier).where(
        AnimalIdentifier.animal_id.in_(matched_ids), AnimalIdentifier.is_active.is_(True),
    ))).scalars().all()
    identifier_keys = {(i.animal_id, i.id_type, i.id_value) for i in identifiers}
    via_identifier = {e.matched_animal_id for e in entries
                      if e.id_type != AnimalIdentifierType.VISUAL_TAG
                      or (e.matched_animal_id, e.id_type, e.raw_value) in identifier_keys}
    matched = [dict(animal_id=a.id, tag_number=a.tag_number, species=a.species,
                    matched_via="identifier" if a.id in via_identifier else "tag_number")
               for a in animals if a.id in matched_ids]
    missing = [dict(animal_id=a.id, tag_number=a.tag_number, species=a.species,
                    category=a.category.name_sw) for a in animals if a.id not in matched_ids]
    unmatched = [dict(raw_value=e.raw_value, id_type=e.id_type)
                 for e in entries if e.matched_animal_id is None]
    denominator = len(matched) + len(missing)
    location = await db.get(Location, session.location_id)
    return ReconciliationResultResponse(
        session_id=session.id, location_name=location.name,
        session_date=session.session_date, input_type=session.input_type,
        total_scanned=len(entries), matched=matched, unmatched_scan=unmatched,
        in_system_not_seen=missing, matched_count=len(matched),
        unmatched_scan_count=len(unmatched), in_system_not_seen_count=len(missing),
        coverage_pct=100.0 * len(matched) / denominator if denominator else 0.0,
    )


async def _process_reconciliation_session(db, session_id):
    session = await _load_reconciliation_session(db, session_id)
    entries = (await db.execute(select(ReconciliationEntry).where(
        ReconciliationEntry.session_id == session_id,
    ).order_by(ReconciliationEntry.id))).scalars().all()
    for entry in entries:
        ids = set((await db.execute(select(AnimalIdentifier.animal_id).where(
            AnimalIdentifier.id_type == entry.id_type,
            AnimalIdentifier.id_value == entry.raw_value,
            AnimalIdentifier.is_active.is_(True),
        ))).scalars().all())
        if not ids and entry.id_type == AnimalIdentifierType.VISUAL_TAG:
            ids = set((await db.execute(select(Animal.id).where(
                Animal.tag_number == entry.raw_value,
            ))).scalars().all())
        if len(ids) > 1:
            raise HTTPException(status_code=409, detail=f"Ambiguous tag: {entry.raw_value}")
        entry.matched_animal_id = next(iter(ids), None)
        entry.match_status = "matched" if ids else "unmatched_scan"
    await db.flush()
    return await _reconciliation_result(db, session)


@api_router.post("/reconciliation/sessions", response_model=ReconciliationResultResponse)
async def create_reconciliation_session(
    data: ReconciliationSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    if await db.get(Location, data.location_id) is None:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        session = ReconciliationSession(
            **data.model_dump(exclude={"entries"}), recorded_by=current_user.id,
        )
        db.add(session)
        await db.flush()
        db.add_all([ReconciliationEntry(session_id=session.id, **entry.model_dump())
                    for entry in data.entries])
        await db.flush()
        result = await _process_reconciliation_session(db, session.id)
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


@api_router.get("/reconciliation/sessions", response_model=List[ReconciliationSessionSummary])
async def list_reconciliation_sessions(
    location_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    query = select(ReconciliationSession)
    if location_id is not None:
        query = query.where(ReconciliationSession.location_id == location_id)
    if date_from is not None:
        query = query.where(ReconciliationSession.session_date >= date_from)
    if date_to is not None:
        query = query.where(ReconciliationSession.session_date <= date_to)
    sessions = (await db.execute(query.order_by(
        ReconciliationSession.session_date.desc(), ReconciliationSession.id.desc(),
    ))).scalars().all()
    summaries = []
    for session in sessions:
        result = await _reconciliation_result(db, session)
        summaries.append(ReconciliationSessionSummary(
            id=session.id, created_at=session.created_at,
            **result.model_dump(exclude={"session_id", "matched", "unmatched_scan", "in_system_not_seen"}),
        ))
    return summaries


@api_router.get("/reconciliation/sessions/{session_id}", response_model=ReconciliationResultResponse)
async def get_reconciliation_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return await _reconciliation_result(db, await _load_reconciliation_session(db, session_id))


@api_router.post("/reconciliation/sessions/{session_id}/reprocess", response_model=ReconciliationResultResponse)
async def reprocess_reconciliation_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        result = await _process_reconciliation_session(db, session_id)
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


@api_router.post("/admin/import/pd-tests", response_model=PDTestImportResult)
async def import_pd_tests(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    result = PDTestImportResult(matched=0, events_created=0, not_found=[], skipped=[], total_rows=0)
    aliases = {alias: value for value, names in (
        (PDResult.PREGNANT, ("pregnant", "yes", "p")),
        (PDResult.OPEN, ("open", "no", "negative", "n")),
        (PDResult.REPEAT, ("recheck", "r", "check")),
    ) for alias in names}
    matched_ids = set()
    stream = io.TextIOWrapper(file.file, encoding="utf-8-sig", newline="")
    try:
        reader = csv.DictReader(stream, strict=True)
        required = {"tag_number", "test_date", "result", "months_pregnant", "vet", "notes"}
        if (not reader.fieldnames or not required.issubset(reader.fieldnames)
                or len(reader.fieldnames) != len(set(reader.fieldnames))):
            raise HTTPException(status_code=400, detail="CSV must have unique headers including: " + ", ".join(sorted(required)))
        for row in reader:
            result.total_rows += 1
            line = reader.line_num
            if None in row or any(value is None for value in row.values()):
                raise HTTPException(status_code=400, detail=f"CSV row {line}: incorrect column count")
            row = {key: value.strip() for key, value in row.items()}
            missing = [key for key in ("tag_number", "test_date") if not row[key]]
            if missing:
                result.skipped.append(f"Row {line}: missing {', '.join(missing)}")
                continue
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["test_date"]):
                    raise ValueError()
                test_date = date.fromisoformat(row["test_date"])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"CSV row {line}: test_date must be a valid YYYY-MM-DD date")
            pd_result = aliases.get(row["result"].lower())
            if pd_result is None:
                raise HTTPException(status_code=400, detail=f"CSV row {line}: invalid PD result")
            months = None
            if pd_result == PDResult.PREGNANT and row["months_pregnant"]:
                if not re.fullmatch(r"[0-9]+", row["months_pregnant"]) or len(row["months_pregnant"]) > 10:
                    raise HTTPException(status_code=400, detail=f"CSV row {line}: months_pregnant must be a nonnegative integer")
                months = int(row["months_pregnant"])
                if months > 2147483647:
                    raise HTTPException(status_code=400, detail=f"CSV row {line}: months_pregnant exceeds the integer limit")
            if len(row["tag_number"]) > 100 or len(row["vet"]) > 100:
                raise HTTPException(status_code=400, detail=f"CSV row {line}: tag_number and vet must not exceed 100 characters")
            animals = (await db.execute(select(Animal).where(
                Animal.tag_number == row["tag_number"], Animal.status == AnimalStatus.ACTIVE,
            ).limit(2).with_for_update())).scalars().all()
            if len(animals) > 1:
                raise HTTPException(status_code=409, detail=f"CSV row {line}: ambiguous active tag {row['tag_number']}")
            if not animals:
                result.not_found.append(row["tag_number"])
                continue
            animal = animals[0]
            event = ReproductiveEvent(
                animal_id=animal.id, event_type=ReproductiveEventType.PD_TEST,
                event_date=test_date, pd_result=pd_result, months_pregnant=months,
                vet=row["vet"] or None, notes=row["notes"] or None, recorded_by=current_user.id,
            )
            db.add(event)
            await db.flush()
            await _apply_reproductive_status(db, animal.id, event)
            matched_ids.add(animal.id)
            result.events_created += 1
        result.matched = len(matched_ids)
        await db.commit()
        return result
    except (UnicodeError, csv.Error) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid UTF-8 CSV file") from exc
    except Exception:
        await db.rollback()
        raise
    finally:
        stream.detach()


# ---------- Customers and sale details ----------
async def _sales_customer(db, customer_id):
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


async def _sales_line_items(db, date_from=None, date_to=None, location_id=None,
                            species=None, customer_id=None):
    query = (select(Event, DailyLog.log_date, Location.name, Category.name_sw,
                    SaleDetail, Customer.name)
             .join(DailyLog, Event.daily_log_id == DailyLog.id)
             .join(Location, DailyLog.location_id == Location.id)
             .outerjoin(Category, Event.category_id == Category.id)
             .join(SaleDetail, SaleDetail.event_id == Event.id)
             .outerjoin(Customer, SaleDetail.customer_id == Customer.id)
             .where(Event.event_type == EventType.SOLD))
    if date_from is not None:
        query = query.where(DailyLog.log_date >= date_from)
    if date_to is not None:
        query = query.where(DailyLog.log_date <= date_to)
    if location_id is not None:
        query = query.where(DailyLog.location_id == location_id)
    if species is not None:
        query = query.where(Event.species == species)
    if customer_id is not None:
        query = query.where(SaleDetail.customer_id == customer_id)
    rows = (await db.execute(query.order_by(DailyLog.log_date.desc(), Event.id.desc()))).all()
    return [SalesLineItem(date=day, farm=farm, species=event.species, category=category,
                          qty=event.count, price_per_head=detail.price_per_head,
                          total_price=detail.total_price, customer_name=customer_name,
                          event_id=event.id)
            for event, day, farm, category, detail, customer_name in rows]


@api_router.get("/customers", response_model=List[CustomerResponse])
async def list_customers(
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    query = select(Customer)
    if is_active is not None:
        query = query.where(Customer.is_active == is_active)
    if search:
        query = query.where(func.lower(Customer.name).contains(search.strip().lower(), autoescape=True))
    return (await db.execute(query.order_by(Customer.name, Customer.id))).scalars().all()


@api_router.post("/customers", response_model=CustomerResponse)
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    customer = Customer(**data.model_dump(), created_by=current_user.id)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@api_router.get("/customers/{customer_id}", response_model=CustomerDetailResponse)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    customer = await _sales_customer(db, customer_id)
    return CustomerDetailResponse(
        **CustomerResponse.model_validate(customer).model_dump(),
        purchases=await _sales_line_items(db, customer_id=customer_id),
    )


@api_router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    customer = await _sales_customer(db, customer_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, key, value)
    await db.commit()
    await db.refresh(customer)
    return customer


@api_router.delete("/customers/{customer_id}")
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    customer = await _sales_customer(db, customer_id)
    customer.is_active = False
    await db.commit()
    return {"message": "Customer deactivated"}


@api_router.get("/customers/{customer_id}/purchases", response_model=List[SalesLineItem])
async def customer_purchases(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _sales_customer(db, customer_id)
    return await _sales_line_items(db, customer_id=customer_id)


async def _sale_event(db, event_id, lock=False):
    query = select(Event).where(Event.id == event_id)
    if lock:
        query = query.with_for_update()
    event = (await db.execute(query)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.event_type != EventType.SOLD:
        raise HTTPException(status_code=400, detail="Sale details require a SOLD event")
    return event


async def _sale_detail_response(db, detail):
    customer = await db.get(Customer, detail.customer_id) if detail.customer_id is not None else None
    return SaleDetailResponse(
        id=detail.id, event_id=detail.event_id, customer_id=detail.customer_id,
        customer_name=customer.name if customer else None, price_per_head=detail.price_per_head,
        total_price=detail.total_price, notes=detail.notes, created_at=detail.created_at,
    )


@api_router.post("/events/{event_id}/sale-detail", response_model=SaleDetailResponse)
async def save_sale_detail(
    event_id: int,
    data: SaleDetailCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    try:
        # Lock the existing event to serialize concurrent upserts for this sale.
        event = await _sale_event(db, event_id, lock=True)
        values = data.model_dump(exclude_unset=True)
        if data.customer_id is not None:
            await _sales_customer(db, data.customer_id)
        detail = (await db.execute(select(SaleDetail).where(SaleDetail.event_id == event_id))).scalar_one_or_none()
        new = detail is None
        if new:
            detail = SaleDetail(event_id=event_id, recorded_by=current_user.id)
        for key, value in values.items():
            setattr(detail, key, value)
        # A supplied non-null total wins. Notes/customer-only updates preserve the
        # saved total; a new price or an explicit null total requests calculation.
        if data.total_price is None and (new or "price_per_head" in values or "total_price" in values):
            detail.total_price = (detail.price_per_head * event.count
                                  if detail.price_per_head is not None else None)
        if detail.total_price is not None and not Decimal("0") <= detail.total_price <= Decimal("9999999999.99"):
            raise HTTPException(status_code=400, detail="Computed total is outside the supported price range")
        db.add(detail)
        await db.flush()
        await db.refresh(detail)
        response = await _sale_detail_response(db, detail)
        await db.commit()
        return response
    except Exception:
        await db.rollback()
        raise


@api_router.get("/events/{event_id}/sale-detail", response_model=SaleDetailResponse)
async def get_sale_detail(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _sale_event(db, event_id)
    detail = (await db.execute(select(SaleDetail).where(SaleDetail.event_id == event_id))).scalar_one_or_none()
    if detail is None:
        raise HTTPException(status_code=404, detail="Sale detail not found")
    return await _sale_detail_response(db, detail)


@api_router.get("/reports/sales", response_model=SalesReportResponse)
async def sales_report(
    date_from: date,
    date_to: date,
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    customer_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    items = await _sales_line_items(db, date_from, date_to, location_id, species, customer_id)
    revenue = sum((item.total_price or Decimal("0") for item in items), Decimal("0.00"))
    head = sum(item.qty for item in items)
    buckets = {}
    for item in items:
        month = item.date.strftime("%Y-%m")
        bucket = buckets.setdefault(month, {"month": month, "revenue": Decimal("0.00"), "head_count": 0})
        bucket["revenue"] += item.total_price or Decimal("0")
        bucket["head_count"] += item.qty
    return SalesReportResponse(
        summary={"total_revenue": revenue, "total_head": head,
                 "avg_price_per_head": (revenue / head).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if head else Decimal("0.00"),
                 "period": {"from": date_from, "to": date_to}},
        by_period=[buckets[month] for month in sorted(buckets)], line_items=items,
    )


# ---------- Structured mortality ----------
async def _seed_death_causes(connection):
    for order, name in enumerate(("Disease", "Predation", "Accident", "Starvation/Drought",
                                  "Dystocia", "Unknown", "Other")):
        await connection.execute(text(
            "INSERT INTO death_causes (name, is_active, sort_order) VALUES (:name, true, :sort_order) "
            "ON CONFLICT (name) DO NOTHING"
        ), {"name": name, "sort_order": order})


async def _validate_death_cause(db, event_type, cause_id, existing_id=None):
    if cause_id is None:
        return
    if event_type != EventType.DEATH:
        raise HTTPException(status_code=400, detail="Structured death causes apply only to DEATH events")
    cause = await db.get(DeathCause, cause_id)
    if cause is None:
        raise HTTPException(status_code=404, detail="Death cause not found")
    if not cause.is_active and cause_id != existing_id:
        raise HTTPException(status_code=400, detail="Death cause is inactive")


async def _get_death_cause(db, cause_id):
    cause = await db.get(DeathCause, cause_id)
    if cause is None:
        raise HTTPException(status_code=404, detail="Death cause not found")
    return cause


async def _save_death_cause(db, cause):
    try:
        db.add(cause)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A death cause with this name already exists")
    await db.refresh(cause)
    return cause


@api_router.get("/death-causes", response_model=List[DeathCauseResponse])
async def list_death_causes(
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return (await db.execute(select(DeathCause).where(DeathCause.is_active == is_active)
                            .order_by(DeathCause.sort_order, DeathCause.name))).scalars().all()


@api_router.post("/death-causes", response_model=DeathCauseResponse)
async def create_death_cause(
    data: DeathCauseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    return await _save_death_cause(db, DeathCause(**data.model_dump()))


@api_router.put("/death-causes/{cause_id}", response_model=DeathCauseResponse)
async def update_death_cause(
    cause_id: int, data: DeathCauseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    cause = await _get_death_cause(db, cause_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(cause, key, value)
    return await _save_death_cause(db, cause)


@api_router.delete("/death-causes/{cause_id}")
async def deactivate_death_cause(
    cause_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    cause = await _get_death_cause(db, cause_id)
    cause.is_active = False
    await db.commit()
    return {"message": "Death cause deactivated"}


@api_router.get("/settings/mortality-thresholds", response_model=List[MortalityThresholdResponse])
async def get_mortality_thresholds(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return (await db.execute(select(MortalityThreshold).order_by(MortalityThreshold.species))).scalars().all()


@api_router.put("/settings/mortality-thresholds", response_model=List[MortalityThresholdResponse])
async def update_mortality_thresholds(
    data: List[MortalityThresholdUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if len({item.species for item in data}) != len(data):
        raise HTTPException(status_code=400, detail="Each species may appear only once")
    # Dialect-specific ON CONFLICT keeps first-time concurrent upserts atomic.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as threshold_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as threshold_insert
    try:
        for item in sorted(data, key=lambda item: item.species.value):
            statement = threshold_insert(MortalityThreshold).values(
                species=item.species, threshold=item.threshold, updated_by=current_user.id,
            )
            await db.execute(statement.on_conflict_do_update(
                index_elements=[MortalityThreshold.species],
                set_={"threshold": item.threshold, "updated_by": current_user.id, "updated_at": func.now()},
            ))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return (await db.execute(select(MortalityThreshold).order_by(MortalityThreshold.species)
                            .execution_options(populate_existing=True))).scalars().all()


@api_router.get("/reports/mortality", response_model=MortalityReportResponse)
async def mortality_report(
    date_from: date, date_to: date,
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    opening = await build_stock_snapshot(db, date_from, location_id)
    closing = await build_stock_snapshot(db, date_to, location_id)
    stocks = {}
    for snapshot, boundary in ((opening, 0), (closing, 1)):
        for (loc, sp, _category), value in snapshot.items():
            if location_id is not None and loc != location_id:
                continue
            if species is not None and species != sp:
                continue
            stocks.setdefault((loc, sp), [0, 0])[boundary] += value["count"]
    query = (select(Event, DailyLog.log_date, DailyLog.location_id, DeathCause.name)
             .join(DailyLog, Event.daily_log_id == DailyLog.id)
             .outerjoin(DeathCause, Event.cause_of_death_id == DeathCause.id)
             .where(Event.event_type == EventType.DEATH,
                    DailyLog.log_date >= date_from, DailyLog.log_date <= date_to))
    if location_id is not None:
        query = query.where(DailyLog.location_id == location_id)
    if species is not None:
        query = query.where(Event.species == species)
    events = (await db.execute(query)).all()
    deaths, causes = {}, {}
    total = 0
    # Twelve calendar months ending in date_to's month, clipped to the range.
    end_month = (date_to.year - 1) * 12 + date_to.month - 1
    start_month = max((date_from.year - 1) * 12 + date_from.month - 1, end_month - 11)
    months = {}
    for index in range(start_month, end_month + 1):
        key = f"{index // 12 + 1:04d}-{index % 12 + 1:02d}"
        months[key] = {"month": key, "deaths": 0, "by_species": {sp.value: 0 for sp in SpeciesType}}
    for event, day, loc, cause in events:
        key = (loc, event.species)
        deaths[key] = deaths.get(key, 0) + event.count
        stocks.setdefault(key, [0, 0])
        total += event.count
        if cause is not None:
            causes[cause] = causes.get(cause, 0) + event.count
        month = day.strftime("%Y-%m")
        if month in months:
            months[month]["deaths"] += event.count
            months[month]["by_species"][event.species.value] += event.count
    thresholds = {row.species: row.threshold for row in
                  (await db.execute(select(MortalityThreshold))).scalars().all()}
    locations = {row.id: row.name for row in (await db.execute(select(Location))).scalars().all()}

    def metrics(sp, count, bounds):
        average = Decimal(bounds[0] + bounds[1]) / 2
        rate = Decimal(count) / average * 100 if average > 0 else None
        threshold = thresholds.get(sp)
        return dict(species=sp, deaths=count, avg_stock=float(average),
                    mortality_rate_pct=round(float(rate), 2) if rate is not None else None,
                    threshold_pct=float(threshold) if threshold is not None else None,
                    is_alert=rate is not None and threshold is not None and rate > threshold)

    farms, aggregate = [], {}
    for (loc, sp), bounds in stocks.items():
        count = deaths.get((loc, sp), 0)
        if not count and not any(bounds):
            continue
        farms.append(dict(farm=locations.get(loc, "Unknown"), location_id=loc, **metrics(sp, count, bounds)))
        combined = aggregate.setdefault(sp, [0, 0, 0])
        combined[0] += bounds[0]
        combined[1] += bounds[1]
        combined[2] += count
    farms.sort(key=lambda row: (not row["is_alert"], -(row["mortality_rate_pct"] or 0), row["farm"], row["species"].value))
    return MortalityReportResponse(
        summary={"total_deaths": total, "period": {"from": date_from, "to": date_to}},
        by_species=[metrics(sp, values[2], values[:2]) for sp, values in sorted(aggregate.items(), key=lambda pair: pair[0].value)],
        by_farm=farms,
        by_cause=[dict(cause_name=name, count=count, pct_of_total=round(count / total * 100, 2) if total else 0)
                  for name, count in sorted(causes.items(), key=lambda pair: (pair[0].lower() == "unknown", -pair[1], pair[0]))],
        by_month=list(months.values()), flagged=[row for row in farms if row["is_alert"]],
    )


# Include router after all route declarations.
app.include_router(api_router)

@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
