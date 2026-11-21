"""Farm-health scheduling: intervals, health events, vaccine types."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, Enum as SQLEnum, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from models.enums import CategoryScope, HealthEventType, SpeciesType


class HealthInterval(Base):
    """Configurable reminder intervals per location+species+event_type"""
    __tablename__ = "health_intervals"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    species = Column(SQLEnum(SpeciesType), nullable=False)
    event_type = Column(SQLEnum(HealthEventType), nullable=False)
    interval_days = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    location = relationship("Location")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (UniqueConstraint('location_id', 'species', 'event_type', name='uq_health_interval'),)


class FarmHealthEvent(Base):
    """Unified health event log: dipping, vaccination, deworming, diary entries"""
    __tablename__ = "farm_health_events"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    event_type = Column(SQLEnum(HealthEventType), nullable=False)
    event_date = Column(Date, nullable=False)
    species = Column(SQLEnum(SpeciesType), nullable=True)       # null for LOG type
    category_scope = Column(SQLEnum(CategoryScope), nullable=True)  # null for LOG type
    category_ids = Column(JSON, nullable=True)                  # list[int], null means ALL
    product_name = Column(String(255), nullable=True)           # null for LOG type
    dosage = Column(String(100), nullable=True)
    cost_per_head = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    head_count = Column(Integer, nullable=True)
    next_due_date = Column(Date, nullable=True)                 # auto-computed
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    location = relationship("Location")
    creator = relationship("User", foreign_keys=[created_by])
    vaccine_type_id = Column(Integer, ForeignKey("vaccine_types.id"), nullable=True)
    vaccine_type = relationship("VaccineType")


class VaccineType(Base):
    """Predefined vaccine types with default schedules"""
    __tablename__ = "vaccine_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    species_applicability = Column(JSON, nullable=True)   # e.g. ["CATTLE"] or null = all
    default_interval_days = Column(Integer, nullable=True)  # null = no fixed schedule
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])
