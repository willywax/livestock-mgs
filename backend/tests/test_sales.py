"""Customer and sale-detail API tests; SQLite in-memory, no live HTTP."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conftest import FARM_ID, auth, category_id, make_daily_log, make_location
from models import Customer, Event, EventType, SaleDetail, SpeciesType

pytestmark = pytest.mark.asyncio


async def customer(client, name='Buyer', **values):
    response = await client.post('/api/customers', json={'name': name, **values}, headers=auth('data_entry'))
    assert response.status_code == 200, response.text
    return response.json()['id']


async def event(db, day=date(2026, 1, 10), location=FARM_ID, kind=EventType.SOLD,
                species=SpeciesType.CATTLE, count=3):
    log = await make_daily_log(db, location, day)
    row = Event(daily_log_id=log, event_type=kind, species=species,
                category_id=await category_id(db, species), count=count)
    db.add(row)
    await db.commit()
    return row.id


async def save(client, event_id, **values):
    return await client.post(f'/api/events/{event_id}/sale-detail', headers=auth('data_entry'), json=values)


async def report(client, **params):
    return await client.get('/api/reports/sales', headers=auth('viewer'),
                            params={'date_from': '2026-01-01', 'date_to': '2026-12-31', **params})


async def test_customer_crud_search_and_soft_delete(client, db_session):
    cid = await customer(client, 'Buyer One', phone='123', customer_type='abattoir')
    response = await client.put(f'/api/customers/{cid}', headers=auth('data_entry'),
                                json={'name': 'Updated Buyer', 'phone': None, 'customer_type': 'feedlot'})
    assert response.status_code == 200 and response.json()['customer_type'] == 'feedlot'
    assert response.json()['phone'] is None
    detail = (await client.get(f'/api/customers/{cid}', headers=auth('viewer'))).json()
    assert detail['name'] == 'Updated Buyer' and detail['purchases'] == []
    listing = await client.get('/api/customers', headers=auth('viewer'), params={'search': 'UPDATED', 'is_active': True})
    assert [row['id'] for row in listing.json()] == [cid]
    assert (await client.delete(f'/api/customers/{cid}', headers=auth('admin'))).status_code == 200
    assert (await db_session.get(Customer, cid)).is_active is False
    assert (await client.get('/api/customers', headers=auth('viewer'), params={'is_active': True})).json() == []
    assert len((await client.get('/api/customers', headers=auth('viewer'), params={'is_active': False})).json()) == 1


async def test_sale_total_upsert_and_history(client, db_session):
    cid = await customer(client)
    eid = await event(db_session)
    response = await save(client, eid, customer_id=cid, price_per_head='10.25', notes='Initial')
    assert response.status_code == 200, response.text
    original = response.json()
    assert Decimal(original['total_price']) == Decimal('30.75')
    assert original['customer_name'] == 'Buyer'
    response = await save(client, eid, total_price='29.99')
    assert response.json()['id'] == original['id'] and Decimal(response.json()['total_price']) == Decimal('29.99')
    response = await save(client, eid, notes='Only notes')
    assert Decimal(response.json()['total_price']) == Decimal('29.99')
    response = await save(client, eid, price_per_head='12.50')
    assert Decimal(response.json()['total_price']) == Decimal('37.50')
    assert await db_session.scalar(select(func.count(SaleDetail.id))) == 1
    stored_event = await db_session.get(Event, eid)
    assert stored_event.count == 3 and stored_event.sale_price is None and stored_event.buyer_name is None
    read = await client.get(f'/api/events/{eid}/sale-detail', headers=auth('viewer'))
    assert read.json() == response.json()
    await client.delete(f'/api/customers/{cid}', headers=auth('admin'))
    purchases = (await client.get(f'/api/customers/{cid}/purchases', headers=auth('viewer'))).json()
    detail = (await client.get(f'/api/customers/{cid}', headers=auth('viewer'))).json()
    assert detail['purchases'] == purchases and purchases[0]['event_id'] == eid


async def test_sale_validation_and_missing_records(client, db_session):
    eid = await event(db_session, kind=EventType.BIRTH)
    assert (await save(client, eid, price_per_head='10')).status_code == 400
    sold = await event(db_session, day=date(2026, 1, 11))
    assert (await save(client, sold, customer_id=9999)).status_code == 404
    for values in ({'price_per_head': '-1'}, {'total_price': '-1'}, {'price_per_head': '0.001'}, {'total_price': 'NaN'}):
        assert (await save(client, sold, **values)).status_code == 422
    assert (await save(client, sold, price_per_head='9999999999.99')).status_code == 400
    assert await db_session.scalar(select(func.count(SaleDetail.id))) == 0
    assert (await client.get(f'/api/events/{sold}/sale-detail', headers=auth('viewer'))).status_code == 404
    assert (await save(client, 9999)).status_code == 404
    assert (await client.get('/api/customers/9999', headers=auth('viewer'))).status_code == 404
    for values in ({'name': None}, {'name': ' '}, {'customer_type': None}, {'is_active': None}):
        cid = await customer(client)
        assert (await client.put(f'/api/customers/{cid}', headers=auth('data_entry'), json=values)).status_code == 422


async def test_report_totals_months_dates_and_filters(client, db_session):
    first_customer = await customer(client, 'First')
    second_customer = await customer(client, 'Second')
    other = await make_location(db_session, 'Other Farm')
    first = await event(db_session, day=date(2026, 1, 1), count=2)
    last = await event(db_session, day=date(2026, 2, 28), location=other, count=4, species=SpeciesType.GOAT)
    outside = await event(db_session, day=date(2025, 12, 31), count=10)
    await event(db_session, day=date(2026, 2, 15), count=99)  # No sale detail: excluded.
    for eid, cid, price in [(first, first_customer, '10.50'), (last, second_customer, '20'), (outside, first_customer, '100')]:
        assert (await save(client, eid, customer_id=cid, price_per_head=price)).status_code == 200
    response = await report(client, date_to='2026-02-28')
    assert response.status_code == 200, response.text
    result = response.json()
    assert [row['event_id'] for row in result['line_items']] == [last, first]
    assert Decimal(result['summary']['total_revenue']) == Decimal('101.00')
    assert result['summary']['total_head'] == 6 and Decimal(result['summary']['avg_price_per_head']) == Decimal('16.83')
    assert result['summary']['period'] == {'from': '2026-01-01', 'to': '2026-02-28'}
    assert [row['month'] for row in result['by_period']] == ['2026-01', '2026-02']
    assert [row['head_count'] for row in result['by_period']] == [2, 4]
    for params, expected in [({'location_id': FARM_ID}, first), ({'customer_id': first_customer}, first), ({'species': 'goat'}, last)]:
        rows = (await report(client, **params)).json()['line_items']
        assert [row['event_id'] for row in rows] == [expected]
    assert (await report(client, date_from='2027-01-01')).status_code == 400
    empty = (await report(client, date_from='2027-01-01', date_to='2027-02-01')).json()
    assert empty['line_items'] == [] and empty['by_period'] == [] and Decimal(empty['summary']['avg_price_per_head']) == 0


async def test_nullable_and_explicit_prices(client, db_session):
    eid = await event(db_session)
    assert (await save(client, eid)).json()['total_price'] is None
    response = await save(client, eid, price_per_head='2.10', total_price='5.00')
    assert Decimal(response.json()['total_price']) == Decimal('5.00')
    response = await save(client, eid, total_price=None)
    assert Decimal(response.json()['total_price']) == Decimal('6.30')
    response = await save(client, eid, price_per_head=None, customer_id=None)
    assert response.json()['total_price'] is None and response.json()['price_per_head'] is None
    result = (await report(client)).json()
    assert result['summary']['total_head'] == 3 and Decimal(result['summary']['total_revenue']) == 0


async def test_role_gates(client, db_session):
    cid = await customer(client)
    eid = await event(db_session)
    assert (await client.post('/api/customers', json={'name': 'Denied'})).status_code == 403
    assert (await client.get('/api/customers')).status_code == 403
    for method, url, payload in [
        ('post', '/api/customers', {'name': 'Denied'}),
        ('put', f'/api/customers/{cid}', {'name': 'Denied'}),
        ('post', f'/api/events/{eid}/sale-detail', {'total_price': '1'}),
    ]:
        assert (await getattr(client, method)(url, json=payload, headers=auth('viewer'))).status_code == 403
    assert (await client.delete(f'/api/customers/{cid}', headers=auth('data_entry'))).status_code == 403
    assert (await client.post(f'/api/events/{eid}/sale-detail', json={'total_price': '1'}, headers=auth('admin'))).status_code == 200
