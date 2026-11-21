"""Events and daily logs (create/update/response, pagination)."""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import List, Literal, Optional
from datetime import date, datetime

from models import AbortionStage, EventType, SpeciesType


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


class DailyLogPage(BaseModel):
    items: List[DailyLogResponse]
    total: int
    page: int
    page_size: int
    pages: int
