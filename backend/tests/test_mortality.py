"""Structured mortality tests: SQLite in memory, no server startup."""
from datetime import date

import pytest
from sqlalchemy import select

from conftest import FARM_ID, auth, category_id, make_daily_log, make_location
from models import DeathCause, Event, EventType, OpeningBalance, SpeciesType
from services.seed import _seed_death_causes

pytestmark = pytest.mark.asyncio


async def cause(client, name='Disease'):
    response = await client.post('/api/death-causes', headers=auth('admin'), json={'name': name})
    assert response.status_code == 200, response.text
    return response.json()['id']


async def report(client, **params):
    return await client.get('/api/reports/mortality', headers=auth('viewer'),
                            params={'date_from': '2026-01-01', 'date_to': '2026-12-31', **params})


async def death(db, day, count, cause_id=None, location=FARM_ID, kind=EventType.DEATH):
    log = await make_daily_log(db, location, day)
    row = Event(daily_log_id=log, event_type=kind, species=SpeciesType.CATTLE,
                category_id=await category_id(db, SpeciesType.CATTLE), count=count,
                cause_of_death_id=cause_id, is_stock_event=True)
    db.add(row)
    await db.commit()
    return row.id


async def test_causes_crud_and_permissions(client):
    cid = await cause(client)
    assert (await client.get('/api/death-causes', headers=auth('viewer'))).json()[0]['id'] == cid
    response = await client.put(f'/api/death-causes/{cid}', headers=auth('admin'), json={'name': 'Illness', 'description': 'Disease related'})
    assert response.json()['name'] == 'Illness'
    assert (await client.post('/api/death-causes', headers=auth('admin'), json={'name': 'Illness'})).status_code == 409
    assert (await client.delete(f'/api/death-causes/{cid}', headers=auth('admin'))).status_code == 200
    assert (await client.get('/api/death-causes', headers=auth('viewer'))).json() == []
    assert len((await client.get('/api/death-causes?is_active=false', headers=auth('viewer'))).json()) == 1
    for role in ('viewer', 'data_entry'):
        assert (await client.post('/api/death-causes', headers=auth(role), json={'name': 'Denied'})).status_code == 403
        assert (await client.put(f'/api/death-causes/{cid}', headers=auth(role), json={'name': 'Denied'})).status_code == 403
        assert (await client.delete(f'/api/death-causes/{cid}', headers=auth(role))).status_code == 403
    assert (await client.get('/api/death-causes')).status_code == 403


async def test_seed_idempotent_preserves_deactivation(db_session):
    connection = await db_session.connection()
    await _seed_death_causes(connection)
    await _seed_death_causes(connection)
    rows = (await db_session.execute(select(DeathCause))).scalars().all()
    assert len(rows) == 7
    rows[0].is_active = False
    await db_session.flush()
    await _seed_death_causes(connection)
    await db_session.refresh(rows[0])
    assert rows[0].is_active is False


async def test_thresholds_atomic_validation_and_roles(client):
    url = '/api/settings/mortality-thresholds'
    response = await client.put(url, headers=auth('admin'), json=[{'species': 'cattle', 'threshold': '5.00'}])
    assert response.status_code == 200, response.text
    response = await client.put(url, headers=auth('admin'), json=[{'species': 'cattle', 'threshold': '4.00'}, {'species': 'sheep', 'threshold': '2'}])
    assert len(response.json()) == 2
    rows = (await client.get(url, headers=auth('viewer'))).json()
    assert next(row for row in rows if row['species'] == 'cattle')['threshold'] == '4.00'
    assert (await client.put(url, headers=auth('admin'), json=[{'species': 'cattle', 'threshold': 1}, {'species': 'goat', 'threshold': -1}])).status_code == 422
    assert (await client.put(url, headers=auth('admin'), json=[{'species': 'cattle', 'threshold': 1}] * 2)).status_code == 400
    for role in ('viewer', 'data_entry'):
        assert (await client.put(url, headers=auth(role), json=[])).status_code == 403


async def test_event_roundtrip_validation_and_clear(client, db_session):
    cid = await cause(client)
    log = await make_daily_log(db_session, FARM_ID, date(2026, 2, 1))
    category = await category_id(db_session, SpeciesType.CATTLE)
    body = dict(event_type='death', species='cattle', category_id=category, count=2, cause_of_death_id=cid)
    response = await client.post(f'/api/daily-logs/{log}/events', headers=auth('admin'), json=body)
    assert response.status_code == 200 and response.json()['cause_of_death_id'] == cid
    eid = response.json()['id']
    detail = await client.get(f'/api/daily-logs/{log}', headers=auth('viewer'))
    assert detail.json()['events'][0]['cause_of_death_id'] == cid
    response = await client.put(f'/api/events/{eid}', headers=auth('admin'), json={'cause_of_death_id': 99999})
    assert response.status_code == 404
    response = await client.put(f'/api/events/{eid}', headers=auth('admin'), json={'cause_of_death_id': None})
    assert response.status_code == 200 and response.json()['cause_of_death_id'] is None
    response = await client.post(f'/api/daily-logs/{log}/events', headers=auth('admin'), json={**body, 'event_type': 'birth'})
    assert response.status_code == 400
    await client.delete(f'/api/death-causes/{cid}', headers=auth('admin'))
    assert (await client.post(f'/api/daily-logs/{log}/events', headers=auth('admin'), json=body)).status_code == 400


