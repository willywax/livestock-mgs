"""Customers, sale details and sales report schemas."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

from models import CustomerType, SpeciesType


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    location: Optional[str] = Field(default=None, max_length=200)
    customer_type: CustomerType = CustomerType.INDIVIDUAL
    notes: Optional[str] = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Customer name cannot be blank")
        return value.strip()


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    location: Optional[str] = Field(default=None, max_length=200)
    customer_type: Optional[CustomerType] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name", "customer_type", "is_active")
    @classmethod
    def nonnull_fields(cls, value, info):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("This field cannot be null or blank")
        return value.strip() if info.field_name == "name" else value


class CustomerResponse(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class SaleDetailCreate(BaseModel):
    customer_id: Optional[int] = None
    price_per_head: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    total_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: Optional[str] = None


class SaleDetailResponse(SaleDetailCreate):
    id: int
    event_id: int
    customer_name: Optional[str]
    created_at: datetime


class SalesLineItem(BaseModel):
    date: date
    farm: str
    species: SpeciesType
    category: Optional[str]
    qty: int
    price_per_head: Optional[Decimal]
    total_price: Optional[Decimal]
    customer_name: Optional[str]
    event_id: int


class SalesSummary(BaseModel):
    total_revenue: Decimal
    total_head: int
    avg_price_per_head: Decimal
    period: dict[str, date]


class SalesPeriodBucket(BaseModel):
    month: str
    revenue: Decimal
    head_count: int


class SalesReportResponse(BaseModel):
    summary: SalesSummary
    by_period: List[SalesPeriodBucket]
    line_items: List[SalesLineItem]


class CustomerDetailResponse(CustomerResponse):
    purchases: List[SalesLineItem]
