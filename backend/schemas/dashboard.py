"""Dashboard response schemas."""
from pydantic import BaseModel
from typing import List, Optional

from models import EventType, SpeciesType


# Dashboard schemas
class SpeciesTotals(BaseModel):
    species: SpeciesType
    total: int
    color: str

class CategoryTotal(BaseModel):
    category_id: int
    category_name_sw: str
    count: int
    net_change: Optional[int] = None

class SpeciesCategoryTotals(BaseModel):
    species: SpeciesType
    categories: List[CategoryTotal]
    total: int

class LocationTotals(BaseModel):
    location_id: int
    location_name: str
    cattle: int
    sheep: int
    goat: int
    total: int

class EventSummary(BaseModel):
    event_type: EventType
    count: int
    stock_change: int

class HerdPerformance(BaseModel):
    species: SpeciesType
    total_stock: int
    breeding_females: int
    births_30d: int
    deaths_30d: int
    calving_rate: float
    mortality_rate: float
    color: str

class NetChange(BaseModel):
    species: SpeciesType
    births: int
    deaths: int
    bought: int
    sold: int
    gift_in: int
    gift_out: int
    missing: int
    weaned: int
    net_change: int  # births + bought + gift_in - deaths - sold - gift_out - missing

class DashboardResponse(BaseModel):
    species_totals: List[SpeciesTotals]
    species_category_totals: List[SpeciesCategoryTotals]
    location_totals: List[LocationTotals]
    today_events: List[EventSummary]
    total_animals: int
    total_locations: int
    pending_logs_today: int
    herd_performance: List[HerdPerformance]
    net_changes: List[NetChange]
    selected_location_id: Optional[int] = None
    selected_location_name: Optional[str] = None
