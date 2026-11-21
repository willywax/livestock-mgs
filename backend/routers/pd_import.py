"""Bulk pregnancy-diagnosis import."""
import csv
import io
import re
from datetime import date

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from models import Animal, AnimalStatus, PDResult, ReproductiveEvent, ReproductiveEventType, User, UserRole
from schemas import PDTestImportResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.reproduction import _apply_reproductive_status

router = APIRouter()

@router.post("/admin/import/pd-tests", response_model=PDTestImportResult)
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
