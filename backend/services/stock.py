"""Stock accounting: availability checks, apply/reverse event effects, recompute. Event writes and stock adjustments must stay symmetric and commit in one transaction."""
from datetime import date, datetime, timezone
from typing import List, Optional

from models import DailyLog, Event, EventType, OpeningBalance, SpeciesType, StockLevel
from schemas import EventCreate
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
