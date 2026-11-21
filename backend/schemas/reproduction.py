"""Reproduction: bull assignments, cycles, BCS, analytics, reproductive events, PD import, status board."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Literal, Optional
from datetime import date, datetime

from models import AbortionStage, AnimalSex, CalvingOutcome, PDResult, ReproductiveCycleStatus, ReproductiveEventType, ServiceType, SpeciesType


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



class PDTestImportResult(BaseModel):
    matched: int
    events_created: int
    not_found: List[str]
    skipped: List[str]
    total_rows: int



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
