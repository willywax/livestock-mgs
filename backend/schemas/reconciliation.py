"""Physical tag reconciliation session schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from datetime import date, datetime

from models import AnimalIdentifierType, ReconciliationInputType, SpeciesType


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
