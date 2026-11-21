"""Individual animal register: CRUD, import, lookup, transfer, tag replacement."""
import csv
import io
from datetime import datetime, timezone
from typing import List, Optional, Union

from auth import get_current_user, require_roles
from database import get_db
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from models import Animal, AnimalAcquisitionType, AnimalIdentifier, AnimalIdentifierType, AnimalLocationHistory, AnimalSex, AnimalStatus, Category, DailyLog, Event, EventType, Location, SpeciesType, StockLevel, User, UserRole
from schemas import AnimalCreate, AnimalIdentifierResponse, AnimalLocationHistoryResponse, AnimalLookupResponse, AnimalPage, AnimalResponse, AnimalTransfer, AnimalUpdate, BulkImportResult, EventCreate, ReconciliationRow, ReplaceTagRequest, ReplaceTagResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.common import REPEAT_BREEDER_THRESHOLD
from services.stock import apply_event_to_stock

router = APIRouter()

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
        last_calving_date=animal.last_calving_date,
    )

@router.get("/templates/animals")
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

@router.get("/animals", response_model=Union[List[AnimalResponse], AnimalPage])
async def list_animals(
    species: Optional[SpeciesType] = None,
    location_id: Optional[int] = None,
    category_id: Optional[int] = None,
    status: Optional[AnimalStatus] = None,
    search: Optional[str] = None,
    is_temp_tag: Optional[bool] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=200),
    export: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bare list by default (existing clients) and with export=true; `{items,total,page,page_size,pages}`
    when page/page_size is given (ignored if export=true)."""
    filters = []
    if species:
        filters.append(Animal.species == species)
    if location_id:
        filters.append(Animal.location_id == location_id)
    if category_id:
        filters.append(Animal.category_id == category_id)
    if status:
        filters.append(Animal.status == status)
    if is_temp_tag is not None:
        filters.append(Animal.is_temp_tag == is_temp_tag)
    if search and search.strip():
        term = search.strip().lower()
        filters.append(or_(
            func.lower(Animal.tag_number).contains(term, autoescape=True),
            func.lower(Animal.name).contains(term, autoescape=True),
            func.lower(Animal.registry_tag_id).contains(term, autoescape=True),
            select(AnimalIdentifier.id).where(
                AnimalIdentifier.animal_id == Animal.id,
                AnimalIdentifier.is_active == True,
                func.lower(AnimalIdentifier.id_value).contains(term, autoescape=True),
            ).exists(),
        ))

    # The related rows are tiny; load only the columns _animal_response reads. Animal columns stay whole
    # because the list response (and Animals.jsx) uses notes and every other field.
    query = select(Animal).options(
        selectinload(Animal.category).load_only(Category.id, Category.name_sw, Category.name_en),
        selectinload(Animal.location).load_only(Location.id, Location.name),
        selectinload(Animal.creator).load_only(User.id, User.name),
    ).where(*filters).order_by(Animal.species, Animal.tag_number, Animal.id)

    paged = (page is not None or page_size is not None) and not export
    if paged:
        page = page or 1
        page_size = page_size or 50
        query = query.offset((page - 1) * page_size).limit(page_size)
    animals = (await db.execute(query)).scalars().all()
    items = [_animal_response(a) for a in animals]
    if items:
        tags_by_animal = {item.id: [] for item in items}
        identifiers = (await db.execute(select(
            AnimalIdentifier.animal_id, AnimalIdentifier.id_value,
        ).where(
            AnimalIdentifier.animal_id.in_(tags_by_animal),
            AnimalIdentifier.is_active == True,
        ).order_by(AnimalIdentifier.id))).all()
        for animal_id, value in identifiers:
            tags_by_animal[animal_id].append(value)
        for item in items:
            item.search_tags = tags_by_animal[item.id]
    if not paged:
        return items
    total = (await db.execute(select(func.count()).select_from(Animal).where(*filters))).scalar_one()
    return AnimalPage(items=items, total=total, page=page, page_size=page_size, pages=-(-total // page_size))

@router.post("/animals", response_model=AnimalResponse)
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

@router.post("/animals/bulk-import", response_model=BulkImportResult)
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

@router.get("/animals/register-reconciliation", response_model=List[ReconciliationRow])
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

@router.get("/animals/lookup-by-id", response_model=AnimalLookupResponse)
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


@router.get("/animals/repeat-breeders")
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



@router.get("/animals/{animal_id}", response_model=AnimalResponse)
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

@router.get("/animals/{animal_id}/location-history", response_model=List[AnimalLocationHistoryResponse])
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

@router.post("/animals/{animal_id}/replace-tag", response_model=ReplaceTagResponse)
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

@router.put("/animals/{animal_id}", response_model=AnimalResponse)
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

@router.post("/animals/{animal_id}/transfer", response_model=AnimalResponse)
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
