from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Optional, List, Literal
from datetime import datetime, date
from decimal import Decimal
from models import (
    UserRole, EventType, SpeciesType, AbortionStage, AnimalSex, AnimalAcquisitionType, AnimalStatus,
    HealthEventType, CategoryScope, VaccineType as VaccineTypeModel,
    ServiceType, PDResult, ReproductiveCycleStatus, CalvingOutcome, NoteType,
    AnimalIdentifierType, ReproductiveEventType, ReconciliationInputType, CustomerType,
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
    pd_result: Optional[Literal["pregnant", "open"]] = None
    months_pregnant: Optional[int] = Field(default=None, ge=0, le=12)
    # Death-specific
    cause_of_death_id: Optional[int] = None
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

    @model_validator(mode="after")
    def validate_reproductive_event(self):
        if self.event_type in (EventType.PD_TEST, EventType.SERVICE, EventType.ABORTION):
            self.is_stock_event = False
        if self.event_type == EventType.PD_TEST and self.pd_result is None:
            raise ValueError("A PD test requires result pregnant or open")
        if self.event_type != EventType.PD_TEST and (self.pd_result is not None or self.months_pregnant is not None):
            raise ValueError("PD fields only apply to a PD test")
        if self.pd_result == "open":
            self.months_pregnant = None
        return self


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
    pd_result: Optional[Literal["pregnant", "open"]] = None
    months_pregnant: Optional[int] = Field(default=None, ge=0, le=12)
    cause_of_death_id: Optional[int] = None
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
    pd_result: Optional[Literal["pregnant", "open"]] = None
    months_pregnant: Optional[int] = Field(default=None, ge=0, le=12)
    cause_of_death_id: Optional[int] = None
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
    # Non-fatal animal-register sync messages (register updates are best-effort)
    sync_warnings: Optional[List[str]] = None

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
    event_count: Optional[int] = None  # set by the list endpoint only

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
    search_tags: List[str] = Field(default_factory=list)
    is_temp_tag: bool = False
    reproductive_status: str = "unknown"
    last_calving_date: Optional[date] = None

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


# ==================== REPRODUCTION & ANIMAL PROFILE ====================
class BullAssignmentCreate(BaseModel):
    bull_animal_id: int
    location_id: int
    assigned_date: date
    removed_date: Optional[date] = None
    notes: Optional[str] = None

class BullAssignmentUpdate(BaseModel):
    location_id: Optional[int] = None
    assigned_date: Optional[date] = None
    removed_date: Optional[date] = None
    notes: Optional[str] = None

class BullAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    bull_animal_id: int
    location_id: int
    assigned_date: date
    removed_date: Optional[date]
    notes: Optional[str]
    created_at: datetime
    bull_tag_number: Optional[str] = None
    bull_name: Optional[str] = None
    location_name: Optional[str] = None

class ReproductiveCycleCreate(BaseModel):
    animal_id: int
    bull_assignment_id: Optional[int] = None
    service_date: Optional[date] = None
    service_type: ServiceType = ServiceType.NATURAL
    pd_check_date: Optional[date] = None
    pd_result: Optional[PDResult] = None
    pd_months_pregnant: Optional[int] = Field(default=None, ge=0, le=12)
    expected_calving_date: Optional[date] = None
    actual_calving_date: Optional[date] = None
    calving_outcome: Optional[CalvingOutcome] = None
    calf_sex: Optional[AnimalSex] = None
    calf_animal_id: Optional[int] = None
    abortion_stage: Optional[AbortionStage] = None
    bcs_at_service: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    bcs_at_calving: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    status: ReproductiveCycleStatus = ReproductiveCycleStatus.OPEN
    notes: Optional[str] = None

class ReproductiveCycleUpdate(BaseModel):
    # Fields present in the request (even if null) are applied; absent fields are untouched.
    bull_assignment_id: Optional[int] = None
    service_date: Optional[date] = None
    service_type: Optional[ServiceType] = None
    pd_check_date: Optional[date] = None
    pd_result: Optional[PDResult] = None
    pd_months_pregnant: Optional[int] = Field(default=None, ge=0, le=12)
    expected_calving_date: Optional[date] = None
    actual_calving_date: Optional[date] = None
    calving_outcome: Optional[CalvingOutcome] = None
    calf_sex: Optional[AnimalSex] = None
    calf_animal_id: Optional[int] = None
    abortion_stage: Optional[AbortionStage] = None
    bcs_at_service: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    bcs_at_calving: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    status: Optional[ReproductiveCycleStatus] = None
    notes: Optional[str] = None

class ReproductiveCycleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    animal_id: int
    cycle_number: int
    bull_assignment_id: Optional[int]
    service_date: Optional[date]
    service_type: Optional[ServiceType]
    pd_check_date: Optional[date]
    pd_result: Optional[PDResult]
    pd_months_pregnant: Optional[int]
    expected_calving_date: Optional[date]
    actual_calving_date: Optional[date]
    calving_outcome: Optional[CalvingOutcome]
    calf_sex: Optional[AnimalSex]
    calf_animal_id: Optional[int]
    abortion_stage: Optional[AbortionStage]
    bcs_at_service: Optional[float]
    bcs_at_calving: Optional[float]
    calving_interval_days: Optional[int]
    days_to_service: Optional[int]
    status: ReproductiveCycleStatus
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None
    animal_tag_number: Optional[str] = None
    location_name: Optional[str] = None
    bull_tag_number: Optional[str] = None

class AnimalReproductiveSummary(BaseModel):
    animal_id: int
    tag_number: str
    total_calvings: int
    avg_interval_days: Optional[float] = None
    last_calving_date: Optional[date] = None
    current_status: Optional[ReproductiveCycleStatus] = None
    cycles: List[ReproductiveCycleResponse] = []

class BCSRecordCreate(BaseModel):
    animal_id: int
    score_date: date
    bcs: float = Field(ge=1.0, le=5.0)
    scored_by: Optional[str] = None
    notes: Optional[str] = None

class BCSRecordUpdate(BaseModel):
    score_date: Optional[date] = None
    bcs: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    scored_by: Optional[str] = None
    notes: Optional[str] = None

class BCSRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    animal_id: int
    score_date: date
    bcs: float
    scored_by: Optional[str]
    notes: Optional[str]
    created_at: datetime
    animal_tag_number: Optional[str] = None

class AnimalPhotoCreate(BaseModel):
    # Non-file form fields of the multipart upload.
    caption: Optional[str] = Field(default=None, max_length=255)
    taken_date: Optional[date] = None

class AnimalPhotoUpdate(BaseModel):
    caption: Optional[str] = Field(default=None, max_length=255)
    taken_date: Optional[date] = None
    is_primary: Optional[bool] = None

class AnimalPhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    animal_id: int
    gcs_path: str
    caption: Optional[str]
    taken_date: Optional[date]
    is_primary: bool
    uploaded_at: datetime
    photo_url: Optional[str] = None
    warning: Optional[str] = None

class AnimalNoteCreate(BaseModel):
    note_date: date
    note_type: NoteType = NoteType.OBSERVATION
    content: str = Field(min_length=1)

class AnimalNoteUpdate(BaseModel):
    note_date: Optional[date] = None
    note_type: Optional[NoteType] = None
    content: Optional[str] = Field(default=None, min_length=1)

class AnimalNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    animal_id: int
    note_date: date
    note_type: NoteType
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None

class TimelineItem(BaseModel):
    date: date
    event_category: str  # REPRODUCTION | HEALTH | BCS | NOTE
    title: str
    detail: Optional[str] = None
    source_table: str
    source_id: int

class ReproductionMetrics(BaseModel):
    # Rates are fractions in 0-1 (None when the denominator is 0).
    koo_count: int = 0
    live_calvings: int = 0
    calving_rate: Optional[float] = None
    conception_rate: Optional[float] = None
    abortion_rate: Optional[float] = None
    avg_calving_interval_days: Optional[float] = None
    open_cows: int = 0
    pregnant_cows: int = 0
    bcs_distribution: dict = {}

class LocationReproductionMetrics(ReproductionMetrics):
    location_id: int
    location_name: str

class ReproductionAnalyticsResponse(ReproductionMetrics):
    year: int
    location_id: Optional[int] = None
    by_location: List[LocationReproductionMetrics] = []


# Animal register: location history + reconciliation
class AnimalLocationHistoryResponse(BaseModel):
    id: int
    animal_id: int
    from_location_id: Optional[int] = None
    from_location_name: Optional[str] = None
    to_location_id: int
    to_location_name: Optional[str] = None
    moved_date: date
    event_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

class ReconciliationRow(BaseModel):
    location_id: int
    location_name: str
    species: SpeciesType
    stock_count: int
    registered_active: int
    registered_pct: Optional[float] = None
    unregistered: int

ReconciliationResponse = List[ReconciliationRow]


# Temporary tags for untagged newborns
class ReplaceTagRequest(BaseModel):
    new_tag_number: str = Field(min_length=1)

class ReplaceTagResponse(BaseModel):
    message: str
    old_tag: str
    new_tag: str
    animal_id: int


class AnimalIdentifierCreate(BaseModel):
    id_type: AnimalIdentifierType
    id_value: str = Field(min_length=1, max_length=100)
    is_active: bool = True
    notes: Optional[str] = None
    recorded_date: Optional[date] = None


class AnimalIdentifierUpdate(BaseModel):
    id_value: Optional[str] = Field(default=None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    recorded_date: Optional[date] = None

    @field_validator("id_value", "is_active")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class AnimalIdentifierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    animal_id: int
    id_type: AnimalIdentifierType
    id_value: str
    is_active: bool
    notes: Optional[str]
    recorded_date: Optional[date]
    created_at: datetime


class AnimalLookupResponse(BaseModel):
    animal: AnimalResponse
    matched_id: AnimalIdentifierResponse


class AnimalIdentifierImportResult(BaseModel):
    matched: int
    identifiers_added: int
    already_existed: int
    repro_fields_updated: int = 0
    unmatched_eids: List[str]


class ReproductiveEventCreate(BaseModel):
    event_type: ReproductiveEventType
    event_date: date
    pd_result: Optional[Literal["pregnant", "open", "recheck"]] = None
    months_pregnant: Optional[int] = Field(default=None, ge=0)
    calving_outcome: Optional[Literal["live", "stillbirth"]] = None
    offspring_count: Optional[int] = Field(default=None, ge=0)
    abortion_stage: Optional[AbortionStage] = None
    service_type: Optional[ServiceType] = None
    bull_animal_id: Optional[int] = None
    vet: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class ReproductiveEventResponse(ReproductiveEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    animal_id: int
    recorded_by: Optional[int]
    recorded_at: datetime

    @field_validator("pd_result", mode="before")
    @classmethod
    def expose_recheck(cls, value):
        return "recheck" if value == PDResult.REPEAT else value


class ReproductiveSummaryResponse(BaseModel):
    status: str
    last_calving_date: Optional[date]
    last_pd_date: Optional[date]
    months_pregnant: Optional[int]
    services_without_conception: int
    is_repeat_breeder: bool
    events: List[ReproductiveEventResponse]


class ReconciliationEntryInput(BaseModel):
    raw_value: str = Field(min_length=1, max_length=100)
    id_type: AnimalIdentifierType

    @field_validator("raw_value")
    @classmethod
    def nonblank_value(cls, value):
        if not value.strip():
            raise ValueError("Tag value cannot be blank")
        return value


class ReconciliationSessionCreate(BaseModel):
    location_id: int
    session_date: date
    input_type: ReconciliationInputType
    notes: Optional[str] = None
    entries: List[ReconciliationEntryInput]

    @field_validator("entries")
    @classmethod
    def valid_entry_types(cls, entries, info):
        allowed = {
            ReconciliationInputType.RFID: {AnimalIdentifierType.EID, AnimalIdentifierType.READER_CODE},
            ReconciliationInputType.VISUAL: {AnimalIdentifierType.VISUAL_TAG},
            ReconciliationInputType.MIXED: {
                AnimalIdentifierType.EID, AnimalIdentifierType.READER_CODE, AnimalIdentifierType.VISUAL_TAG,
            },
        }.get(info.data.get("input_type"), set())
        if any(entry.id_type not in allowed for entry in entries):
            raise ValueError("Identifier type is not permitted for this session input type")
        return entries


class ReconciliationMatchedAnimal(BaseModel):
    animal_id: int
    tag_number: str
    species: SpeciesType
    matched_via: Literal["identifier", "tag_number"]


class ReconciliationUnmatchedScan(BaseModel):
    raw_value: str
    id_type: AnimalIdentifierType


class ReconciliationMissingAnimal(BaseModel):
    animal_id: int
    tag_number: str
    species: SpeciesType
    category: str


class ReconciliationResultResponse(BaseModel):
    session_id: int
    location_name: str
    session_date: date
    input_type: ReconciliationInputType
    total_scanned: int
    matched: List[ReconciliationMatchedAnimal]
    unmatched_scan: List[ReconciliationUnmatchedScan]
    in_system_not_seen: List[ReconciliationMissingAnimal]
    matched_count: int
    unmatched_scan_count: int
    in_system_not_seen_count: int
    coverage_pct: float


class ReconciliationSessionSummary(BaseModel):
    id: int
    location_name: str
    session_date: date
    input_type: ReconciliationInputType
    total_scanned: int
    matched_count: int
    unmatched_scan_count: int
    in_system_not_seen_count: int
    coverage_pct: float
    created_at: datetime


class PDTestImportResult(BaseModel):
    matched: int
    events_created: int
    not_found: List[str]
    skipped: List[str]
    total_rows: int


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    location: Optional[str] = Field(default=None, max_length=200)
    customer_type: CustomerType = CustomerType.INDIVIDUAL
    notes: Optional[str] = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Customer name cannot be blank")
        return value.strip()


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    location: Optional[str] = Field(default=None, max_length=200)
    customer_type: Optional[CustomerType] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name", "customer_type", "is_active")
    @classmethod
    def nonnull_fields(cls, value, info):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("This field cannot be null or blank")
        return value.strip() if info.field_name == "name" else value


class CustomerResponse(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class SaleDetailCreate(BaseModel):
    customer_id: Optional[int] = None
    price_per_head: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    total_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: Optional[str] = None


class SaleDetailResponse(SaleDetailCreate):
    id: int
    event_id: int
    customer_name: Optional[str]
    created_at: datetime


class SalesLineItem(BaseModel):
    date: date
    farm: str
    species: SpeciesType
    category: Optional[str]
    qty: int
    price_per_head: Optional[Decimal]
    total_price: Optional[Decimal]
    customer_name: Optional[str]
    event_id: int


class SalesSummary(BaseModel):
    total_revenue: Decimal
    total_head: int
    avg_price_per_head: Decimal
    period: dict[str, date]


class SalesPeriodBucket(BaseModel):
    month: str
    revenue: Decimal
    head_count: int


class SalesReportResponse(BaseModel):
    summary: SalesSummary
    by_period: List[SalesPeriodBucket]
    line_items: List[SalesLineItem]


class CustomerDetailResponse(CustomerResponse):
    purchases: List[SalesLineItem]


class DeathCauseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class DeathCauseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("name", "sort_order", "is_active")
    @classmethod
    def validate_nonnull(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Field cannot be null or blank")
        return value.strip() if isinstance(value, str) else value


class DeathCauseResponse(DeathCauseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: datetime


class MortalityThresholdUpdate(BaseModel):
    species: SpeciesType
    threshold: Decimal = Field(ge=0, max_digits=5, decimal_places=2)


class MortalityThresholdResponse(MortalityThresholdUpdate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_by: Optional[int]
    updated_at: datetime


class MortalityBySpecies(BaseModel):
    species: SpeciesType
    deaths: int
    avg_stock: float
    mortality_rate_pct: Optional[float]
    threshold_pct: Optional[float]
    is_alert: bool


class MortalityByFarm(MortalityBySpecies):
    farm: str
    location_id: int


class MortalityByCause(BaseModel):
    cause_name: str
    count: int
    pct_of_total: float


class MortalityByMonth(BaseModel):
    month: str
    deaths: int
    by_species: dict[str, int]


class MortalityReportResponse(BaseModel):
    summary: dict
    by_species: List[MortalityBySpecies]
    by_farm: List[MortalityByFarm]
    by_cause: List[MortalityByCause]
    by_month: List[MortalityByMonth]
    flagged: List[MortalityByFarm]


class StatusBoardAnimal(BaseModel):
    id: int
    tag_number: str
    species: SpeciesType
    category: str
    farm: str
    age_months: Optional[int]
    reproductive_status: str
    last_event_date: Optional[date]
    last_event_type: Optional[ReproductiveEventType]
    last_pd_date: Optional[date]
    last_calving_date: Optional[date]
    months_pregnant: Optional[int]
    services_without_conception: int
    expected_calving_date: Optional[date]


class StatusBoardBucket(BaseModel):
    label: str
    count: int
    animals: List[StatusBoardAnimal]


class StatusBoardSummary(BaseModel):
    total_breeding_females: int
    status_known_pct: float


class ReproductiveStatusBoardResponse(BaseModel):
    summary: StatusBoardSummary
    open: StatusBoardBucket
    pregnant: StatusBoardBucket
    close_to_calving: StatusBoardBucket
    due_this_month: StatusBoardBucket
    recently_calved: StatusBoardBucket
    recently_aborted: StatusBoardBucket
    repeat_breeders: StatusBoardBucket
    unknown_status: StatusBoardBucket
    needs_attention: StatusBoardBucket


# ---------- Category transitions ----------
class CategoryTransitionRuleResponse(BaseModel):
    id: int
    species: SpeciesType
    from_category_id: int
    from_category_name: str
    to_category_id_f: Optional[int] = None
    to_category_name_f: Optional[str] = None
    to_category_id_m: Optional[int] = None
    to_category_name_m: Optional[str] = None
    trigger_type: str
    trigger_age_months: Optional[int] = None
    trigger_event: Optional[str] = None
    is_active: bool
    notes: Optional[str] = None


class CategoryTransitionRuleUpdate(BaseModel):
    trigger_age_months: Optional[int] = Field(default=None, ge=1, le=240)
    to_category_id_f: Optional[int] = None
    to_category_id_m: Optional[int] = None
    is_active: Optional[bool] = None


class TransitionQueueItem(BaseModel):
    animal_id: int
    tag_number: str
    species: SpeciesType
    current_category: str
    to_category_id: int
    to_category: str  # the female or male target, by the animal's sex
    age_months: int
    location_name: Optional[str] = None
    rule_id: int
    trigger: str


class TransitionQueueResponse(BaseModel):
    pending: List[TransitionQueueItem]
    total: int


class ConfirmTransitionRequest(BaseModel):
    to_category_id: int
    notes: Optional[str] = None


class BulkTransitionItem(BaseModel):
    animal_id: int
    to_category_id: int


class BulkConfirmRequest(BaseModel):
    transitions: List[BulkTransitionItem] = Field(min_length=1, max_length=200)
    notes: Optional[str] = None


class CategoryTransitionResponse(BaseModel):
    id: int
    animal_id: int
    tag_number: str
    from_category: str
    to_category: str
    transition_date: date
    trigger: Optional[str] = None
    notes: Optional[str] = None
    confirmed_by_name: Optional[str] = None


class BulkConfirmResult(BaseModel):
    animal_id: int
    success: bool
    transition: Optional[CategoryTransitionResponse] = None
    error: Optional[str] = None


class BulkConfirmResponse(BaseModel):
    results: List[BulkConfirmResult]
    succeeded: int
    failed: int


# Opt-in pagination envelopes (returned only when page/page_size is passed)
class AnimalPage(BaseModel):
    items: List[AnimalResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DailyLogPage(BaseModel):
    items: List[DailyLogResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AnimalTimelineItem(BaseModel):
    event_id: int
    event_type: EventType
    event_date: date
    event_type_label: str
    daily_log_id: int
    farm_name: str
    notes: Optional[str]
    quantity: int
    result: Optional[str]
    recorded_by_name: Optional[str]


class AnimalTimelineResponse(BaseModel):
    items: List[AnimalTimelineItem]
    total: int
    page: int
    page_size: int
