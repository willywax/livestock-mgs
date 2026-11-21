"""Reproductive status board."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends
from models import Animal, AnimalSex, AnimalStatus, ReproductiveEvent, ReproductiveEventType, SpeciesType, User, UserRole
from schemas import ReproductiveStatusBoardResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.common import BREEDING_AGE_MONTHS, REPEAT_BREEDER_THRESHOLD

router = APIRouter()

# Species-specific estimates for the status board; legacy cycle calculations are unchanged.
STATUS_BOARD_GESTATION_DAYS = {SpeciesType.CATTLE: 283, SpeciesType.SHEEP: 147, SpeciesType.GOAT: 150}


@router.get("/reproduction/status-board", response_model=ReproductiveStatusBoardResponse)
async def reproductive_status_board(
    farm_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    """Current active female herd. Buckets deliberately overlap; dates use ranch local time."""
    today = datetime.now(timezone(timedelta(hours=3))).date()
    query = select(Animal).options(selectinload(Animal.category), selectinload(Animal.location)).where(
        Animal.sex == AnimalSex.FEMALE, Animal.status == AnimalStatus.ACTIVE)
    if farm_id is not None:
        query = query.where(Animal.location_id == farm_id)
    if species is not None:
        query = query.where(Animal.species == species)
    animals = (await db.execute(query.order_by(Animal.tag_number, Animal.id))).scalars().all()
    # Join the same filtered herd rather than making one query per animal or a large IN clause.
    events_query = select(ReproductiveEvent).join(Animal, Animal.id == ReproductiveEvent.animal_id).where(
        Animal.sex == AnimalSex.FEMALE, Animal.status == AnimalStatus.ACTIVE,
        ReproductiveEvent.event_date <= today)
    if farm_id is not None:
        events_query = events_query.where(Animal.location_id == farm_id)
    if species is not None:
        events_query = events_query.where(Animal.species == species)
    latest = {}
    aborted = set()
    for event in (await db.execute(events_query.order_by(
            ReproductiveEvent.event_date.desc(), ReproductiveEvent.id.desc()))).scalars():
        latest.setdefault(event.animal_id, event)
        if event.event_type == ReproductiveEventType.ABORTION and event.event_date >= today - timedelta(days=30):
            aborted.add(event.animal_id)
    labels = {
        "open": "Open", "pregnant": "Pregnant", "close_to_calving": "Close to calving",
        "due_this_month": "Due this month", "recently_calved": "Recently calved",
        "recently_aborted": "Recently aborted", "repeat_breeders": "Repeat breeders",
        "unknown_status": "Unknown status", "needs_attention": "Needs attention",
    }
    buckets = {key: {"label": label, "count": 0, "animals": []} for key, label in labels.items()}
    breeding_total = known_total = 0
    for animal in animals:
        born = animal.birth_date
        age = ((today.year - born.year) * 12 + today.month - born.month - (today.day < born.day)) if born else None
        species_key = "goats" if animal.species == SpeciesType.GOAT else animal.species.value
        breeding_age = age is not None and age >= BREEDING_AGE_MONTHS[species_key]
        reproductive_status = animal.reproductive_status or "unknown"
        pregnant = reproductive_status == "pregnant"
        known = reproductive_status in ("open", "pregnant")
        breeding_total += int(breeding_age)
        known_total += int(breeding_age and known)
        expected = None
        if pregnant and animal.last_pd_date is not None and animal.months_pregnant is not None:
            expected = animal.last_pd_date + timedelta(
                days=STATUS_BOARD_GESTATION_DAYS[animal.species] - animal.months_pregnant * 30)
        due = expected is not None and today <= expected <= today + timedelta(days=30)
        services = animal.services_without_conception or 0
        recent = latest.get(animal.id)
        row = dict(
            id=animal.id, tag_number=animal.tag_number, species=animal.species,
            category=animal.category.name_sw if animal.category else "Unknown",
            farm=animal.location.name if animal.location else "Unknown", age_months=age,
            reproductive_status=reproductive_status, last_event_date=recent.event_date if recent else None,
            last_event_type=recent.event_type if recent else None, last_pd_date=animal.last_pd_date,
            last_calving_date=animal.last_calving_date, months_pregnant=animal.months_pregnant,
            services_without_conception=services, expected_calving_date=expected,
        )
        membership = {
            "open": reproductive_status == "open", "pregnant": pregnant,
            "close_to_calving": due, "due_this_month": due,
            "recently_calved": animal.last_calving_date is not None and today - timedelta(days=30) <= animal.last_calving_date <= today,
            "recently_aborted": animal.id in aborted,
            "repeat_breeders": services >= REPEAT_BREEDER_THRESHOLD,
            "unknown_status": reproductive_status == "unknown" and not breeding_age,
            "needs_attention": (reproductive_status == "unknown" and breeding_age) or (
                pregnant and animal.last_pd_date is not None and animal.last_pd_date < today - timedelta(days=180)
            ) or services >= REPEAT_BREEDER_THRESHOLD,
        }
        for key, include in membership.items():
            if include:
                buckets[key]["animals"].append(row)
                buckets[key]["count"] += 1
    return ReproductiveStatusBoardResponse(
        summary=dict(total_breeding_females=breeding_total,
                     status_known_pct=round(known_total / breeding_total * 100, 1) if breeding_total else 0),
        **buckets,
    )
