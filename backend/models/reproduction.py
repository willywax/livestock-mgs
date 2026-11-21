"""Reproduction: bull assignments, cycles, BCS records, standalone reproductive events."""
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, Enum as SQLEnum, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from database import Base
from models.enums import AbortionStage, AnimalSex, CalvingOutcome, PDResult, ReproductiveCycleStatus, ReproductiveEventType, ServiceType


class BullAssignment(Base):
    """A bull (Animal) running with a location for a period; removed_date null = still assigned."""
    __tablename__ = "bull_assignments"

    id = Column(Integer, primary_key=True, index=True)
    bull_animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    assigned_date = Column(Date, nullable=False)
    removed_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    bull = relationship("Animal", foreign_keys=[bull_animal_id])
    location = relationship("Location")

    __table_args__ = (UniqueConstraint('bull_animal_id', 'location_id', 'assigned_date', name='uq_bull_assignment'),)


class ReproductiveCycle(Base):
    """One service/pregnancy/calving cycle for a female animal."""
    __tablename__ = "reproductive_cycles"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    cycle_number = Column(Integer, nullable=False)
    bull_assignment_id = Column(Integer, ForeignKey("bull_assignments.id"), nullable=True)
    service_date = Column(Date, nullable=True)
    service_type = Column(SQLEnum(ServiceType), default=ServiceType.NATURAL, nullable=True)
    pd_check_date = Column(Date, nullable=True)
    pd_result = Column(SQLEnum(PDResult), nullable=True)
    pd_months_pregnant = Column(Integer, nullable=True)
    expected_calving_date = Column(Date, nullable=True)
    actual_calving_date = Column(Date, nullable=True)
    calving_outcome = Column(SQLEnum(CalvingOutcome), nullable=True)
    calf_sex = Column(SQLEnum(AnimalSex), nullable=True)
    calf_animal_id = Column(Integer, ForeignKey("animals.id"), nullable=True)
    abortion_stage = Column(SQLEnum(AbortionStage), nullable=True)
    bcs_at_service = Column(Numeric(3, 1), nullable=True)   # 1.0-5.0
    bcs_at_calving = Column(Numeric(3, 1), nullable=True)   # 1.0-5.0
    calving_interval_days = Column(Integer, nullable=True)  # computed on save
    days_to_service = Column(Integer, nullable=True)        # computed on save
    status = Column(SQLEnum(ReproductiveCycleStatus), default=ReproductiveCycleStatus.OPEN, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    animal = relationship("Animal", foreign_keys=[animal_id])
    bull_assignment = relationship("BullAssignment")
    calf = relationship("Animal", foreign_keys=[calf_animal_id])

    __table_args__ = (UniqueConstraint('animal_id', 'cycle_number', name='uq_repro_cycle'),)


class BCSRecord(Base):
    """Body condition score (1.0-5.0) for an animal on a date."""
    __tablename__ = "bcs_records"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    score_date = Column(Date, nullable=False)
    bcs = Column(Numeric(3, 1), nullable=False)
    scored_by = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    animal = relationship("Animal")


class ReproductiveEvent(Base):
    __tablename__ = "reproductive_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    animal_id = Column(Integer, ForeignKey("animals.id"), nullable=False, index=True)
    event_type = Column(SQLEnum(ReproductiveEventType), nullable=False)
    event_date = Column(Date, nullable=False)
    pd_result = Column(SQLEnum(PDResult), nullable=True)
    months_pregnant = Column(Integer, nullable=True)
    calving_outcome = Column(String(20), nullable=True)
    offspring_count = Column(Integer, nullable=True)
    abortion_stage = Column(SQLEnum(AbortionStage), nullable=True)
    service_type = Column(SQLEnum(ServiceType), nullable=True)
    bull_animal_id = Column(Integer, ForeignKey("animals.id"), nullable=True)
    vet = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_repro_events_event_type', 'event_type'),
        Index('ix_repro_events_event_date', 'event_date'),
        Index('ix_repro_events_animal_date', 'animal_id', 'event_date'),
    )
