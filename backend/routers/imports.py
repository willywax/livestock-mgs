"""CSV templates and bulk imports (locations, opening balances)."""
import csv
import io
from datetime import datetime

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from models import Category, Location, OpeningBalance, SpeciesType, User, UserRole
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.stock import update_stock_level

router = APIRouter()

# ==================== IMPORT/EXPORT ROUTES ====================
@router.get("/templates/locations")
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

@router.get("/templates/opening-balances")
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

@router.post("/import/locations")
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

@router.post("/import/opening-balances")
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
