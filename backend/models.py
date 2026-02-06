from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Date, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DATA_ENTRY = "data_entry"
    VIEWER = "viewer"

class EventType(str, enum.Enum):
    BIRTH = "birth"
    DEATH = "death"
    SOLD = "sold"
    MISSING = "missing"
    GIFT_IN = "gift_in"
    GIFT_OUT = "gift_out"
    BOUGHT = "bought"
    TRANSFER = "transfer"
    CATEGORY_CHANGE = "category_change"
    ABORTION = "abortion"
    WEANING = "weaning"  # Moving calves from nursing to weaned categories

class SpeciesType(str, enum.Enum):
    CATTLE = "cattle"
    SHEEP = "sheep"
    GOAT = "goat"

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
    
    __table_args__ = (UniqueConstraint('location_id', 'log_date', name='uq_daily_log'),)

class AbortionStage(str, enum.Enum):
    EARLY = "early"      # 0-3 months
    MID = "mid"          # 3-6 months
    LATE = "late"        # 6-9 months

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
    
    # Death-specific fields
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
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    daily_log = relationship("DailyLog", back_populates="events")
    category = relationship("Category", foreign_keys=[category_id])
    from_category = relationship("Category", foreign_keys=[from_category_id])
    to_category = relationship("Category", foreign_keys=[to_category_id])
    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])
    disease = relationship("Disease", foreign_keys=[disease_id])

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
