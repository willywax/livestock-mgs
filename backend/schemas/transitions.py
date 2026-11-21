"""Category-transition rule, queue and confirmation schemas."""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

from models import SpeciesType


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
