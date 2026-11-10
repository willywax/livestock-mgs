from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

import server
from conftest import FARM_ID, auth, category_id, make_daily_log, make_location, make_stock, post_event, api_stock
from models import (Animal, AnimalAcquisitionType, AnimalSex, AnimalStatus, Event, EventAnimalLink,
                    SpeciesType, User, DailyLog, CategoryTransition)

pytestmark = pytest.mark.asyncio


async def setup(db, **overrides):
    cat = await category_id(db, SpeciesType.CATTLE)
    fields = dict(tag_number='MOTHER', species=SpeciesType.CATTLE, category_id=cat, location_id=FARM_ID,
                  sex=AnimalSex.FEMALE, acquisition_type=AnimalAcquisitionType.BORN,
                  acquisition_date=date(2020, 1, 1), reproductive_status='pregnant', months_pregnant=8,
                  services_without_conception=2)
    fields.update(overrides)
    animal = Animal(**fields)
    db.add(animal)
    await db.commit()
    log = await make_daily_log(db, FARM_ID, date(2026, 11, 1))
    return animal, log, cat


async def create(client, log, kind, **fields):
    response = await post_event(client, log, event_type=kind, species='cattle', count=0, **fields)
    assert response.status_code == 200, response.text
    return response.json()


async def timeline(client, animal, **params):
    response = await client.get(f'/api/animals/{animal.id}/daily-log-timeline', params=params, headers=auth('viewer'))
    assert response.status_code == 200, response.text
    return response.json()


async def test_birth_updates_mother_not_offspring(client, db_session):
    animal, log, cat = await setup(db_session)
    ev = await create(client, log, 'birth', category_id=cat, mother_tag='MOTHER', offspring_tags='BABY')
    assert not ev['sync_warnings']
    await db_session.refresh(animal)
    assert (animal.reproductive_status, animal.last_calving_date, animal.months_pregnant,
            animal.services_without_conception) == ('open', date(2026, 11, 1), None, 0)
    baby = (await db_session.execute(select(Animal).where(Animal.tag_number == 'BABY'))).scalar_one()
    assert baby.last_calving_date is None and baby.reproductive_status == 'unknown'
    assert (await timeline(client, animal))['total'] == 1
    assert (await timeline(client, baby))['total'] == 1


@pytest.mark.parametrize('result,months,status', [('pregnant', 4, 'pregnant'), ('open', None, 'open')])
async def test_pd_fields_round_trip_without_stock(client, db_session, result, months, status):
    animal, log, cat = await setup(db_session)
    ev = await create(client, log, 'pd_test', animal_tags='MOTHER', pd_result=result, months_pregnant=months, is_stock_event=True)
    assert ev['is_stock_event'] is False and ev['pd_result'] == result
    assert ev['months_pregnant'] == months and not ev['sync_warnings']
    await db_session.refresh(animal)
    assert animal.reproductive_status == status and animal.months_pregnant == months
    assert animal.last_pd_date == date(2026, 11, 1)
    assert await api_stock(client, FARM_ID, cat) == 50
    detail = await client.get(f'/api/daily-logs/{log}', headers=auth('viewer'))
    assert detail.json()['events'][0]['pd_result'] == result


async def test_abortion_mother_only_and_restore_on_delete(client, db_session):
    animal, log, _ = await setup(db_session, last_calving_date=date(2024, 1, 1))
    ev = await create(client, log, 'abortion', mother_tag='MOTHER')
    await db_session.refresh(animal)
    assert animal.reproductive_status == 'open' and animal.months_pregnant is None and animal.last_calving_date is None
    deleted = await client.delete(f"/api/events/{ev['id']}", headers=auth('admin'))
    assert deleted.status_code == 200, deleted.text
    await db_session.refresh(animal)
    assert animal.months_pregnant == 8 and animal.last_calving_date == date(2024, 1, 1)
    assert (await timeline(client, animal))['total'] == 0


@pytest.mark.parametrize('status,expected', [('open', 3), ('unknown', 3), ('pregnant', 2)])
async def test_service_only_counts_open_or_unknown(client, db_session, status, expected):
    animal, log, _ = await setup(db_session, reproductive_status=status)
    ev = await create(client, log, 'service', animal_tags='MOTHER, MOTHER')
    assert not ev['sync_warnings']
    await db_session.refresh(animal)
    assert animal.services_without_conception == expected
    assert (await timeline(client, animal))['total'] == 1


async def test_services_resave_edit_and_delete_are_replayable(client, db_session):
    animal, log, _ = await setup(db_session, reproductive_status='open', services_without_conception=0)
    first = await create(client, log, 'service', animal_tags='MOTHER')
    second = await create(client, log, 'service', animal_tags='MOTHER')
    event = await db_session.get(Event, first['id'])
    assert await server._sync_animals_from_event(db_session, event, await db_session.get(DailyLog, log), await db_session.get(User, 1)) == []
    await db_session.refresh(animal)
    assert animal.services_without_conception == 2
    updated = await client.put(f"/api/events/{first['id']}", json={'notes': 'Corrected'}, headers=auth('admin'))
    assert updated.status_code == 200 and not updated.json()['sync_warnings']
    await db_session.refresh(animal)
    assert animal.services_without_conception == 2
    assert (await client.delete(f"/api/events/{first['id']}", headers=auth('admin'))).status_code == 200
    await db_session.refresh(animal)
    assert animal.services_without_conception == 1
    assert (await client.delete(f"/api/events/{second['id']}", headers=auth('admin'))).status_code == 200
    await db_session.refresh(animal)
    assert animal.services_without_conception == 0


