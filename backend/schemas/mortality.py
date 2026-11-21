"""Death causes, mortality thresholds and mortality report schemas."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from models import SpeciesType


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
