"""Animal identifiers (EID, brand, ...) and the identifier import."""
import csv
import io
from datetime import date, datetime
from typing import List

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from models import Animal, AnimalIdentifier, AnimalIdentifierType, Location, SpeciesType, User, UserRole
from schemas import AnimalIdentifierCreate, AnimalIdentifierImportResult, AnimalIdentifierResponse, AnimalIdentifierUpdate
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import _ANY_ROLE, _require_animal

router = APIRouter()

@router.post("/admin/import/animal-identifiers", response_model=AnimalIdentifierImportResult)
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


@router.get("/animals/{animal_id}/identifiers", response_model=List[AnimalIdentifierResponse])
async def list_animal_identifiers(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _require_animal(db, animal_id)
    result = await db.execute(select(AnimalIdentifier).where(AnimalIdentifier.animal_id == animal_id)
                             .order_by(AnimalIdentifier.id_type, AnimalIdentifier.created_at, AnimalIdentifier.id))
    return [AnimalIdentifierResponse.model_validate(item) for item in result.scalars().all()]


@router.post("/animals/{animal_id}/identifiers", response_model=AnimalIdentifierResponse)
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


@router.put("/animals/{animal_id}/identifiers/{identifier_id}", response_model=AnimalIdentifierResponse)
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


@router.delete("/animals/{animal_id}/identifiers/{identifier_id}")
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
