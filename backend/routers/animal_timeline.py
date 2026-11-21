"""Animal activity timelines."""
from datetime import date
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models import AnimalNote, BCSRecord, CategoryScope, DailyLog, Event, EventAnimalLink, EventType, FarmHealthEvent as FarmHealthEventModel, Location, ReproductiveCycle, User
from schemas import AnimalTimelineItem, AnimalTimelineResponse, TimelineItem
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import _ANY_ROLE, _CYCLE_LOAD, _require_animal

router = APIRouter()

# ---------- Daily-log animal timeline (existing activity timeline stays compatible) ----------
@router.get("/animals/{animal_id}/daily-log-timeline", response_model=AnimalTimelineResponse)
async def get_daily_log_animal_timeline(
    animal_id: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    event_type: Optional[EventType] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _require_animal(db, animal_id)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must not be after to_date")
    linked = select(EventAnimalLink.id).where(EventAnimalLink.event_id == Event.id,
        EventAnimalLink.animal_id == animal_id, EventAnimalLink.is_active.is_(True)).exists()
    filters = [linked]
    if from_date:
        filters.append(DailyLog.log_date >= from_date)
    if to_date:
        filters.append(DailyLog.log_date <= to_date)
    if event_type:
        filters.append(Event.event_type == event_type)
    total = await db.scalar(select(func.count(Event.id)).join(DailyLog).where(*filters))
    query = (select(Event, DailyLog.log_date, Location.name, User.name)
             .join(DailyLog, DailyLog.id == Event.daily_log_id)
             .join(Location, Location.id == DailyLog.location_id)
             .outerjoin(User, User.id == Event.created_by)
             .where(*filters).order_by(DailyLog.log_date.desc(), Event.id.desc())
             .offset((page - 1) * page_size).limit(page_size))
    labels = {EventType.BIRTH: "Birth", EventType.PD_TEST: "PD test", EventType.SERVICE: "Service / mating",
              EventType.ABORTION: "Abortion", EventType.SOLD: "Sale", EventType.DEATH: "Death",
              EventType.TRANSFER: "Transfer", EventType.CATEGORY_CHANGE: "Category change"}
    items = [AnimalTimelineItem(event_id=event.id, event_type=event.event_type, event_date=day,
        event_type_label=labels.get(event.event_type, event.event_type.value.replace('_', ' ').title()),
        daily_log_id=event.daily_log_id, farm_name=farm, notes=event.notes, quantity=event.count,
        result=event.pd_result if event.event_type == EventType.PD_TEST else None, recorded_by_name=recorder)
        for event, day, farm, recorder in (await db.execute(query)).all()]
    return AnimalTimelineResponse(items=items, total=total or 0, page=page, page_size=page_size)


# ---------- Animal timeline ----------
@router.get("/animals/{animal_id}/timeline", response_model=List[TimelineItem])
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
