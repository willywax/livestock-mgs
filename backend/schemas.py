from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from models import (
    UserRole, EventType, SpeciesType, AbortionStage, AnimalSex, AnimalAcquisitionType, AnimalStatus,
    HealthEventType, CategoryScope, VaccineType as VaccineTypeModel,
    RegistrySyncAction, RegistrySyncState,
)

# Auth schemas
class UserLogin(BaseModel):
    phone: str
    password: str

class UserCreate(BaseModel):
    phone: str
    password: str
    name: str
    role: UserRole = UserRole.VIEWER

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    phone: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# Location schemas
class LocationCreate(BaseModel):
    name: str
    description: Optional[str] = None

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime

# Category schemas
class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name_sw: str
    name_en: str
    species: SpeciesType
    sort_order: int

# Opening Balance schemas
class OpeningBalanceCreate(BaseModel):
    location_id: int
    species: SpeciesType
    category_id: int
    count: int
    period_start: date

class OpeningBalanceUpdate(BaseModel):
    count: int

class OpeningBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    species: SpeciesType
    category_id: int
    count: int
    period_start: date
    location_name: Optional[str] = None
    category_name_sw: Optional[str] = None

# Disease schemas
class DiseaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    species: Optional[SpeciesType] = None

class DiseaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str]
    species: Optional[SpeciesType]
    is_active: bool

# Event schemas
class EventCreate(BaseModel):
    event_type: EventType
    species: SpeciesType
    category_id: Optional[int] = None
    count: int = 0
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    from_category_id: Optional[int] = None
    to_category_id: Optional[int] = None
    notes: Optional[str] = None
    is_stock_event: bool = True
    # Common field for all events
    animal_tags: Optional[str] = None
    # Death-specific
    cause_of_death: Optional[str] = None
    disease_id: Optional[int] = None  # If cause is "disease"
    days_sick: Optional[int] = None
    attending_vet: Optional[str] = None
    # Abortion-specific
    abortion_stage: Optional[AbortionStage] = None  # early, mid, late
    # Birth-specific
    mother_tag: Optional[str] = None
    offspring_tags: Optional[str] = None
    # Sale-specific
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_address: Optional[str] = None
    sale_price: Optional[int] = None
    # Set when the tag in animal_tags (death/sold) or mother_tag (birth) was picked via
    # RegistryTagPicker, carrying that tag's status at selection time. Not persisted on
    # Event — consumed only to build a registry_sync_outbox row for this event.
    registry_previous_status: Optional[str] = None

class EventUpdate(BaseModel):
    event_type: Optional[EventType] = None
    species: Optional[SpeciesType] = None
    category_id: Optional[int] = None
    count: Optional[int] = None
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    from_category_id: Optional[int] = None
    to_category_id: Optional[int] = None
    notes: Optional[str] = None
    animal_tags: Optional[str] = None
    cause_of_death: Optional[str] = None
    disease_id: Optional[int] = None
    days_sick: Optional[int] = None
    attending_vet: Optional[str] = None
    abortion_stage: Optional[AbortionStage] = None
    mother_tag: Optional[str] = None
    offspring_tags: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_address: Optional[str] = None
    sale_price: Optional[int] = None
    gift_party_name: Optional[str] = None
    gift_party_phone: Optional[str] = None
    gift_reason: Optional[str] = None
    # Set when animal_tags (death/sold) or mother_tag (birth) was (re)picked via
    # RegistryTagPicker during an edit — see EventCreate.registry_previous_status.
    registry_previous_status: Optional[str] = None

