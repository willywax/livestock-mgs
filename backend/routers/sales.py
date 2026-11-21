"""Customers, sale details and the sales report."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Category, Customer, DailyLog, Event, EventType, Location, SaleDetail, SpeciesType, User, UserRole
from schemas import CustomerCreate, CustomerDetailResponse, CustomerResponse, CustomerUpdate, SaleDetailCreate, SaleDetailResponse, SalesLineItem, SalesReportResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import _ANY_ROLE

router = APIRouter()

# ---------- Customers and sale details ----------
async def _sales_customer(db, customer_id):
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


async def _sales_line_items(db, date_from=None, date_to=None, location_id=None,
                            species=None, customer_id=None):
    query = (select(Event, DailyLog.log_date, Location.name, Category.name_sw,
                    SaleDetail, Customer.name)
             .join(DailyLog, Event.daily_log_id == DailyLog.id)
             .join(Location, DailyLog.location_id == Location.id)
             .outerjoin(Category, Event.category_id == Category.id)
             .join(SaleDetail, SaleDetail.event_id == Event.id)
             .outerjoin(Customer, SaleDetail.customer_id == Customer.id)
             .where(Event.event_type == EventType.SOLD))
    if date_from is not None:
        query = query.where(DailyLog.log_date >= date_from)
    if date_to is not None:
        query = query.where(DailyLog.log_date <= date_to)
    if location_id is not None:
        query = query.where(DailyLog.location_id == location_id)
    if species is not None:
        query = query.where(Event.species == species)
    if customer_id is not None:
        query = query.where(SaleDetail.customer_id == customer_id)
    rows = (await db.execute(query.order_by(DailyLog.log_date.desc(), Event.id.desc()))).all()
    return [SalesLineItem(date=day, farm=farm, species=event.species, category=category,
                          qty=event.count, price_per_head=detail.price_per_head,
                          total_price=detail.total_price, customer_name=customer_name,
                          event_id=event.id)
            for event, day, farm, category, detail, customer_name in rows]


@router.get("/customers", response_model=List[CustomerResponse])
async def list_customers(
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    query = select(Customer)
    if is_active is not None:
        query = query.where(Customer.is_active == is_active)
    if search:
        query = query.where(func.lower(Customer.name).contains(search.strip().lower(), autoescape=True))
    return (await db.execute(query.order_by(Customer.name, Customer.id))).scalars().all()


@router.post("/customers", response_model=CustomerResponse)
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    customer = Customer(**data.model_dump(), created_by=current_user.id)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerDetailResponse)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    customer = await _sales_customer(db, customer_id)
    return CustomerDetailResponse(
        **CustomerResponse.model_validate(customer).model_dump(),
        purchases=await _sales_line_items(db, customer_id=customer_id),
    )


@router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    customer = await _sales_customer(db, customer_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, key, value)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.delete("/customers/{customer_id}")
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    customer = await _sales_customer(db, customer_id)
    customer.is_active = False
    await db.commit()
    return {"message": "Customer deactivated"}


@router.get("/customers/{customer_id}/purchases", response_model=List[SalesLineItem])
async def customer_purchases(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _sales_customer(db, customer_id)
    return await _sales_line_items(db, customer_id=customer_id)


async def _sale_event(db, event_id, lock=False):
    query = select(Event).where(Event.id == event_id)
    if lock:
        query = query.with_for_update()
    event = (await db.execute(query)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.event_type != EventType.SOLD:
        raise HTTPException(status_code=400, detail="Sale details require a SOLD event")
    return event


async def _sale_detail_response(db, detail):
    customer = await db.get(Customer, detail.customer_id) if detail.customer_id is not None else None
    return SaleDetailResponse(
        id=detail.id, event_id=detail.event_id, customer_id=detail.customer_id,
        customer_name=customer.name if customer else None, price_per_head=detail.price_per_head,
        total_price=detail.total_price, notes=detail.notes, created_at=detail.created_at,
    )


@router.post("/events/{event_id}/sale-detail", response_model=SaleDetailResponse)
async def save_sale_detail(
    event_id: int,
    data: SaleDetailCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    try:
        # Lock the existing event to serialize concurrent upserts for this sale.
        event = await _sale_event(db, event_id, lock=True)
        values = data.model_dump(exclude_unset=True)
        if data.customer_id is not None:
            await _sales_customer(db, data.customer_id)
        detail = (await db.execute(select(SaleDetail).where(SaleDetail.event_id == event_id))).scalar_one_or_none()
        new = detail is None
        if new:
            detail = SaleDetail(event_id=event_id, recorded_by=current_user.id)
        for key, value in values.items():
            setattr(detail, key, value)
        # A supplied non-null total wins. Notes/customer-only updates preserve the
        # saved total; a new price or an explicit null total requests calculation.
        if data.total_price is None and (new or "price_per_head" in values or "total_price" in values):
            detail.total_price = (detail.price_per_head * event.count
                                  if detail.price_per_head is not None else None)
        if detail.total_price is not None and not Decimal("0") <= detail.total_price <= Decimal("9999999999.99"):
            raise HTTPException(status_code=400, detail="Computed total is outside the supported price range")
        db.add(detail)
        await db.flush()
        await db.refresh(detail)
        response = await _sale_detail_response(db, detail)
        await db.commit()
        return response
    except Exception:
        await db.rollback()
        raise


@router.get("/events/{event_id}/sale-detail", response_model=SaleDetailResponse)
async def get_sale_detail(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _sale_event(db, event_id)
    detail = (await db.execute(select(SaleDetail).where(SaleDetail.event_id == event_id))).scalar_one_or_none()
    if detail is None:
        raise HTTPException(status_code=404, detail="Sale detail not found")
    return await _sale_detail_response(db, detail)


@router.get("/reports/sales", response_model=SalesReportResponse)
async def sales_report(
    date_from: date,
    date_to: date,
    location_id: Optional[int] = None,
    species: Optional[SpeciesType] = None,
    customer_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    items = await _sales_line_items(db, date_from, date_to, location_id, species, customer_id)
    revenue = sum((item.total_price or Decimal("0") for item in items), Decimal("0.00"))
    head = sum(item.qty for item in items)
    buckets = {}
    for item in items:
        month = item.date.strftime("%Y-%m")
        bucket = buckets.setdefault(month, {"month": month, "revenue": Decimal("0.00"), "head_count": 0})
        bucket["revenue"] += item.total_price or Decimal("0")
        bucket["head_count"] += item.qty
    return SalesReportResponse(
        summary={"total_revenue": revenue, "total_head": head,
                 "avg_price_per_head": (revenue / head).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if head else Decimal("0.00"),
                 "period": {"from": date_from, "to": date_to}},
        by_period=[buckets[month] for month in sorted(buckets)], line_items=items,
    )
