"""Daily, range, analytics and detailed reports."""
from datetime import date, timedelta
from typing import Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import AbortionStage, Category, DailyLog, Event, EventType, Location, SpeciesType, StockLevel, User, UserRole
from schemas import AbortionAnalysis, AbortionBySpecies, AbortionByStage, AnalyticsResponse, CategoryTotal, DeathAnalysis, DeathByCategory, DeathByCause, DeathByDisease, DeathByLocation, DeathBySpecies, DetailedReportEvent, DetailedReportResponse, NetChange, SalesAnalysis, SalesByBuyer, SalesBySpecies, SpeciesCategoryTotals, SpeciesRates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.stock_snapshot import build_location_totals_from_snapshot, build_stock_snapshot

router = APIRouter()

# ==================== REPORTS ROUTES ====================

@router.get("/reports/daily")
async def get_daily_report(
    report_date: date = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    if not report_date:
        report_date = date.today()
    
    # Get all logs for the date
    result = await db.execute(
        select(DailyLog)
        .options(selectinload(DailyLog.location), selectinload(DailyLog.events))
        .where(DailyLog.log_date == report_date)
    )
    logs = result.scalars().all()
    
    # Get current stock levels
    result = await db.execute(
        select(StockLevel)
        .options(selectinload(StockLevel.location), selectinload(StockLevel.category))
    )
    stock_levels = result.scalars().all()
    
    # Organize stock by location and species
    stock_by_location = {}
    for sl in stock_levels:
        loc_name = sl.location.name if sl.location else "Unknown"
        if loc_name not in stock_by_location:
            stock_by_location[loc_name] = {"cattle": 0, "sheep": 0, "goat": 0}
        stock_by_location[loc_name][sl.species.value] += sl.current_count
    
    # Organize events
    events_by_location = {}
    for log in logs:
        loc_name = log.location.name if log.location else "Unknown"
        if loc_name not in events_by_location:
            events_by_location[loc_name] = []
        
        for event in log.events:
            events_by_location[loc_name].append({
                "type": event.event_type.value,
                "species": event.species.value,
                "count": event.count,
                "notes": event.notes
            })
    
    return {
        "date": report_date.isoformat(),
        "stock_by_location": stock_by_location,
        "events_by_location": events_by_location,
        "total_logs": len(logs)
    }

@router.get("/reports/range")
async def get_range_report(
    start_date: date,
    end_date: date,
    event_type: Optional[EventType] = None,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    query = select(Event).join(DailyLog).where(
        and_(
            DailyLog.log_date >= start_date,
            DailyLog.log_date <= end_date
        )
    )
    
    if event_type:
        query = query.where(Event.event_type == event_type)
    if location_id:
        query = query.where(
            or_(
                DailyLog.location_id == location_id,
                Event.from_location_id == location_id,
                Event.to_location_id == location_id
            )
        )
    
    result = await db.execute(query)
    events = result.scalars().all()
    
    # Aggregate by event type
    events_by_type = {}
    net_movements = {"cattle": 0, "sheep": 0, "goat": 0}
    
    for event in events:
        et = event.event_type.value
        if et not in events_by_type:
            events_by_type[et] = {"count": 0, "total_animals": 0}
        events_by_type[et]["count"] += 1
        events_by_type[et]["total_animals"] += event.count
        
        if event.is_stock_event:
            species_key = event.species.value
            if event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
                net_movements[species_key] += event.count
            elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
                net_movements[species_key] -= event.count
    
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "events_by_type": events_by_type,
        "net_movements": net_movements,
        "total_events": len(events)
    }

@router.get("/reports/analytics", response_model=AnalyticsResponse)
async def get_analytics_report(
    start_date: date,
    end_date: date,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    """Get mortality rate, calving rate, weaning rate, death/abortion/sales analysis for a date range"""
    
    # Get location info if filtered
    location_name = None
    if location_id:
        loc_result = await db.execute(select(Location).where(Location.id == location_id))
        loc = loc_result.scalar_one_or_none()
        if loc:
            location_name = loc.name
    
    species_colors = {
        SpeciesType.CATTLE: "#2D5A27",
        SpeciesType.GOAT: "#D97706",
        SpeciesType.SHEEP: "#0284C7"
    }
    
    # Get all events in date range with category info
    events_query = (
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.disease), selectinload(Event.daily_log))
        .join(DailyLog)
        .where(and_(DailyLog.log_date >= start_date, DailyLog.log_date <= end_date))
    )
    if location_id:
        events_query = events_query.where(
            or_(
                DailyLog.location_id == location_id,
                Event.from_location_id == location_id,
                Event.to_location_id == location_id
            )
        )
    result = await db.execute(events_query)
    events = result.scalars().all()

    category_result = await db.execute(
        select(Category).where(Category.name_sw.in_(["Koo", "Dume Mbegu"]))
    )
    categories = category_result.scalars().all()
    category_ids = {(cat.species, cat.name_sw): cat.id for cat in categories}

    def category_net_change(species: SpeciesType, category_id: Optional[int]) -> int:
        if not category_id:
            return 0
        change = 0
        for event in events:
            if event.species != species or not event.is_stock_event:
                continue
            if event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
                if event.category_id == category_id:
                    change += event.count
            elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
                if event.category_id == category_id:
                    change -= event.count
            elif event.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
                if event.from_category_id == category_id:
                    change -= event.count
                if event.to_category_id == category_id:
                    change += event.count
        return change
    
    # Get current stock levels for each species
    species_data = {}
    net_changes_list = []
    
    for sp in SpeciesType:
        # Get total stock
        stock_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(StockLevel.species == sp)
        if location_id:
            stock_query = stock_query.where(StockLevel.location_id == location_id)
        result = await db.execute(stock_query)
        total_stock = result.scalar() or 0
        
        # Count events for this species
        birth_events = [e for e in events if e.species == sp and e.event_type == EventType.BIRTH]
        births = sum(e.count for e in birth_events)
        births_male = sum(
            e.count for e in birth_events
            if e.category and e.category.name_sw.strip().lower().endswith(" dume")
        )
        births_female = sum(
            e.count for e in birth_events
            if e.category and e.category.name_sw.strip().lower().endswith(" jike")
        )
        deaths = sum(e.count for e in events if e.species == sp and e.event_type == EventType.DEATH)
        weaned = sum(e.count for e in events if e.species == sp and e.event_type == EventType.WEANING)
        sold = sum(e.count for e in events if e.species == sp and e.event_type == EventType.SOLD)
        bought = sum(e.count for e in events if e.species == sp and e.event_type == EventType.BOUGHT)
        gift_in = sum(e.count for e in events if e.species == sp and e.event_type == EventType.GIFT_IN)
        gift_out = sum(e.count for e in events if e.species == sp and e.event_type == EventType.GIFT_OUT)
        missing = sum(e.count for e in events if e.species == sp and e.event_type == EventType.MISSING)
        
        breeding_female_category_id = category_ids.get((sp, "Koo"))
        breeding_male_category_id = category_ids.get((sp, "Dume Mbegu"))

        # Get breeding female count (Koo category) for calving rate
        breeding_females = 0
        if breeding_female_category_id:
            bf_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                and_(StockLevel.species == sp, StockLevel.category_id == breeding_female_category_id)
            )
            if location_id:
                bf_query = bf_query.where(StockLevel.location_id == location_id)
            result = await db.execute(bf_query)
            breeding_females = result.scalar() or 0

        breeding_males = 0
        if breeding_male_category_id:
            bm_query = select(func.coalesce(func.sum(StockLevel.current_count), 0)).where(
                and_(StockLevel.species == sp, StockLevel.category_id == breeding_male_category_id)
            )
            if location_id:
                bm_query = bm_query.where(StockLevel.location_id == location_id)
            result = await db.execute(bm_query)
            breeding_males = result.scalar() or 0

        breeding_females_trend = category_net_change(sp, breeding_female_category_id)
        
        # Calculate rates
        mortality_rate = (deaths / total_stock * 100) if total_stock > 0 else 0
        calving_rate = (births / breeding_females * 100) if breeding_females > 0 else 0
        weaning_rate = (weaned / births * 100) if births > 0 else 0
        
        species_data[sp] = SpeciesRates(
            species=sp,
            total_stock=total_stock,
            breeding_females=breeding_females,
            breeding_males=breeding_males,
            breeding_females_trend=breeding_females_trend,
            births=births,
            births_male=births_male,
            births_female=births_female,
            deaths=deaths,
            weaned=weaned,
            sold=sold,
            bought=bought,
            calving_rate=round(calving_rate, 2),
            mortality_rate=round(mortality_rate, 2),
            weaning_rate=round(weaning_rate, 2),
            color=species_colors.get(sp, "#666666")
        )
        
        # Net change calculation
        net_change = births + bought + gift_in - deaths - sold - gift_out - missing
        net_changes_list.append(NetChange(
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

    # Category breakdown for animal groups
    category_totals = []
    for sp in SpeciesType:
        category_net_changes = {}
        for event in events:
            if event.species != sp or not event.is_stock_event:
                continue
            if event.event_type in [EventType.BIRTH, EventType.GIFT_IN, EventType.BOUGHT]:
                if event.category_id:
                    category_net_changes[event.category_id] = category_net_changes.get(event.category_id, 0) + event.count
            elif event.event_type in [EventType.DEATH, EventType.SOLD, EventType.MISSING, EventType.GIFT_OUT]:
                if event.category_id:
                    category_net_changes[event.category_id] = category_net_changes.get(event.category_id, 0) - event.count
            elif event.event_type in [EventType.CATEGORY_CHANGE, EventType.WEANING]:
                if event.from_category_id:
                    category_net_changes[event.from_category_id] = category_net_changes.get(event.from_category_id, 0) - event.count
                if event.to_category_id:
                    category_net_changes[event.to_category_id] = category_net_changes.get(event.to_category_id, 0) + event.count

        cat_query = select(StockLevel).options(selectinload(StockLevel.category)).where(StockLevel.species == sp)
        if location_id:
            cat_query = cat_query.where(StockLevel.location_id == location_id)
        result = await db.execute(cat_query)
        stock_levels = result.scalars().all()

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
                count=data["count"],
                net_change=category_net_changes.get(cat_id, 0)
            )
            for cat_id, data in category_counts.items()
            if data["count"] > 0
        ]

        species_total = sum(c.count for c in categories_list)
        category_totals.append(SpeciesCategoryTotals(
            species=sp,
            categories=categories_list,
            total=species_total
        ))
    
    # ===== DETAILED DEATH ANALYSIS =====
    death_events = [e for e in events if e.event_type == EventType.DEATH]
    total_deaths = sum(e.count for e in death_events)

    location_lookup = {}
    location_result = await db.execute(select(Location))
    for loc in location_result.scalars().all():
        location_lookup[loc.id] = loc.name
    
    # Aggregate death causes
    death_causes_dict = {}
    for event in death_events:
        cause = event.cause_of_death or "Unknown"
        if cause not in death_causes_dict:
            death_causes_dict[cause] = {"count": 0, "days_sick_sum": 0, "days_sick_count": 0}
        death_causes_dict[cause]["count"] += event.count
        if event.days_sick is not None:
            death_causes_dict[cause]["days_sick_sum"] += event.days_sick * event.count
            death_causes_dict[cause]["days_sick_count"] += event.count
    
    top_causes = []
    for cause, data in sorted(death_causes_dict.items(), key=lambda x: x[1]["count"], reverse=True):
        avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
        top_causes.append(DeathByCause(
            cause=cause,
            count=data["count"],
            percentage=round((data["count"] / total_deaths * 100) if total_deaths > 0 else 0, 1),
            avg_days_sick=round(avg_days, 1) if avg_days else None
        ))
    
    # Aggregate diseases
    disease_dict = {}
    for event in death_events:
        if event.disease_id and event.disease:
            d_id = event.disease_id
            if d_id not in disease_dict:
                disease_dict[d_id] = {"name": event.disease.name, "count": 0, "days_sick_sum": 0, "days_sick_count": 0}
            disease_dict[d_id]["count"] += event.count
            if event.days_sick is not None:
                disease_dict[d_id]["days_sick_sum"] += event.days_sick * event.count
                disease_dict[d_id]["days_sick_count"] += event.count
    
    top_diseases = []
    for d_id, data in sorted(disease_dict.items(), key=lambda x: x[1]["count"], reverse=True):
        avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
        top_diseases.append(DeathByDisease(
            disease_id=d_id,
            disease_name=data["name"],
            count=data["count"],
            percentage=round((data["count"] / total_deaths * 100) if total_deaths > 0 else 0, 1),
            avg_days_sick=round(avg_days, 1) if avg_days else None
        ))
    
    # Death analysis by species
    deaths_by_species = []
    total_with_vet = sum(e.count for e in death_events if e.attending_vet)
    
    for sp in SpeciesType:
        sp_deaths = [e for e in death_events if e.species == sp]
        sp_total = sum(e.count for e in sp_deaths)
        
        if sp_total == 0:
            continue
        
        # By category
        cat_deaths = {}
        for e in sp_deaths:
            cat_id = e.category_id or 0
            cat_name = e.category.name_sw if e.category else "Unknown"
            if cat_id not in cat_deaths:
                cat_deaths[cat_id] = {"name_sw": cat_name, "count": 0}
            cat_deaths[cat_id]["count"] += e.count
        
        by_category = [
            DeathByCategory(category_id=cat_id, category_name_sw=data["name_sw"], count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1))
            for cat_id, data in sorted(cat_deaths.items(), key=lambda x: x[1]["count"], reverse=True)
        ]
        
        # By cause
        sp_causes = {}
        for e in sp_deaths:
            cause = e.cause_of_death or "Unknown"
            if cause not in sp_causes:
                sp_causes[cause] = {"count": 0, "days_sick_sum": 0, "days_sick_count": 0}
            sp_causes[cause]["count"] += e.count
            if e.days_sick is not None:
                sp_causes[cause]["days_sick_sum"] += e.days_sick * e.count
                sp_causes[cause]["days_sick_count"] += e.count
        
        by_cause = []
        for cause, data in sorted(sp_causes.items(), key=lambda x: x[1]["count"], reverse=True):
            avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
            by_cause.append(DeathByCause(cause=cause, count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1),
                avg_days_sick=round(avg_days, 1) if avg_days else None))
        
        # By disease for this species
        sp_disease_dict = {}
        for e in sp_deaths:
            if e.disease_id and e.disease:
                d_id = e.disease_id
                if d_id not in sp_disease_dict:
                    sp_disease_dict[d_id] = {"name": e.disease.name, "count": 0, "days_sick_sum": 0, "days_sick_count": 0}
                sp_disease_dict[d_id]["count"] += e.count
                if e.days_sick is not None:
                    sp_disease_dict[d_id]["days_sick_sum"] += e.days_sick * e.count
                    sp_disease_dict[d_id]["days_sick_count"] += e.count
        
        by_disease = []
        for d_id, data in sorted(sp_disease_dict.items(), key=lambda x: x[1]["count"], reverse=True):
            avg_days = (data["days_sick_sum"] / data["days_sick_count"]) if data["days_sick_count"] > 0 else None
            by_disease.append(DeathByDisease(disease_id=d_id, disease_name=data["name"], count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1),
                avg_days_sick=round(avg_days, 1) if avg_days else None))
        
        sp_with_vet = sum(e.count for e in sp_deaths if e.attending_vet)
        total_days = sum((e.days_sick or 0) * e.count for e in sp_deaths if e.days_sick is not None)
        days_count = sum(e.count for e in sp_deaths if e.days_sick is not None)
        sp_avg_days = (total_days / days_count) if days_count > 0 else None
        
        deaths_by_species.append(DeathBySpecies(
            species=sp, total_deaths=sp_total, by_category=by_category, by_cause=by_cause,
            by_disease=by_disease, with_vet_attendance=sp_with_vet,
            without_vet_attendance=sp_total - sp_with_vet,
            avg_days_sick=round(sp_avg_days, 1) if sp_avg_days else None
        ))
    
    vet_attendance_rate = (total_with_vet / total_deaths * 100) if total_deaths > 0 else 0

    death_locations = {}
    for event in death_events:
        log = event.daily_log
        if not log:
            continue
        loc_id = log.location_id
        if not loc_id:
            continue
        if loc_id not in death_locations:
            death_locations[loc_id] = {
                "name": location_lookup.get(loc_id, "Unknown"),
                "count": 0
            }
        death_locations[loc_id]["count"] += event.count

    deaths_by_location = []
    for loc_id, data in sorted(death_locations.items(), key=lambda x: x[1]["count"], reverse=True):
        deaths_by_location.append(DeathByLocation(
            location_id=loc_id,
            location_name=data["name"],
            total_deaths=data["count"],
            percentage=round((data["count"] / total_deaths * 100) if total_deaths > 0 else 0, 1)
        ))
    death_analysis = DeathAnalysis(
        total_deaths=total_deaths, by_species=deaths_by_species, top_causes=top_causes,
        top_diseases=top_diseases, vet_attendance_rate=round(vet_attendance_rate, 1),
        by_location=deaths_by_location
    )
    
    # ===== ABORTION ANALYSIS =====
    abortion_events = [e for e in events if e.event_type == EventType.ABORTION]
    total_abortions = sum(e.count for e in abortion_events)
    
    # Overall by stage
    stage_counts = {AbortionStage.EARLY: 0, AbortionStage.MID: 0, AbortionStage.LATE: 0}
    for e in abortion_events:
        if e.abortion_stage:
            stage_counts[e.abortion_stage] += e.count
    
    overall_by_stage = [
        AbortionByStage(stage=stage, count=count,
            percentage=round((count / total_abortions * 100) if total_abortions > 0 else 0, 1))
        for stage, count in stage_counts.items()
    ]
    
    # By species
    abortions_by_species = []
    for sp in SpeciesType:
        sp_abortions = [e for e in abortion_events if e.species == sp]
        sp_total = sum(e.count for e in sp_abortions)
        
        if sp_total == 0:
            continue
        
        # By stage for this species
        sp_stage_counts = {AbortionStage.EARLY: 0, AbortionStage.MID: 0, AbortionStage.LATE: 0}
        for e in sp_abortions:
            if e.abortion_stage:
                sp_stage_counts[e.abortion_stage] += e.count
        
        sp_by_stage = [
            AbortionByStage(stage=stage, count=count,
                percentage=round((count / sp_total * 100) if sp_total > 0 else 0, 1))
            for stage, count in sp_stage_counts.items()
        ]
        
        # By category
        cat_abortions = {}
        for e in sp_abortions:
            cat_id = e.category_id or 0
            cat_name = e.category.name_sw if e.category else "Unknown"
            if cat_id not in cat_abortions:
                cat_abortions[cat_id] = {"name_sw": cat_name, "count": 0}
            cat_abortions[cat_id]["count"] += e.count
        
        by_category = [
            DeathByCategory(category_id=cat_id, category_name_sw=data["name_sw"], count=data["count"],
                percentage=round((data["count"] / sp_total * 100), 1))
            for cat_id, data in sorted(cat_abortions.items(), key=lambda x: x[1]["count"], reverse=True)
        ]
        
        # Calculate abortion rate (abortions / breeding females)
        breeding_females = species_data[sp].breeding_females
        abortion_rate = (sp_total / breeding_females * 100) if breeding_females > 0 else 0
        
        abortions_by_species.append(AbortionBySpecies(
            species=sp, total_abortions=sp_total, by_stage=sp_by_stage,
            by_category=by_category, abortion_rate=round(abortion_rate, 2)
        ))
    
    abortion_analysis = AbortionAnalysis(
        total_abortions=total_abortions, by_species=abortions_by_species, by_stage=overall_by_stage
    )
    
    # ===== SALES ANALYSIS =====
    sale_events = [e for e in events if e.event_type == EventType.SOLD]
    total_sales_count = sum(e.count for e in sale_events)
    total_sales_value = sum(e.sale_price or 0 for e in sale_events if e.sale_price)
    avg_sale_price = (total_sales_value / total_sales_count) if total_sales_count > 0 else 0
    
    # By species
    sales_by_species = []
    for sp in SpeciesType:
        sp_sales = [e for e in sale_events if e.species == sp]
        sp_count = sum(e.count for e in sp_sales)
        sp_value = sum(e.sale_price or 0 for e in sp_sales if e.sale_price)
        sp_avg = (sp_value / sp_count) if sp_count > 0 else 0
        
        if sp_count == 0:
            continue
        
        # By category
        cat_sales = {}
        for e in sp_sales:
            cat_id = e.category_id or 0
            cat_name = e.category.name_sw if e.category else "Unknown"
            if cat_id not in cat_sales:
                cat_sales[cat_id] = {"category_name_sw": cat_name, "count": 0, "total_value": 0}
            cat_sales[cat_id]["count"] += e.count
            cat_sales[cat_id]["total_value"] += e.sale_price or 0
        
        by_category = []
        for cat_id, data in sorted(cat_sales.items(), key=lambda x: x[1]["count"], reverse=True):
            by_category.append({
                "category_name_sw": data["category_name_sw"],
                "count": data["count"],
                "total_value": data["total_value"],
                "avg_price": round(data["total_value"] / data["count"], 2) if data["count"] > 0 else 0
            })
        
        sales_by_species.append(SalesBySpecies(
            species=sp, count=sp_count, total_value=sp_value,
            average_price=round(sp_avg, 2), by_category=by_category
        ))
    
    # Top buyers
    buyer_dict = {}
    for e in sale_events:
        buyer = e.buyer_name or "Unknown"
        if buyer not in buyer_dict:
            buyer_dict[buyer] = {"count": 0, "total_value": 0, "species": {}}
        buyer_dict[buyer]["count"] += e.count
        buyer_dict[buyer]["total_value"] += e.sale_price or 0
        sp_name = e.species.value
        buyer_dict[buyer]["species"][sp_name] = buyer_dict[buyer]["species"].get(sp_name, 0) + e.count
    
    top_buyers = [
        SalesByBuyer(buyer_name=name, count=data["count"], total_value=data["total_value"],
            species_breakdown=data["species"])
        for name, data in sorted(buyer_dict.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    ]
    
    # Price range
    all_prices = [e.sale_price for e in sale_events if e.sale_price and e.sale_price > 0]
    price_range = {
        "min": min(all_prices) if all_prices else 0,
        "max": max(all_prices) if all_prices else 0,
        "median": sorted(all_prices)[len(all_prices)//2] if all_prices else 0
    }
    
    sales_analysis = SalesAnalysis(
        total_count=total_sales_count, total_value=total_sales_value,
        average_price=round(avg_sale_price, 2), by_species=sales_by_species,
        top_buyers=top_buyers, price_range=price_range
    )
    
    return AnalyticsResponse(
        period_start=start_date, period_end=end_date,
        species_rates=list(species_data.values()), category_totals=category_totals, death_analysis=death_analysis,
        abortion_analysis=abortion_analysis, sales_analysis=sales_analysis,
        net_changes=net_changes_list, location_id=location_id, location_name=location_name
    )

@router.get("/reports/detailed", response_model=DetailedReportResponse)
async def get_detailed_report(
    start_date: date,
    end_date: date,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER))
):
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    selected_location_name = None
    if location_id:
        loc_result = await db.execute(select(Location).where(Location.id == location_id))
        loc = loc_result.scalar_one_or_none()
        if loc:
            selected_location_name = loc.name

    opening_date = start_date - timedelta(days=1)
    opening_snapshot = await build_stock_snapshot(db, opening_date, location_id=location_id)
    closing_snapshot = await build_stock_snapshot(db, end_date, location_id=location_id)

    include_zero = bool(location_id)
    opening_totals = await build_location_totals_from_snapshot(
        db, opening_snapshot, location_id=location_id, include_zero=include_zero
    )
    closing_totals = await build_location_totals_from_snapshot(
        db, closing_snapshot, location_id=location_id, include_zero=include_zero
    )

    events_query = (
        select(Event, DailyLog.log_date, DailyLog.location_id)
        .join(DailyLog)
        .options(
            selectinload(Event.daily_log).selectinload(DailyLog.location),
            selectinload(Event.category),
            selectinload(Event.from_location),
            selectinload(Event.to_location),
            selectinload(Event.from_category),
            selectinload(Event.to_category)
        )
        .where(and_(DailyLog.log_date >= start_date, DailyLog.log_date <= end_date))
        .order_by(DailyLog.log_date.asc(), Event.id.asc())
    )
    if location_id:
        events_query = events_query.where(DailyLog.location_id == location_id)
    result = await db.execute(events_query)
    event_rows = result.all()

    events = []
    for event, log_date, log_location_id in event_rows:
        log_location_name = "Unknown"
        if event.daily_log and event.daily_log.location:
            log_location_name = event.daily_log.location.name

        events.append(DetailedReportEvent(
            id=event.id,
            log_date=log_date,
            location_id=log_location_id,
            location_name=log_location_name,
            event_type=event.event_type,
            species=event.species,
            count=event.count,
            category_name_sw=event.category.name_sw if event.category else None,
            from_location_name=event.from_location.name if event.from_location else None,
            to_location_name=event.to_location.name if event.to_location else None,
            from_category_name_sw=event.from_category.name_sw if event.from_category else None,
            to_category_name_sw=event.to_category.name_sw if event.to_category else None,
            notes=event.notes
        ))

    return DetailedReportResponse(
        start_date=start_date,
        end_date=end_date,
        location_id=location_id,
        location_name=selected_location_name,
        opening_totals=opening_totals,
        closing_totals=closing_totals,
        events=events
    )