class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: EventType
    species: SpeciesType
    category_id: Optional[int]
    count: int
    from_location_id: Optional[int]
    to_location_id: Optional[int]
    from_category_id: Optional[int]
    to_category_id: Optional[int]
    notes: Optional[str]
    is_stock_event: bool
    created_at: datetime
    category_name_sw: Optional[str] = None
    from_category_name_sw: Optional[str] = None
    to_category_name_sw: Optional[str] = None
    from_location_name: Optional[str] = None
    to_location_name: Optional[str] = None
    # Additional fields
    animal_tags: Optional[str] = None
    cause_of_death: Optional[str] = None
    disease_id: Optional[int] = None
    disease_name: Optional[str] = None
    days_sick: Optional[int] = None
    attending_vet: Optional[str] = None
    abortion_stage: Optional[AbortionStage] = None
    mother_tag: Optional[str] = None
    offspring_tags: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_address: Optional[str] = None
    sale_price: Optional[int] = None
    gift_party_name: Optional[str] = None
    gift_party_phone: Optional[str] = None
    gift_reason: Optional[str] = None
    # Non-blocking warning when this event's registry_sync_outbox row came back CONFLICT —
    # the event was still saved locally; see registry_sync.conflict_warning_message.
    registry_sync_warning: Optional[str] = None

# Daily Log schemas
class DailyLogCreate(BaseModel):
    location_id: int
    log_date: date
    has_events: bool = False
    notes: Optional[str] = None
    events: List[EventCreate] = []

class DailyLogUpdate(BaseModel):
    location_id: Optional[int] = None
    log_date: Optional[date] = None
    notes: Optional[str] = None

class DailyLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    log_date: date
    has_events: bool
    notes: Optional[str]
    is_locked: bool
    created_at: datetime
    location_name: Optional[str] = None
    events: List[EventResponse] = []

# Stock Level schemas
class StockLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    species: SpeciesType
    category_id: int
    current_count: int
    last_updated: datetime
    location_name: Optional[str] = None
    category_name_sw: Optional[str] = None

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

# Animal schemas
class AnimalCreate(BaseModel):
    tag_number: str
    name: Optional[str] = None
    species: SpeciesType
    category_id: int
    location_id: int
    sex: AnimalSex
    birth_date: Optional[date] = None
    mother_tag: Optional[str] = None
    father_tag: Optional[str] = None
    acquisition_type: AnimalAcquisitionType
    acquisition_date: date
    notes: Optional[str] = None

class AnimalUpdate(BaseModel):
    tag_number: Optional[str] = None
    name: Optional[str] = None
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    sex: Optional[AnimalSex] = None
    birth_date: Optional[date] = None
    mother_tag: Optional[str] = None
    father_tag: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[AnimalStatus] = None

class AnimalTransfer(BaseModel):
    to_location_id: int
    transfer_date: date
    notes: Optional[str] = None

class AnimalAssignRegistryTag(BaseModel):
    tag_id: str

class AnimalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tag_number: str
    name: Optional[str]
    species: SpeciesType
    category_id: int
    location_id: int
    sex: AnimalSex
    birth_date: Optional[date]
    mother_tag: Optional[str]
    father_tag: Optional[str]
    acquisition_type: AnimalAcquisitionType
    acquisition_date: date
    status: AnimalStatus
    status_changed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    category_name_sw: Optional[str] = None
    category_name_en: Optional[str] = None
    location_name: Optional[str] = None
    created_by_name: Optional[str] = None
    registry_tag_id: Optional[str] = None
    registry_sync_warning: Optional[str] = None

class UntaggedCalfResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tag_number: str
    name: Optional[str]
    species: SpeciesType
    birth_date: Optional[date]
    days_since_birth: Optional[int] = None
    category_name_sw: Optional[str] = None
    location_name: Optional[str] = None

class BulkImportResult(BaseModel):
    created: int
    skipped: int
    errors: List[str]
    message: str


# Health Interval schemas
class HealthIntervalCreate(BaseModel):
    location_id: int
    species: SpeciesType
    event_type: HealthEventType
    interval_days: int
    notes: Optional[str] = None

class HealthIntervalUpdate(BaseModel):
    interval_days: Optional[int] = None
    notes: Optional[str] = None

class HealthIntervalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    species: SpeciesType
    event_type: HealthEventType
    interval_days: int
    notes: Optional[str]
    location_name: Optional[str] = None


# Farm Health Event schemas
class CategoryInfo(BaseModel):
    id: int
    name_sw: str
    name_en: str

class FarmHealthEventCreate(BaseModel):
    location_id: int
    event_type: HealthEventType
    event_date: date
    species: Optional[SpeciesType] = None
    category_scope: Optional[CategoryScope] = None
    category_ids: Optional[List[int]] = None
    product_name: Optional[str] = None
    dosage: Optional[str] = None
    cost_per_head: Optional[float] = None
    total_cost: Optional[float] = None
    head_count: Optional[int] = None
    notes: Optional[str] = None
    vaccine_type_id: Optional[int] = None
    next_due_date: Optional[date] = None

class FarmHealthEventUpdate(BaseModel):
    event_date: Optional[date] = None
    species: Optional[SpeciesType] = None
    category_scope: Optional[CategoryScope] = None
    category_ids: Optional[List[int]] = None
    product_name: Optional[str] = None
    dosage: Optional[str] = None
    cost_per_head: Optional[float] = None
    total_cost: Optional[float] = None
    head_count: Optional[int] = None
    notes: Optional[str] = None
    vaccine_type_id: Optional[int] = None
    next_due_date: Optional[date] = None

class FarmHealthEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    event_type: HealthEventType
    event_date: date
    species: Optional[SpeciesType]
    category_scope: Optional[CategoryScope]
    category_ids: Optional[List[int]]
    product_name: Optional[str]
    dosage: Optional[str]
    cost_per_head: Optional[float]
    total_cost: Optional[float]
    head_count: Optional[int]
    next_due_date: Optional[date]
    notes: Optional[str]
    created_at: datetime
    location_name: Optional[str] = None
    resolved_categories: Optional[List[CategoryInfo]] = None
    created_by_name: Optional[str] = None
    vaccine_type_id: Optional[int] = None
    vaccine_type_name: Optional[str] = None

class LastEventSummary(BaseModel):
    location_id: int
    location_name: str
    species: Optional[SpeciesType]
    event_type: HealthEventType
    last_date: Optional[date]
    next_due_date: Optional[date]
    is_overdue: bool
    days_overdue: Optional[int]


# Vaccine Type schemas
class VaccineTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    species_applicability: Optional[List[str]] = None
    default_interval_days: Optional[int] = None

class VaccineTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    species_applicability: Optional[List[str]] = None
    default_interval_days: Optional[int] = None
    is_active: Optional[bool] = None

class VaccineTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str]
    species_applicability: Optional[List[str]]
    default_interval_days: Optional[int]
    is_active: bool


class LastVaccinationSummary(BaseModel):
    location_id: int
    location_name: str
    species: SpeciesType
    vaccine_type_id: int
    vaccine_type_name: str
    last_event_date: Optional[date]
    days_since: Optional[int]
    next_due_date: Optional[date]
    is_overdue: bool


# Registry sync schemas
class SyncDrainResult(BaseModel):
    processed: int
    sent: int
    conflict: int
    failed: int
    pending: int

class OutboxIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_event_id: str
    tag_id: str
    action: RegistrySyncAction
    intended_status: Optional[str]
    previous_status: Optional[str]
    state: RegistrySyncState
    attempts: int
    last_error: Optional[str]
    created_at: datetime
    sent_at: Optional[datetime]

class ReconcileMismatchResponse(BaseModel):
    tag_id: str
    kind: str
    detail: str
    local_status: Optional[str] = None
    registry_status: Optional[str] = None

class SyncReportResponse(BaseModel):
    since: date
    generated_at: datetime
    outbox_issues: List[OutboxIssueResponse]
    reconcile_mismatches: List[ReconcileMismatchResponse]
    reconcile_unavailable: bool
    reconcile_error: Optional[str] = None
