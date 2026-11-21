"""Stock level schemas."""
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

from models import SpeciesType


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
