"""Users, locations, categories, daily logs, events and stock levels."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, Enum as SQLEnum, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from models.enums import AbortionStage, EventType, SpeciesType, UserRole


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Location(Base):
    __tablename__ = "locations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name_sw = Column(String(100), nullable=False)  # Swahili name
    name_en = Column(String(100), nullable=False)  # English name
    species = Column(SQLEnum(SpeciesType), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    __table_args__ = (UniqueConstraint('name_sw', 'species', name='uq_category_species'),)


class OpeningBalance(Base):
    __tablename__ = "opening_balances"
    
    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    species = Column(SQLEnum(SpeciesType), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    count = Column(Integer, default=0, nullable=False)
    period_start = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    location = relationship("Location")
    category = relationship("Category")
    
    __table_args__ = (UniqueConstraint('location_id', 'species', 'category_id', 'period_start', name='uq_opening_balance'),)


class DailyLog(Base):
    __tablename__ = "daily_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    log_date = Column(Date, nullable=False)
    has_events = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    is_locked = Column(Boolean, default=False)
    locked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    location = relationship("Location")
    events = relationship("Event", back_populates="daily_log", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('location_id', 'log_date', name='uq_daily_log'),
        Index('ix_daily_logs_log_date', 'log_date'),
    )


class Disease(Base):
    """List of diseases for death cause tracking"""
    __tablename__ = "diseases"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    species = Column(SQLEnum(SpeciesType), nullable=True)  # Null means all species
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    daily_log_id = Column(Integer, ForeignKey("daily_logs.id"), nullable=False)
    event_type = Column(SQLEnum(EventType), nullable=False)
    species = Column(SQLEnum(SpeciesType), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    count = Column(Integer, default=0, nullable=False)
    # For transfers
    from_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    to_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    # For category changes
    from_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    to_category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    notes = Column(Text, nullable=True)
    is_stock_event = Column(Boolean, default=True)  # False for abortion (note only)
    
    # Animal tags (comma-separated for multiple)
    animal_tags = Column(Text, nullable=True)
    pd_result = Column(String(20), nullable=True)
    months_pregnant = Column(Integer, nullable=True)
    
    # Death-specific fields
    cause_of_death_id = Column(Integer, ForeignKey("death_causes.id"), nullable=True)
    cause_of_death = Column(String(255), nullable=True)  # "disease", "accident", "predator", etc.
    disease_id = Column(Integer, ForeignKey("diseases.id"), nullable=True)  # If cause is disease
    days_sick = Column(Integer, nullable=True)
    attending_vet = Column(String(255), nullable=True)  # DK = Doctor/Vet
    
    # Abortion-specific fields
    abortion_stage = Column(SQLEnum(AbortionStage), nullable=True)  # early, mid, late
    
    # Birth-specific fields
    mother_tag = Column(String(100), nullable=True)
    offspring_tags = Column(Text, nullable=True)  # Comma-separated
    
    # Sale-specific fields
    buyer_name = Column(String(255), nullable=True)
    buyer_phone = Column(String(50), nullable=True)
    buyer_address = Column(Text, nullable=True)
    sale_price = Column(Integer, nullable=True)  # Price per animal or total

    # Gift-specific fields (GIFT_IN / GIFT_OUT only)
    gift_party_name = Column(String(255), nullable=True)
    gift_party_phone = Column(String(50), nullable=True)
    gift_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    daily_log = relationship("DailyLog", back_populates="events")
    category = relationship("Category", foreign_keys=[category_id])
    from_category = relationship("Category", foreign_keys=[from_category_id])
    to_category = relationship("Category", foreign_keys=[to_category_id])
    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])
    disease = relationship("Disease", foreign_keys=[disease_id])

    __table_args__ = (
        Index('ix_events_daily_log_id', 'daily_log_id'),
        Index('ix_events_event_type', 'event_type'),
    )


class EventAnimalLink(Base):
    """Durable daily-log membership and replay journal; tombstones retain the baseline."""
    __tablename__ = "event_animal_links"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    tag_at_link = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source_key = Column(String(100), nullable=True)
    reproductive_payload = Column(JSON, nullable=True)
    reproductive_baseline = Column(JSON, nullable=True)
    category_transition_id = Column(Integer, ForeignKey("category_transitions.id"), nullable=True)
    __table_args__ = (
        UniqueConstraint('event_id', 'animal_id', 'role', name='uq_event_animal_role'),
        UniqueConstraint('animal_id', 'source_key', name='uq_animal_repro_source'),
    )


class StockLevel(Base):
    """Computed stock levels - updated after each event"""
    __tablename__ = "stock_levels"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    species = Column(SQLEnum(SpeciesType), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    current_count = Column(Integer, default=0, nullable=False)
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    location = relationship("Location")
    category = relationship("Category")

    __table_args__ = (UniqueConstraint('location_id', 'species', 'category_id', name='uq_stock_level'),)
