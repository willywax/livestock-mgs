"""Individual animal register: animals, location history, photos, notes, identifiers, category transitions."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Enum as SQLEnum, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Base
from models.enums import AnimalAcquisitionType, AnimalIdentifierType, AnimalSex, AnimalStatus, NoteType, SpeciesType, TransitionTriggerType


class Animal(Base):
    """Individual animal registry with tag-level tracking"""
    __tablename__ = "animals"

    id = Column(Integer, primary_key=True, index=True)
    tag_number = Column(String(100), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    species = Column(SQLEnum(SpeciesType), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    sex = Column(SQLEnum(AnimalSex), nullable=False)
    birth_date = Column(Date, nullable=True)
    mother_tag = Column(String(100), nullable=True)
    father_tag = Column(String(100), nullable=True)
    acquisition_type = Column(SQLEnum(AnimalAcquisitionType), nullable=False)
    acquisition_date = Column(Date, nullable=False)
    status = Column(SQLEnum(AnimalStatus), default=AnimalStatus.ACTIVE, nullable=False)
    status_changed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    registry_tag_id = Column(String(100), nullable=True, index=True)
    is_temp_tag = Column(Boolean, default=False, nullable=False, server_default='false')
    reproductive_status = Column(String(20), default="unknown", server_default="unknown", nullable=True)
    last_calving_date = Column(Date, nullable=True)
    last_pd_date = Column(Date, nullable=True)
    months_pregnant = Column(Integer, nullable=True)
    services_without_conception = Column(Integer, default=0, server_default="0", nullable=True)
    lifetime_calvings = Column(Integer, nullable=True)  # derived count; backfilled from reproductive_cycles
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    category = relationship("Category")
    location = relationship("Location")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint('tag_number', 'species', 'location_id', name='uq_animal_tag'),
        Index('ix_animals_location_id', 'location_id'),
        Index('ix_animals_category_id', 'category_id'),
        Index('ix_animals_reproductive_status', 'reproductive_status'),
        Index('ix_animals_birth_date', 'birth_date'),
        Index('ix_animals_species_category_status', 'species', 'category_id', 'status'),
        Index('ix_animals_location_status', 'location_id', 'status'),
    )


class AnimalPhoto(Base):
    """Metadata for a photo stored in Google Cloud Storage (object path only, never a URL)."""
    __tablename__ = "animal_photos"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    gcs_path = Column(String(500), nullable=False)
    caption = Column(String(255), nullable=True)
    taken_date = Column(Date, nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    animal = relationship("Animal")


class AnimalNote(Base):
    """Free-text profile note on an animal (observation, weight, incident...)."""
    __tablename__ = "animal_notes"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    note_date = Column(Date, nullable=False)
    note_type = Column(SQLEnum(NoteType), default=NoteType.OBSERVATION, nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    animal = relationship("Animal")


class AnimalLocationHistory(Base):
    """Append-only log of animal location moves (event-driven or manual)."""
    __tablename__ = "animal_location_history"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    from_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)  # null = first recorded location
    to_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    moved_date = Column(Date, nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=True, index=True)  # null for manual moves
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    animal = relationship("Animal")
    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])


class AnimalIdentifier(Base):
    __tablename__ = "animal_identifiers"
    __table_args__ = (
        UniqueConstraint("animal_id", "id_type", "id_value"),
        Index('ix_animal_identifiers_id_value', 'id_value'),
        Index('ix_animal_identifiers_type_value', 'id_type', 'id_value'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    id_type = Column(SQLEnum(AnimalIdentifierType), nullable=False)
    id_value = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    recorded_date = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CategoryTransitionRule(Base):
    __tablename__ = "category_transition_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    species = Column(SQLEnum(SpeciesType), nullable=False)
    from_category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    to_category_id_f = Column(Integer, ForeignKey("categories.id"), nullable=True)  # target for females
    to_category_id_m = Column(Integer, ForeignKey("categories.id"), nullable=True)  # target for males
    trigger_type = Column(SQLEnum(TransitionTriggerType), nullable=False)
    trigger_age_months = Column(Integer, nullable=True)
    trigger_event = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)

    __table_args__ = (UniqueConstraint('species', 'from_category_id', 'trigger_type', name='uq_transition_rule'),)


class CategoryTransition(Base):
    """Audit log: one row per confirmed category change of an animal."""
    __tablename__ = "category_transitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("category_transition_rules.id"), nullable=True)
    from_category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    to_category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    transition_date = Column(Date, nullable=False)
    trigger = Column(String(50), nullable=True)  # "age_7m", "first_calving", "manual"
    notes = Column(Text, nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index('ix_category_transitions_date', 'transition_date'),)