async def test_daily_log_creation_carries_cause(client, db_session):
    cid = await cause(client)
    category = await category_id(db_session, SpeciesType.CATTLE)
    response = await client.post('/api/daily-logs', headers=auth('admin'), json={
        'location_id': FARM_ID, 'log_date': '2026-03-01', 'events': [
            {'event_type': 'death', 'species': 'cattle', 'category_id': category, 'count': 1, 'cause_of_death_id': cid},
        ],
    })
    assert response.status_code == 200, response.text
    assert response.json()['events'][0]['cause_of_death_id'] == cid


async def test_analytics_stock_causes_alerts_and_filters(client, db_session):
    cid = await cause(client)
    await death(db_session, date(2026, 2, 1), 4, cid)
    await death(db_session, date(2026, 3, 1), 1)
    # Opening 50; closing 45; average 47.5; five deaths => 10.5263%.
    await client.put('/api/settings/mortality-thresholds', headers=auth('admin'), json=[{'species': 'cattle', 'threshold': '10.52'}])
    response = await report(client)
    assert response.status_code == 200, response.text
    result = response.json()
    row = result['by_species'][0]
    assert row['avg_stock'] == 47.5 and row['mortality_rate_pct'] == 10.53 and row['is_alert']
    assert result['summary']['total_deaths'] == 5
    assert result['by_cause'] == [{'cause_name': 'Disease', 'count': 4, 'pct_of_total': 80.0}]
    assert len(result['flagged']) == 1 and len(result['by_month']) == 12
    assert result['by_month'][1]['by_species']['cattle'] == 4
    assert result['by_month'][0]['deaths'] == 0
    assert (await report(client, species='goat')).json()['summary']['total_deaths'] == 0
    assert (await report(client, date_to='2026-01-31')).json()['summary']['total_deaths'] == 0
    await client.delete(f'/api/death-causes/{cid}', headers=auth('admin'))
    assert (await report(client)).json()['by_cause'][0]['count'] == 4
    other = await make_location(db_session, 'Other')
    assert (await report(client, location_id=other)).json()['by_farm'] == []
    assert (await report(client, date_from='2027-01-01')).status_code == 400


async def test_boundaries_weighting_equality_and_month_window(client, db_session):
    # Both boundary snapshots include events on that date.
    await death(db_session, date(2026, 1, 1), 5)
    await death(db_session, date(2026, 12, 31), 5)
    other = await make_location(db_session, 'Large farm')
    category = await category_id(db_session, SpeciesType.CATTLE)
    db_session.add(OpeningBalance(location_id=other, species=SpeciesType.CATTLE,
                                  category_id=category, count=100, period_start=date(2024, 1, 1)))
    await db_session.commit()
    result = (await report(client)).json()
    assert result['by_species'][0]['avg_stock'] == 142.5
    assert result['by_species'][0]['mortality_rate_pct'] == 7.02
    assert result['by_species'][0]['threshold_pct'] is None and not result['flagged']
    # At the end boundary only: opening == closing == 40; five deaths = 12.5%.
    await client.put('/api/settings/mortality-thresholds', headers=auth('admin'), json=[{'species': 'cattle', 'threshold': '12.5'}])
    result = (await report(client, date_from='2026-12-31', location_id=FARM_ID)).json()
    assert result['by_species'][0]['mortality_rate_pct'] == 12.5 and not result['flagged']
    result = (await report(client, date_from='2024-01-01', date_to='2026-03-15')).json()
    assert len(result['by_month']) == 12 and result['by_month'][0]['month'] == '2025-04'


async def test_zero_stock_null_rate_and_only_deaths(client, db_session):
    other = await make_location(db_session, 'No stock')
    await death(db_session, date(2026, 2, 1), 1, location=other)
    await death(db_session, date(2026, 3, 1), 2, location=other, kind=EventType.BOUGHT)
    result = (await report(client, location_id=other, date_to='2026-02-28')).json()
    assert result['summary']['total_deaths'] == 1 and result['by_species'][0]['mortality_rate_pct'] is None
    assert result['by_cause'] == [] and not result['flagged']
    assert (await report(client, location_id=other)).json()['summary']['total_deaths'] == 1
