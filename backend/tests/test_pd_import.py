"""Bulk PD imports use in-memory SQLite and in-process ASGI only."""
import csv
import io
from datetime import date

import pytest
from sqlalchemy import func, select

from conftest import FARM_ID, USER_IDS, auth, category_id, make_location
from models import (Animal, AnimalAcquisitionType, AnimalSex, AnimalStatus,
                    PDResult, ReproductiveEvent, ReproductiveEventType, SpeciesType)

pytestmark = pytest.mark.asyncio
URL = '/api/admin/import/pd-tests'
HEADER = ['tag_number', 'test_date', 'result', 'months_pregnant', 'vet', 'notes']


async def animal(db, tag='00123', **values):
    item = Animal(tag_number=tag, species=SpeciesType.CATTLE,
                  category_id=await category_id(db, SpeciesType.CATTLE),
                  location_id=values.pop('location_id', FARM_ID), sex=AnimalSex.FEMALE,
                  acquisition_type=AnimalAcquisitionType.BORN, acquisition_date=date(2020, 1, 1),
                  reproductive_status='unknown', services_without_conception=3, **values)
    db.add(item)
    await db.commit()
    return item.id


async def upload(client, rows, role='data_entry', header=HEADER, filename='results.csv', bom=False):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerows(rows)
    contents = ('\ufeff' if bom else '') + stream.getvalue()
    return await client.post(URL, headers=auth(role) if role else {},
                             files={'file': (filename, contents.encode('utf-8'), 'text/csv')})


@pytest.mark.parametrize('alias,expected', [
    ('pregnant', PDResult.PREGNANT), ('YES', PDResult.PREGNANT), ('p', PDResult.PREGNANT),
    ('open', PDResult.OPEN), ('NO', PDResult.OPEN), ('negative', PDResult.OPEN), ('n', PDResult.OPEN),
    ('recheck', PDResult.REPEAT), ('R', PDResult.REPEAT), ('check', PDResult.REPEAT),
])
async def test_aliases_create_events_and_update_status(client, db_session, alias, expected):
    aid = await animal(db_session)
    response = await upload(client, [['00123', '2026-11-09', alias, '4', 'Dr Vet', 'Note, with comma']], bom=True)
    assert response.status_code == 200, response.text
    assert response.json() == dict(matched=1, events_created=1, not_found=[], skipped=[], total_rows=1)
    saved = (await db_session.execute(select(ReproductiveEvent))).scalar_one()
    assert (saved.animal_id, saved.event_type, saved.pd_result) == (aid, ReproductiveEventType.PD_TEST, expected)
    assert (saved.vet, saved.notes, saved.recorded_by) == ('Dr Vet', 'Note, with comma', USER_IDS['data_entry'])
    current = await db_session.get(Animal, aid)
    await db_session.refresh(current)
    pregnant = expected == PDResult.PREGNANT
    assert current.reproductive_status == ('pregnant' if pregnant else 'open')
    assert saved.months_pregnant == current.months_pregnant == (4 if pregnant else None)
    assert current.last_pd_date == date(2026, 11, 9)
    assert current.services_without_conception == (0 if pregnant else 3)


async def test_skips_unknown_inactive_and_exact_match(client, db_session):
    await animal(db_session, 'ACTIVE')
    await animal(db_session, 'INACTIVE', status=AnimalStatus.DEAD)
    response = await upload(client, [
        ['ACTIVE', '2026-11-09', 'yes', '', '', ''],
        ['active', '2026-11-09', 'no', '', '', ''],
        ['INACTIVE', '2026-11-09', 'no', '', '', ''],
        ['UNKNOWN', '2026-11-09', 'no', '', '', ''],
        ['', '2026-11-09', '', '', '', ''], ['ACTIVE', '', '', '', '', ''],
    ], role='admin')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['matched'] == result['events_created'] == 1
    assert result['not_found'] == ['active', 'INACTIVE', 'UNKNOWN']
    assert result['total_rows'] == 6
    assert result['skipped'] == ['Row 6: missing tag_number', 'Row 7: missing test_date']


async def test_distinct_animals_and_csv_order(client, db_session):
    aid = await animal(db_session)
    response = await upload(client, [
        ['00123', '2026-11-09', 'p', '4', '', ''],
        ['00123', '2026-11-08', 'r', 'ignored', '', ''],
    ])
    assert response.json()['matched'] == 1 and response.json()['events_created'] == 2
    current = await db_session.get(Animal, aid)
    await db_session.refresh(current)
    assert current.reproductive_status == 'open' and current.last_pd_date == date(2026, 11, 8)


@pytest.mark.parametrize('bad', [
    ['00123', '2026-02-30', 'p', '3', '', ''],
    ['00123', '20261109', 'p', '3', '', ''],
    ['00123', '2026-11-09', 'invalid', '3', '', ''],
    ['00123', '2026-11-09', 'p', '-1', '', ''],
    ['00123', '2026-11-09', 'p', '2.5', '', ''],
    ['00123', '2026-11-09', 'p', '2147483648', '', ''],
    ['00123', '2026-11-09', 'p', '3', 'v' * 101, ''],
    ['00123', '2026-11-09', 'p'],
])
async def test_invalid_row_rolls_back_events_and_status(client, db_session, bad):
    aid = await animal(db_session)
    response = await upload(client, [['00123', '2026-11-09', 'p', '3', '', ''], bad])
    assert response.status_code == 400 and 'row 3' in response.json()['detail']
    assert await db_session.scalar(select(func.count(ReproductiveEvent.id))) == 0
    current = await db_session.get(Animal, aid)
    assert current.reproductive_status == 'unknown' and current.services_without_conception == 3


async def test_ambiguous_active_tag_rolls_back(client, db_session):
    await animal(db_session)
    await animal(db_session, 'DUPLICATE')
    loc = await make_location(db_session, 'Other')
    await animal(db_session, 'DUPLICATE', location_id=loc)
    response = await upload(client, [
        ['00123', '2026-11-09', 'p', '', '', ''],
        ['DUPLICATE', '2026-11-09', 'p', '', '', ''],
    ])
    assert response.status_code == 409
    assert await db_session.scalar(select(func.count(ReproductiveEvent.id))) == 0


async def test_access_headers_and_empty_file(client):
    for role in (None, 'viewer'):
        assert (await upload(client, [], role=role)).status_code == 403
    assert (await upload(client, [], filename='results.txt')).status_code == 400
    assert (await upload(client, [], header=['tag_number'])).status_code == 400
    assert (await upload(client, [], header=HEADER + ['result'])).status_code == 400
    result = await upload(client, [])
    assert result.status_code == 200 and result.json()['total_rows'] == 0


@pytest.mark.parametrize('contents', [b'\xff\xfeinvalid', b'tag_number,test_date,result,months_pregnant,vet,notes\n"unclosed'])
async def test_invalid_encoding_and_csv(client, contents):
    response = await client.post(URL, headers=auth('admin'), files={'file': ('test.csv', contents, 'text/csv')})
    assert response.status_code == 400
