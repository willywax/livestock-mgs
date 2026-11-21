"""Daily/range/analytics/detailed report schemas, including abortion and sales analytics."""
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

from models import AbortionStage, EventType, SpeciesType

from schemas.dashboard import LocationTotals, NetChange, SpeciesCategoryTotals


# Report schemas
class DateRangeReport(BaseModel):
    start_date: date
    end_date: date
    events_by_type: dict
    net_movements: dict
    location_summaries: List[dict]

class DetailedReportEvent(BaseModel):
    id: int
    log_date: date
    location_id: int
    location_name: str
    event_type: EventType
    species: SpeciesType
    count: int
    category_name_sw: Optional[str] = None
    from_location_name: Optional[str] = None
    to_location_name: Optional[str] = None
    from_category_name_sw: Optional[str] = None
    to_category_name_sw: Optional[str] = None
    notes: Optional[str] = None

class DetailedReportResponse(BaseModel):
    start_date: date
    end_date: date
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    opening_totals: List[LocationTotals]
    closing_totals: List[LocationTotals]
    events: List[DetailedReportEvent]

class SpeciesRates(BaseModel):
    species: SpeciesType
    total_stock: int
    breeding_females: int
    breeding_males: int
    breeding_females_trend: int
    births: int
    births_male: int
    births_female: int
    deaths: int
    weaned: int
    sold: int
    bought: int
    calving_rate: float  # births / breeding females * 100
    mortality_rate: float  # deaths / total stock * 100
    weaning_rate: float  # weaned / births * 100
    color: str

class DeathByCategory(BaseModel):
    category_id: int
    category_name_sw: str
    count: int
    percentage: float

class DeathByCause(BaseModel):
    cause: str
    count: int
    percentage: float
    avg_days_sick: Optional[float] = None

class DeathByDisease(BaseModel):
    disease_id: int
    disease_name: str
    count: int
    percentage: float
    avg_days_sick: Optional[float] = None

class DeathByLocation(BaseModel):
    location_id: int
    location_name: str
    total_deaths: int
    percentage: float

class DeathBySpecies(BaseModel):
    species: SpeciesType
    total_deaths: int
    by_category: List[DeathByCategory]
    by_cause: List[DeathByCause]
    by_disease: List[DeathByDisease]  # Detailed disease breakdown
    with_vet_attendance: int
    without_vet_attendance: int
    avg_days_sick: Optional[float] = None

class DeathAnalysis(BaseModel):
    total_deaths: int
    by_species: List[DeathBySpecies]
    by_location: List[DeathByLocation]
    top_causes: List[DeathByCause]
    top_diseases: List[DeathByDisease]  # Top diseases across all species
    vet_attendance_rate: float

# Abortion Analytics
class AbortionByStage(BaseModel):
    stage: AbortionStage
    count: int
    percentage: float

class AbortionBySpecies(BaseModel):
    species: SpeciesType
    total_abortions: int
    by_stage: List[AbortionByStage]
    by_category: List[DeathByCategory]  # Reuse for category breakdown
    abortion_rate: float  # abortions / breeding females * 100

class AbortionAnalysis(BaseModel):
    total_abortions: int
    by_species: List[AbortionBySpecies]
    by_stage: List[AbortionByStage]  # Overall stage breakdown

# Sales Analytics
class SalesBySpecies(BaseModel):
    species: SpeciesType
    count: int
    total_value: int
    average_price: float
    by_category: List[dict]  # [{category_name_sw, count, total_value, avg_price}]

class SalesByBuyer(BaseModel):
    buyer_name: str
    count: int
    total_value: int
    species_breakdown: dict  # {species: count}

class SalesAnalysis(BaseModel):
    total_count: int
    total_value: int
    average_price: float
    by_species: List[SalesBySpecies]
    top_buyers: List[SalesByBuyer]
    price_range: dict  # {min, max, median}

class AnalyticsResponse(BaseModel):
    period_start: date
    period_end: date
    species_rates: List[SpeciesRates]
    category_totals: List[SpeciesCategoryTotals]
    death_analysis: DeathAnalysis
    abortion_analysis: AbortionAnalysis
    sales_analysis: SalesAnalysis
    net_changes: List[NetChange]
    location_id: Optional[int] = None
    location_name: Optional[str] = None
