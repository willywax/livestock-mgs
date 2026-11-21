"""Structured mortality: death causes and alert thresholds."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Enum as SQLEnum, String, Text, func

from database import Base
from models.enums import SpeciesType


class DeathCause(Base):
    __tablename__ = "death_causes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MortalityThreshold(Base):
    __tablename__ = "mortality_thresholds"
    id = Column(Integer, primary_key=True, autoincrement=True)
    species = Column(SQLEnum(SpeciesType), nullable=False, unique=True)
    threshold = Column(Numeric(5, 2), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
