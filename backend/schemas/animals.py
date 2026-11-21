"""Animal register: CRUD, import, reconciliation rows, tag replacement, identifiers, pagination."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional
from datetime import date, datetime

from models import AnimalAcquisitionType, AnimalIdentifierType, AnimalSex, AnimalStatus, SpeciesType


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



# Opt-in pagination envelopes (returned only when page/page_size is passed)
class AnimalPage(BaseModel):
    items: List[AnimalResponse]
    total: int
    page: int
    page_size: int
    pages: int
