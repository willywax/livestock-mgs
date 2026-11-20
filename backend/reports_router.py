"""Read-only reproduction reports: /api/reports/{calving,reproductive-status,abortions}.

Kept separate from server.py's api_router. The paths here must never collide with the existing
/api/reports/* routes (daily, range, analytics, detailed, sales, mortality), which are left alone.
Queries use SQLAlchemy Core so they run on PostgreSQL and on the SQLite test database; the
"latest cycle per animal" lookup is a row_number() window (portable) instead of LATERAL.

Enum output: calving_outcome, cycle_status, id_type and by_status keys are the enum NAMES
(LIVE_CALF, OPEN, EID ...) as in the report spec; species, sex, calf_status and abortion_stage
use the API values (cattle, female, active, early ...) like the rest of the API.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from auth import require_roles
from database import get_db
from models import (
    Animal, AnimalIdentifier, AnimalSex, CalvingOutcome, Location, ReproductiveCycle,
    ReproductiveCycleStatus, SpeciesType, User, UserRole,
)

reports_router = APIRouter(prefix="/api/reports", tags=["reports"])

_ANY_ROLE = (UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)
_CALVED_OUTCOMES = (
    CalvingOutcome.LIVE_CALF, CalvingOutcome.STILLBIRTH,
    CalvingOutcome.ASSISTED_LIVE, CalvingOutcome.ASSISTED_DEAD,
)


class TagOut(BaseModel):
    id_type: str
    id_value: str


# ---------- shared helpers ----------
async def _tags_by_animal(db: AsyncSession, animal_ids) -> Dict[int, List[TagOut]]:
    """Active identifiers for all given animals in ONE query, grouped by animal_id."""
    ids = sorted({i for i in animal_ids if i is not None})
    if not ids:
        return {}
    result = await db.execute(
        select(AnimalIdentifier.animal_id, AnimalIdentifier.id_type, AnimalIdentifier.id_value)
        .where(AnimalIdentifier.animal_id.in_(ids), AnimalIdentifier.is_active.is_(True))
        .order_by(AnimalIdentifier.animal_id, AnimalIdentifier.id)
    )
    grouped: Dict[int, List[TagOut]] = {}
    for animal_id, id_type, id_value in result.all():
        grouped.setdefault(animal_id, []).append(TagOut(id_type=id_type.name, id_value=id_value))
    return grouped


def _check_dates(date_from: Optional[date], date_to: Optional[date]) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")


def _enum_name(member) -> Optional[str]:
    return member.name if member is not None else None


def _enum_value(member) -> Optional[str]:
    return member.value if member is not None else None


# ---------- calving ----------
class CalvingSummary(BaseModel):
    total: int
    live: int
    stillbirths: int
    assisted: int


class CalvingRow(BaseModel):
    dam_tag: str
    dam_tags: List[TagOut]
    location_name: Optional[str] = None
    species: str
    calved_date: date
    calving_outcome: str
    calving_interval_days: Optional[int] = None
    calf_tag: Optional[str] = None
    calf_tags: List[TagOut]
    calf_sex: Optional[str] = None
    calf_status: Optional[str] = None


class CalvingReport(BaseModel):
    summary: CalvingSummary
    rows: List[CalvingRow]


@reports_router.get("/calving", response_model=CalvingReport)
async def calving_report(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    _check_dates(date_from, date_to)
    dam, calf = aliased(Animal), aliased(Animal)
    rc = ReproductiveCycle
    query = (
        select(
            rc.actual_calving_date, rc.calving_outcome, rc.calving_interval_days, rc.calf_sex,
            dam.id.label("dam_id"), dam.tag_number.label("dam_tag"), dam.species,
            Location.name.label("location_name"),
            calf.id.label("calf_id"), calf.tag_number.label("calf_tag"), calf.status.label("calf_status"),
        )
        .select_from(rc)
        .join(dam, dam.id == rc.animal_id)
        .outerjoin(calf, calf.id == rc.calf_animal_id)
        .outerjoin(Location, Location.id == dam.location_id)
        .where(rc.actual_calving_date.isnot(None), rc.calving_outcome.in_(_CALVED_OUTCOMES))
        .order_by(rc.actual_calving_date.desc(), rc.id.desc())
    )
    if location_id is not None:
        query = query.where(dam.location_id == location_id)
    if species is not None:
        query = query.where(dam.species == species)
    if date_from:
        query = query.where(rc.actual_calving_date >= date_from)
    if date_to:
        query = query.where(rc.actual_calving_date <= date_to)
    records = (await db.execute(query)).all()

    tags = await _tags_by_animal(db, [r.dam_id for r in records] + [r.calf_id for r in records])
    outcomes = [r.calving_outcome for r in records]
    summary = CalvingSummary(
        total=len(records),
        live=sum(o in (CalvingOutcome.LIVE_CALF, CalvingOutcome.ASSISTED_LIVE) for o in outcomes),
        stillbirths=sum(o == CalvingOutcome.STILLBIRTH for o in outcomes),
        assisted=sum(o in (CalvingOutcome.ASSISTED_LIVE, CalvingOutcome.ASSISTED_DEAD) for o in outcomes),
    )
    rows = [
        CalvingRow(
            dam_tag=r.dam_tag, dam_tags=tags.get(r.dam_id, []),
            location_name=r.location_name, species=r.species.value,
            calved_date=r.actual_calving_date, calving_outcome=r.calving_outcome.name,
            calving_interval_days=r.calving_interval_days,
            calf_tag=r.calf_tag, calf_tags=tags.get(r.calf_id, []),
            calf_sex=_enum_value(r.calf_sex), calf_status=_enum_value(r.calf_status),
        )
        for r in records
    ]
    return CalvingReport(summary=summary, rows=rows)


# ---------- reproductive status ----------
class ReproStatusSummary(BaseModel):
    total: int
    by_status: Dict[str, int]


class ReproStatusRow(BaseModel):
    tag_number: str
    tags: List[TagOut]
    location_name: Optional[str] = None
    species: str
    cycle_status: Optional[str] = None
    last_calving_date: Optional[date] = None
    calving_interval_days: Optional[int] = None
    lifetime_calvings: Optional[int] = None
    months_pregnant: Optional[int] = None
    last_pd_date: Optional[date] = None
    expected_calving_date: Optional[date] = None


class ReproStatusReport(BaseModel):
    summary: ReproStatusSummary
    rows: List[ReproStatusRow]


def _parse_status_list(raw: Optional[str]) -> List[ReproductiveCycleStatus]:
    if not raw or not raw.strip():
        return []
    parsed = []
    for part in raw.split(","):
        part = part.strip().upper()
        if not part:
            continue
        try:
            parsed.append(ReproductiveCycleStatus[part])
        except KeyError:
            allowed = ", ".join(s.name for s in ReproductiveCycleStatus)
            raise HTTPException(status_code=400, detail=f"Invalid status '{part}'. Allowed: {allowed}")
    return parsed


@reports_router.get("/reproductive-status", response_model=ReproStatusReport)
async def reproductive_status_report(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    status: Optional[str] = Query(None, description="Comma-separated cycle statuses, e.g. OPEN,PREGNANT"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    statuses = _parse_status_list(status)
    rc = ReproductiveCycle
    # Latest cycle per animal (created_at DESC, id as tiebreak); portable replacement for LATERAL.
    latest = (
        select(
            rc.animal_id.label("animal_id"), rc.calving_interval_days.label("calving_interval_days"),
            rc.status.label("status"), rc.expected_calving_date.label("expected_calving_date"),
            func.row_number().over(
                partition_by=rc.animal_id, order_by=(rc.created_at.desc(), rc.id.desc())
            ).label("rn"),
        ).subquery()
    )
    query = (
        select(
            Animal.id, Animal.tag_number, Animal.species, Animal.last_calving_date, Animal.last_pd_date,
            Animal.months_pregnant, Animal.lifetime_calvings, Location.name.label("location_name"),
            latest.c.calving_interval_days, latest.c.status.label("cycle_status"),
            latest.c.expected_calving_date,
        )
        .select_from(Animal)
        .outerjoin(latest, and_(latest.c.animal_id == Animal.id, latest.c.rn == 1))
        .outerjoin(Location, Location.id == Animal.location_id)
        .where(Animal.sex == AnimalSex.FEMALE)
        .order_by(Animal.tag_number)
    )
    if location_id is not None:
        query = query.where(Animal.location_id == location_id)
    if species is not None:
        query = query.where(Animal.species == species)
    if statuses:
        query = query.where(latest.c.status.in_(statuses))
    records = (await db.execute(query)).all()

    tags = await _tags_by_animal(db, [r.id for r in records])
    by_status = {s.name: 0 for s in ReproductiveCycleStatus}
    by_status["unknown"] = 0
    for r in records:
        by_status[r.cycle_status.name if r.cycle_status is not None else "unknown"] += 1
    rows = [
        ReproStatusRow(
            tag_number=r.tag_number, tags=tags.get(r.id, []), location_name=r.location_name,
            species=r.species.value, cycle_status=_enum_name(r.cycle_status),
            last_calving_date=r.last_calving_date, calving_interval_days=r.calving_interval_days,
            lifetime_calvings=r.lifetime_calvings, months_pregnant=r.months_pregnant,
            last_pd_date=r.last_pd_date, expected_calving_date=r.expected_calving_date,
        )
        for r in records
    ]
    return ReproStatusReport(summary=ReproStatusSummary(total=len(records), by_status=by_status), rows=rows)


# ---------- abortions ----------
class AbortionSummary(BaseModel):
    total: int
    by_stage: Dict[str, int]


class AbortionRow(BaseModel):
    tag_number: str
    tags: List[TagOut]
    location_name: Optional[str] = None
    species: str
    abortion_date: Optional[datetime] = None
    abortion_stage: Optional[str] = None
    cycle_number: int
    notes: Optional[str] = None


class AbortionReport(BaseModel):
    summary: AbortionSummary
    rows: List[AbortionRow]


@reports_router.get("/abortions", response_model=AbortionReport)
async def abortions_report(
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    _check_dates(date_from, date_to)
    rc = ReproductiveCycle
    query = (
        select(
            rc.created_at.label("abortion_date"), rc.abortion_stage, rc.cycle_number, rc.notes,
            Animal.id, Animal.tag_number, Animal.species, Location.name.label("location_name"),
        )
        .select_from(rc)
        .join(Animal, Animal.id == rc.animal_id)
        .outerjoin(Location, Location.id == Animal.location_id)
        .where(rc.status == ReproductiveCycleStatus.ABORTED)
        .order_by(rc.created_at.desc(), rc.id.desc())
    )
    if location_id is not None:
        query = query.where(Animal.location_id == location_id)
    if species is not None:
        query = query.where(Animal.species == species)
    if date_from:
        query = query.where(func.date(rc.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(rc.created_at) <= date_to)
    records = (await db.execute(query)).all()

    tags = await _tags_by_animal(db, [r.id for r in records])
    by_stage: Dict[str, int] = {}
    for r in records:
        key = _enum_value(r.abortion_stage) or "unknown"
        by_stage[key] = by_stage.get(key, 0) + 1
    rows = [
        AbortionRow(
            tag_number=r.tag_number, tags=tags.get(r.id, []), location_name=r.location_name,
            species=r.species.value, abortion_date=r.abortion_date,
            abortion_stage=_enum_value(r.abortion_stage), cycle_number=r.cycle_number, notes=r.notes,
        )
        for r in records
    ]
    return AbortionReport(summary=AbortionSummary(total=len(records), by_stage=by_stage), rows=rows)