async def test_later_standalone_observation_survives_daily_event_delete(client, db_session):
    animal, log, _ = await setup(db_session, reproductive_status='open', services_without_conception=0)
    ev = await create(client, log, 'service', animal_tags='MOTHER')
    pd = await client.post(f'/api/animals/{animal.id}/reproductive-events', headers=auth('admin'),
                          json={'event_type': 'pd_test', 'event_date': '2026-11-02', 'pd_result': 'pregnant', 'months_pregnant': 3})
    assert pd.status_code == 200, pd.text
    assert (await client.delete(f"/api/events/{ev['id']}", headers=auth('admin'))).status_code == 200
    await db_session.refresh(animal)
    assert animal.reproductive_status == 'pregnant' and animal.months_pregnant == 3 and animal.services_without_conception == 0


async def test_edit_subject_moves_reproductive_effect(client, db_session):
    animal, log, cat = await setup(db_session, reproductive_status='open', services_without_conception=0)
    other = Animal(tag_number='OTHER', species=SpeciesType.CATTLE, category_id=cat, location_id=FARM_ID,
                   sex=AnimalSex.FEMALE, acquisition_type=AnimalAcquisitionType.BORN,
                   acquisition_date=date(2020, 1, 1), reproductive_status='open', services_without_conception=0)
    db_session.add(other)
    await db_session.commit()
    ev = await create(client, log, 'service', animal_tags='MOTHER')
    update = await client.put(f"/api/events/{ev['id']}", headers=auth('admin'), json={'animal_tags': 'OTHER'})
    assert update.status_code == 200 and not update.json()['sync_warnings'], update.text
    await db_session.refresh(animal); await db_session.refresh(other)
    assert animal.services_without_conception == 0 and other.services_without_conception == 1
    assert (await timeline(client, animal))['total'] == 0
    assert (await timeline(client, other))['total'] == 1


async def test_death_sale_transfer_and_retag_preserve_links(client, db_session):
    animal, log, cat = await setup(db_session)
    death = await create(client, log, 'death', category_id=cat, animal_tags='MOTHER')
    await db_session.refresh(animal)
    assert animal.status == AnimalStatus.DEAD
    animal.tag_number = 'NEW-TAG'; await db_session.commit()
    assert (await timeline(client, animal))['items'][0]['event_id'] == death['id']
    assert (await client.delete(f"/api/events/{death['id']}", headers=auth('admin'))).status_code == 200
    await db_session.refresh(animal); assert animal.status == AnimalStatus.ACTIVE
    destination = await make_location(db_session, 'Destination')
    transfer = await create(client, log, 'transfer', category_id=cat, animal_tags='NEW-TAG', from_location_id=FARM_ID, to_location_id=destination)
    assert not transfer['sync_warnings']
    await db_session.refresh(animal); assert animal.location_id == destination
    sold = await create(client, log, 'sold', category_id=cat, animal_tags='NEW-TAG')
    assert not sold['sync_warnings']
    await db_session.refresh(animal); assert animal.status == AnimalStatus.SOLD


async def test_sync_never_raises_and_repro_failure_does_not_break_save(client, db_session, monkeypatch):
    assert await server._sync_animals_from_event(db_session, object(), object(), object())
    animal, log, cat = await setup(db_session)
    async def broken(*args, **kwargs):
        raise RuntimeError('Injected failure')
    monkeypatch.setattr(server, '_sync_daily_links', broken)
    ev = await create(client, log, 'death', category_id=cat, animal_tags='MOTHER')
    assert ev['sync_warnings']
    await db_session.refresh(animal); assert animal.status == AnimalStatus.DEAD


async def test_calving_transition_once_and_isolated_failure(client, db_session, monkeypatch):
    heifer = await category_id(db_session, SpeciesType.CATTLE, 'Mitamba')
    animal, log, cat = await setup(db_session, category_id=heifer)
    await server._seed_category_transition_rules(db_session)
    async def broken(*args, **kwargs):
        raise RuntimeError('transition unavailable')
    monkeypatch.setattr(server, '_confirm_category_transition', broken)
    ev = await create(client, log, 'birth', category_id=cat, mother_tag='MOTHER')
    assert any('transition skipped' in warning for warning in ev['sync_warnings'])
    await db_session.refresh(animal)
    assert animal.reproductive_status == 'open' and animal.last_calving_date == date(2026, 11, 1)


