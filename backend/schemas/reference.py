"""Locations, categories, opening balances, diseases."""
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date, datetime

from models import SpeciesType


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
