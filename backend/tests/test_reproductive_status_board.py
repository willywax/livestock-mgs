from datetime import datetime, timedelta, timezone

import pytest

from conftest import FARM_ID, auth, category_id, make_location
from models import (Animal, AnimalAcquisitionType, AnimalSex, AnimalStatus,
                    ReproductiveEvent, ReproductiveEventType, SpeciesType)

pytestmark = pytest.mark.asyncio
URL = '/api/reproduction/status-board'


def today():
    return datetime.now(timezone(timedelta(hours=3))).date()


async def animal(db, tag, **values):
    species = values.pop('species', SpeciesType.CATTLE)
    fields = dict(tag_number=tag, species=species, category_id=await category_id(db, species),
                  location_id=FARM_ID, sex=AnimalSex.FEMALE, status=AnimalStatus.ACTIVE,
                  acquisition_type=AnimalAcquisitionType.BORN, acquisition_date=today(),
                  reproductive_status='unknown', birth_date=today().replace(year=today().year - 3))
    fields.update(values)
    result = Animal(**fields)
    db.add(result)
    await db.commit()
    return result


async def board(client, role='viewer', **params):
    response = await client.get(URL, params=params, headers=auth(role))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('role', ['admin', 'data_entry', 'viewer'])
async def test_empty_board_all_roles(client, role):
    result = await board(client, role)
    assert result.pop('summary') == {'total_breeding_females': 0, 'status_known_pct': 0}
    assert len(result) == 9
    assert all(bucket['count'] == 0 and bucket['animals'] == [] for bucket in result.values())
    assert (await client.get(URL)).status_code == 403


async def test_current_herd_filters_and_age_summary(client, db_session):
    await animal(db_session, 'OPEN', reproductive_status='open')
    await animal(db_session, 'UNKNOWN')
    await animal(db_session, 'NO-DOB', birth_date=None)
    await animal(db_session, 'YOUNG', birth_date=today() - timedelta(days=100), reproductive_status='pregnant')
    await animal(db_session, 'MALE', sex=AnimalSex.MALE)
    await animal(db_session, 'DEAD', status=AnimalStatus.DEAD)
    await animal(db_session, 'SOLD', status=AnimalStatus.SOLD)
    farm = await make_location(db_session, 'Second Farm')
    await animal(db_session, 'GOAT', species=SpeciesType.GOAT, location_id=farm, reproductive_status='open')
    data = await board(client, farm_id=FARM_ID, species='cattle')
    assert data['summary'] == {'total_breeding_females': 2, 'status_known_pct': 50}
    assert [a['tag_number'] for a in data['needs_attention']['animals']] == ['UNKNOWN']
    assert [a['tag_number'] for a in data['unknown_status']['animals']] == ['NO-DOB']
    assert data['pregnant']['count'] == 1
    goat = await board(client, farm_id=farm, species='goat')
    assert goat['open']['animals'][0]['tag_number'] == 'GOAT'
    assert goat['open']['animals'][0]['farm'] == 'Second Farm'
    assert (await client.get(URL, params={'species': 'invalid'}, headers=auth('viewer'))).status_code == 422


@pytest.mark.parametrize('species,gestation', [(SpeciesType.CATTLE, 283), (SpeciesType.SHEEP, 147), (SpeciesType.GOAT, 150)])
async def test_due_dates_boundaries_and_overlapping_buckets(client, db_session, species, gestation):
    for days in (-1, 0, 30, 31):
        await animal(db_session, f'DUE-{days}', species=species, reproductive_status='pregnant',
                     months_pregnant=4, last_pd_date=today() + timedelta(days=days - gestation + 120))
    await animal(db_session, 'NO-MONTHS', species=species, reproductive_status='pregnant', last_pd_date=today())
    await animal(db_session, 'NO-PD', species=species, reproductive_status='pregnant', months_pregnant=4)
    await animal(db_session, 'OPEN-OLD-PD', species=species, reproductive_status='open', months_pregnant=4,
                 last_pd_date=today() - timedelta(days=gestation - 120))
    data = await board(client)
    assert data['pregnant']['count'] == 6
    assert {a['tag_number'] for a in data['due_this_month']['animals']} == {'DUE-0', 'DUE-30'}
    assert data['close_to_calving']['animals'] == data['due_this_month']['animals']
    assert {a['expected_calving_date'] for a in data['due_this_month']['animals']} == {
        today().isoformat(), (today() + timedelta(days=30)).isoformat()}


async def test_recent_events_latest_event_and_no_duplicate_animals(client, db_session):
    current = await animal(db_session, 'CURRENT', last_calving_date=today() - timedelta(days=30))
    old = await animal(db_session, 'OLD', last_calving_date=today() - timedelta(days=31))
    future = await animal(db_session, 'FUTURE', last_calving_date=today() + timedelta(days=1))
    for aid, offset in [(current.id, -30), (current.id, -2), (old.id, -31), (future.id, 1)]:
        db_session.add(ReproductiveEvent(animal_id=aid, event_type=ReproductiveEventType.ABORTION,
                                         event_date=today() + timedelta(days=offset)))
    db_session.add(ReproductiveEvent(animal_id=current.id, event_type=ReproductiveEventType.SERVICE, event_date=today()))
    await db_session.commit()
    data = await board(client)
    assert data['recently_calved']['count'] == data['recently_aborted']['count'] == 1
    row = data['recently_aborted']['animals'][0]
    assert row['id'] == current.id
    assert row['last_event_date'] == today().isoformat() and row['last_event_type'] == 'service'


async def test_attention_includes_stale_pd_and_repeat_breeders_once(client, db_session):
    await animal(db_session, 'STALE', reproductive_status='pregnant', last_pd_date=today() - timedelta(days=181), services_without_conception=5)
    await animal(db_session, 'BOUNDARY', reproductive_status='pregnant', last_pd_date=today() - timedelta(days=180))
    await animal(db_session, 'REPEAT', reproductive_status='open', services_without_conception=3)
    await animal(db_session, 'TWO', reproductive_status='open', services_without_conception=2)
    data = await board(client)
    assert {a['tag_number'] for a in data['needs_attention']['animals']} == {'STALE', 'REPEAT'}
    assert data['repeat_breeders']['count'] == 2


async def test_breeding_age_boundary(client, db_session):
    boundary = today().replace(year=today().year - 2)
    await animal(db_session, 'MATURE', birth_date=boundary)
    await animal(db_session, 'YOUNGER', birth_date=boundary + timedelta(days=1))
    data = await board(client)
    assert data['needs_attention']['animals'][0]['tag_number'] == 'MATURE'
    assert data['unknown_status']['animals'][0]['tag_number'] == 'YOUNGER'
    assert data['summary']['total_breeding_females'] == 1
