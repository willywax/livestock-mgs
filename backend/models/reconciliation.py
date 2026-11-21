"""Physical tag reconciliation sessions and entries."""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, Enum as SQLEnum, String, Text, func

from database import Base
from models.enums import AnimalIdentifierType, ReconciliationInputType


class ReconciliationSession(Base):
    __tablename__ = "reconciliation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    session_date = Column(Date, nullable=False)
    input_type = Column(SQLEnum(ReconciliationInputType), nullable=False)
    notes = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReconciliationEntry(Base):
    __tablename__ = "reconciliation_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("reconciliation_sessions.id"), nullable=False, index=True)
    raw_value = Column(String(100), nullable=False)
    id_type = Column(SQLEnum(AnimalIdentifierType), nullable=False)
    matched_animal_id = Column(Integer, ForeignKey("animals.id"), nullable=True)
    match_status = Column(String(20), nullable=False, default="unmatched_scan")

    __table_args__ = (Index('ix_recon_entries_match_status', 'match_status'),)
