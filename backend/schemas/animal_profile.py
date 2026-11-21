"""Animal profile extras: photos, notes, timelines."""
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import date, datetime

from models import EventType, NoteType


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
