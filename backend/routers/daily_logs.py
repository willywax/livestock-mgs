"""Daily logs and their events (create/edit/delete with stock effects)."""
import logging
from datetime import date, datetime, timezone
from typing import List, Optional, Union

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models import AnimalLocationHistory, Category, DailyLog, Disease, Event, EventAnimalLink, EventType, Location, User, UserRole
from schemas import DailyLogCreate, DailyLogPage, DailyLogResponse, DailyLogUpdate, EventCreate, EventResponse, EventUpdate
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from services.animal_sync import _event_snapshot, _replay_daily_reproduction, _restore_after_rollback, _reverse_animal_sync, _sync_animals_from_event
from services.mortality import _validate_death_cause
from services.stock import apply_event_to_stock, check_stock_availability, reverse_event_stock

logger = logging.getLogger(__name__)
router = APIRouter()

# ==================== DAILY LOG ROUTES ====================
@router.get("/daily-logs", response_model=Union[List[DailyLogResponse], DailyLogPage])
async def list_daily_logs(
    location_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    """Bare list by default (existing clients); `{items,total,page,page_size,pages}` when page/page_size is given."""
    filters = []
    if location_id:
        filters.append(DailyLog.location_id == location_id)
    if start_date:
        filters.append(DailyLog.log_date >= start_date)
    if end_date:
        filters.append(DailyLog.log_date <= end_date)

    event_count_sq = (
        select(func.count(Event.id))
        .where(Event.daily_log_id == DailyLog.id)
        .correlate(DailyLog)
        .scalar_subquery()
    )
    # Only the columns the list response reads; skips locked_*/updated_*/created_by and the heavy
    # sale/death/gift/tag columns on events.
    query = select(DailyLog, event_count_sq.label("event_count")).options(
        load_only(DailyLog.id, DailyLog.location_id, DailyLog.log_date, DailyLog.has_events,
                  DailyLog.notes, DailyLog.is_locked, DailyLog.created_at),
        selectinload(DailyLog.location).load_only(Location.id, Location.name),
        selectinload(DailyLog.events).load_only(
            Event.id, Event.daily_log_id, Event.event_type, Event.species, Event.category_id, Event.count,
            Event.from_location_id, Event.to_location_id, Event.from_category_id, Event.to_category_id,
            Event.notes, Event.is_stock_event, Event.created_at),
    ).where(*filters).order_by(DailyLog.log_date.desc(), DailyLog.id.desc())

    paged = page is not None or page_size is not None
    if paged:
        page = page or 1
        page_size = page_size or 50
        query = query.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(query)).all()

    response = []
    for log, event_count in rows:
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
            events=events,
            event_count=event_count,
        ))

    if not paged:
        return response
    total = (await db.execute(select(func.count()).select_from(DailyLog).where(*filters))).scalar_one()
    return DailyLogPage(items=response, total=total, page=page, page_size=page_size,
                        pages=-(-total // page_size))

@router.get("/daily-logs/{log_id}", response_model=DailyLogResponse)
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
            pd_result=e.pd_result,
            months_pregnant=e.months_pregnant,
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

@router.post("/daily-logs", response_model=DailyLogResponse)
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
            pd_result=event_data.pd_result,
            months_pregnant=event_data.months_pregnant,
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
            pd_result=event.pd_result,
            months_pregnant=event.months_pregnant,
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


@router.post("/daily-logs/{log_id}/events", response_model=EventResponse)
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
        pd_result=event_data.pd_result,
        months_pregnant=event_data.months_pregnant,
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
        pd_result=event.pd_result,
        months_pregnant=event.months_pregnant,
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

@router.post("/daily-logs/{log_id}/lock")
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

@router.put("/daily-logs/{log_id}", response_model=DailyLogResponse)
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

    if data.log_date is not None:
        try:
            async with db.begin_nested():
                links = (await db.execute(select(EventAnimalLink).join(Event, Event.id == EventAnimalLink.event_id)
                    .where(Event.daily_log_id == log_id, EventAnimalLink.is_active.is_(True)))).scalars().all()
                affected = set()
                for link in links:
                    if link.reproductive_payload:
                        link.reproductive_payload = {**link.reproductive_payload, 'date': log.log_date.isoformat()}
                        affected.add(link.animal_id)
                await db.flush()
                for animal_id in sorted(affected):
                    await _replay_daily_reproduction(db, animal_id)
            await db.commit()
        except Exception:
            await db.rollback()
            await _restore_after_rollback(db, log)
            logger.warning("Daily log date changed but reproductive replay failed", exc_info=True)

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
@router.put("/events/{event_id}", response_model=EventResponse)
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
    effective_result = data.pd_result if 'pd_result' in data.model_fields_set else event.pd_result
    if effective_type == EventType.PD_TEST and effective_result is None:
        raise HTTPException(status_code=400, detail="A PD test requires result pregnant or open")
    if "cause_of_death_id" in data.model_fields_set:
        await _validate_death_cause(db, effective_type, data.cause_of_death_id,
                                    existing_id=event.cause_of_death_id)
    # ADDED: Type-specific field guard — reject fields that don't apply to event_type
    _type_fields: dict = {
        EventType.PD_TEST: {"pd_result", "months_pregnant"},
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
        event.is_stock_event = effective_type not in (EventType.ABORTION, EventType.PD_TEST, EventType.SERVICE)

    if effective_type in (EventType.ABORTION, EventType.PD_TEST, EventType.SERVICE):
        event.is_stock_event = False
    if 'pd_result' in data.model_fields_set:
        event.pd_result = data.pd_result
    if 'months_pregnant' in data.model_fields_set:
        event.months_pregnant = data.months_pregnant
    if effective_type == EventType.PD_TEST and effective_result == 'open':
        event.months_pregnant = None
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
        pd_result=event.pd_result,
        months_pregnant=event.months_pregnant,
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

@router.delete("/events/{event_id}")
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

    # Tombstones retain reproductive baselines without dangling event foreign keys.
    await db.execute(update(EventAnimalLink).where(EventAnimalLink.event_id == event.id)
                     .values(event_id=None, is_active=False))
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
