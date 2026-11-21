"""Dashboard aggregate endpoint."""
from datetime import date, timedelta
from typing import Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models import Category, DailyLog, Event, EventType, Location, SpeciesType, StockLevel, User, UserRole
from schemas import CategoryTotal, DashboardResponse, EventSummary, HerdPerformance, LocationTotals, NetChange, SpeciesCategoryTotals, SpeciesTotals
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()

# ==================== DASHBOARD ROUTES ====================
@router.get("/dashboard", response_model=DashboardResponse)
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