async def test_timeline_order_filters_pagination_and_access(client, db_session):
    animal, log, _ = await setup(db_session, reproductive_status='open')
    one = await create(client, log, 'service', animal_tags='MOTHER', notes='first')
    two = await create(client, log, 'pd_test', animal_tags='MOTHER', pd_result='open')
    older = await make_daily_log(db_session, FARM_ID, date(2026, 10, 1))
    three = await create(client, older, 'service', animal_tags='MOTHER')
    page = await timeline(client, animal, page_size=2)
    assert page['total'] == 3 and [i['event_id'] for i in page['items']] == [two['id'], one['id']]
    assert page['items'][0]['result'] == 'open' and page['items'][0]['recorded_by_name'] == 'admin'
    assert [i['event_id'] for i in (await timeline(client, animal, page=2, page_size=2))['items']] == [three['id']]
    assert (await timeline(client, animal, event_type='service', from_date='2026-11-01', to_date='2026-11-01'))['total'] == 1
    url = f'/api/animals/{animal.id}/daily-log-timeline'
    assert (await client.get(url)).status_code == 403
    assert (await client.get(url, params={'page_size': 101}, headers=auth('viewer'))).status_code == 422
    assert (await client.get(url, params={'from_date': '2026-11-02', 'to_date': '2026-11-01'}, headers=auth('viewer'))).status_code == 400
    assert (await client.get('/api/animals/999/daily-log-timeline', headers=auth('viewer'))).status_code == 404


async def test_pd_validation_before_any_register_changes(client, db_session):
    animal, log, _ = await setup(db_session)
    bad = await post_event(client, log, event_type='pd_test', species='cattle', animal_tags='MOTHER')
    assert bad.status_code == 422
    bad = await post_event(client, log, event_type='pd_test', species='cattle', pd_result='pregnant', months_pregnant=-1)
    assert bad.status_code == 422
    assert await db_session.scalar(select(func.count(Event.id))) == 0


async def test_log_date_edit_replays_in_date_order(client, db_session):
    animal, log, _ = await setup(db_session, reproductive_status='open', services_without_conception=0)
    await create(client, log, 'service', animal_tags='MOTHER')
    later = await make_daily_log(db_session, FARM_ID, date(2026, 11, 2))
    await create(client, later, 'pd_test', animal_tags='MOTHER', pd_result='pregnant', months_pregnant=2)
    update = await client.put(f'/api/daily-logs/{log}', headers=auth('admin'), json={'log_date': '2026-11-03'})
    assert update.status_code == 200, update.text
    await db_session.refresh(animal)
    assert animal.reproductive_status == 'pregnant' and animal.services_without_conception == 0


async def test_first_calving_transition_is_not_repeated_on_edit(client, db_session):
    heifer = await category_id(db_session, SpeciesType.CATTLE, 'Mitamba')
    animal, log, cow = await setup(db_session, category_id=heifer)
    await make_stock(db_session, FARM_ID, SpeciesType.CATTLE, heifer, 1)
    await server._seed_category_transition_rules(db_session)
    ev = await create(client, log, 'birth', mother_tag='MOTHER', category_id=cow)
    assert not ev['sync_warnings'], ev
    await db_session.refresh(animal)
    assert animal.category_id == cow
    for notes in ('updated', 'updated again'):
        response = await client.put(f"/api/events/{ev['id']}", headers=auth('admin'), json={'notes': notes})
        assert response.status_code == 200 and not response.json()['sync_warnings'], response.text
    assert await db_session.scalar(select(func.count(CategoryTransition.id))) == 1
    assert await api_stock(client, FARM_ID, heifer) == 0
    assert await api_stock(client, FARM_ID, cow) == 51
    response = await client.delete(f"/api/events/{ev['id']}", headers=auth('admin'))
    assert response.status_code == 200 and any('transition retained' in msg for msg in response.json()['sync_warnings'])


async def test_male_and_untagged_events_do_not_change_reproductive_fields(client, db_session):
    animal, log, _ = await setup(db_session, sex=AnimalSex.MALE)
    result = await create(client, log, 'pd_test', animal_tags='MOTHER', pd_result='open')
    assert any('female' in msg for msg in result['sync_warnings'])
    await create(client, log, 'service')
    await db_session.refresh(animal)
    assert animal.reproductive_status == 'pregnant' and animal.months_pregnant == 8


async def test_historical_backfill_is_idempotent_and_does_not_replay_state(client, db_session):
    from models import EventType
    animal, log, _ = await setup(db_session)
    db_session.add(Event(daily_log_id=log, event_type=EventType.ABORTION, species=SpeciesType.CATTLE,
                         mother_tag='MOTHER', is_stock_event=False, count=1))
    db_session.add(Event(daily_log_id=log, event_type=EventType.SERVICE, species=SpeciesType.CATTLE,
                         animal_tags='MOTHER-LONGER', is_stock_event=False, count=1))
    await db_session.commit()
    preview = await server._backfill_daily_event_links(db_session)
    assert preview['links'] == 1 and preview['unresolved'] == 1
    assert await db_session.scalar(select(func.count(EventAnimalLink.id))) == 0
    await server._backfill_daily_event_links(db_session, apply=True)
    await server._backfill_daily_event_links(db_session, apply=True)
    assert (await timeline(client, animal))['total'] == 1
    await db_session.refresh(animal)
    assert animal.reproductive_status == 'pregnant' and animal.months_pregnant == 8
