"""Farm-health intervals, events and vaccine types."""
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import date, datetime

from models import CategoryScope, HealthEventType, SpeciesType


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
