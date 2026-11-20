"""Reproduction / animal-profile routes. SQLite in-memory; GCS is monkeypatched (never touched)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

import server
from conftest import FARM_ID, auth, category_id, make_daily_log, make_location, make_stock, post_event
from models import (
    Animal, AnimalAcquisitionType, AnimalPhoto, AnimalSex, AnimalStatus, CategoryScope,
    FarmHealthEvent, HealthEventType, SpeciesType,
)

pytestmark = pytest.mark.asyncio
CATTLE = SpeciesType.CATTLE
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

READ_ROUTES = [
    "/api/bull-assignments", "/api/reproductive-cycles", "/api/reproductive-cycles/1",
    "/api/bcs-records", "/api/animals/1/reproductive-history", "/api/animals/1/photos",
    "/api/animals/1/notes", "/api/animals/1/timeline", "/api/analytics/reproduction",
]


async def make_animal(db, tag, sex=AnimalSex.FEMALE, cat=None, loc=FARM_ID, status=AnimalStatus.ACTIVE):
    cat = cat or await category_id(db, CATTLE)
    animal = Animal(tag_number=tag, species=CATTLE, category_id=cat, location_id=loc, sex=sex,
                    acquisition_type=AnimalAcquisitionType.BORN, acquisition_date=date(2022, 1, 1),
                    status=status)
    db.add(animal)
    await db.commit()
    return animal.id


async def post(client, url, role="admin", **body):
    return await client.post(url, json=body, headers=auth(role))


async def put(client, url, role="admin", **body):
    return await client.put(url, json=body, headers=auth(role))


async def cycle(client, animal_id, **body):
    r = await post(client, "/api/reproductive-cycles", animal_id=animal_id, **body)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- auth ----------------
@pytest.mark.parametrize("route", READ_ROUTES)
async def test_new_routes_reject_anonymous(client, route):
    assert (await client.get(route)).status_code == 403


@pytest.mark.parametrize("route", READ_ROUTES)
async def test_new_routes_reject_garbage_token(client, route):
    assert (await client.get(route, headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_write_and_delete_roles(client, db_session):
    cow = await make_animal(db_session, "C1")
    for url, body in [
        ("/api/bull-assignments", {"bull_animal_id": cow, "location_id": 1, "assigned_date": "2024-01-01"}),
        ("/api/reproductive-cycles", {"animal_id": cow}),
        ("/api/bcs-records", {"animal_id": cow, "score_date": "2024-01-01", "bcs": 3}),
        (f"/api/animals/{cow}/notes", {"note_date": "2024-01-01", "content": "x"}),
    ]:
        assert (await post(client, url, "viewer", **body)).status_code == 403, url
    note = (await post(client, f"/api/animals/{cow}/notes", "data_entry", note_date="2024-01-01", content="ok")).json()
    for url in (f"/api/animals/{cow}/notes/{note['id']}", "/api/reproductive-cycles/1",
                "/api/bull-assignments/1", "/api/bcs-records/1", f"/api/animals/{cow}/photos/1"):
        assert (await client.delete(url, headers=auth("data_entry"))).status_code == 403, url


# ---------------- bull assignments ----------------
async def test_bull_assignment_validation_and_filters(client, db_session):
    bull = await make_animal(db_session, "B1", sex=AnimalSex.MALE)
    cow = await make_animal(db_session, "C1")
    body = {"bull_animal_id": bull, "location_id": 1, "assigned_date": "2024-01-01"}
    assert (await post(client, "/api/bull-assignments", **{**body, "bull_animal_id": cow})).status_code == 400
    assert (await post(client, "/api/bull-assignments", **{**body, "bull_animal_id": 999})).status_code == 404
    assert (await post(client, "/api/bull-assignments", **{**body, "removed_date": "2023-01-01"})).status_code == 400
    r = await post(client, "/api/bull-assignments", "data_entry", **body)
    assert r.status_code == 200 and r.json()["bull_tag_number"] == "B1"
    assert r.json()["location_name"] == "Test Farm"
    assert (await post(client, "/api/bull-assignments", **body)).status_code == 409
    done = await post(client, "/api/bull-assignments", **{**body, "assigned_date": "2023-01-01", "removed_date": "2023-06-01"})
    assert done.status_code == 200
    active = (await client.get("/api/bull-assignments?active_only=true", headers=auth("viewer"))).json()
    assert [a["id"] for a in active] == [r.json()["id"]]
    assert len((await client.get("/api/bull-assignments?location_id=1", headers=auth("viewer"))).json()) == 2


async def test_bull_assignment_update_and_delete_blocked_by_cycles(client, db_session):
    bull = await make_animal(db_session, "B1", sex=AnimalSex.MALE)
    cow = await make_animal(db_session, "C1")
    ba = (await post(client, "/api/bull-assignments", bull_animal_id=bull, location_id=1, assigned_date="2024-01-01")).json()
    upd = await put(client, f"/api/bull-assignments/{ba['id']}", removed_date="2024-05-01", notes="gone")
    assert upd.status_code == 200 and upd.json()["removed_date"] == "2024-05-01"
    assert (await put(client, f"/api/bull-assignments/{ba['id']}", location_id=999)).status_code == 404
    c = await cycle(client, cow, bull_assignment_id=ba["id"])
    assert c["bull_tag_number"] == "B1"
    assert (await client.delete(f"/api/bull-assignments/{ba['id']}", headers=auth("admin"))).status_code == 409
    await client.delete(f"/api/reproductive-cycles/{c['id']}", headers=auth("admin"))
    assert (await client.delete(f"/api/bull-assignments/{ba['id']}", headers=auth("admin"))).status_code == 200


# ---------------- reproductive cycles ----------------
async def test_cycle_numbering_and_expected_calving(client, db_session):
    cow = await make_animal(db_session, "C1")
    c1 = await cycle(client, cow, service_date="2024-01-10")
    c2 = await cycle(client, cow, service_date="2025-01-10")
    assert (c1["cycle_number"], c2["cycle_number"]) == (1, 2)
    assert c1["expected_calving_date"] == (date(2024, 1, 10) + timedelta(days=283)).isoformat()
    assert c1["animal_tag_number"] == "C1" and c1["location_name"] == "Test Farm"
    explicit = await cycle(client, cow, service_date="2026-01-01", expected_calving_date="2026-10-01")
    assert explicit["expected_calving_date"] == "2026-10-01"
    other = await make_animal(db_session, "C2")
    assert (await cycle(client, other))["cycle_number"] == 1  # numbering is per animal


async def test_cycle_validation(client, db_session):
    bull = await make_animal(db_session, "B1", sex=AnimalSex.MALE)
    cow = await make_animal(db_session, "C1")
    assert (await post(client, "/api/reproductive-cycles", animal_id=bull)).status_code == 400
    assert (await post(client, "/api/reproductive-cycles", animal_id=999)).status_code == 404
    assert (await post(client, "/api/reproductive-cycles", animal_id=cow, bull_assignment_id=999)).status_code == 404
    assert (await post(client, "/api/reproductive-cycles", animal_id=cow, bcs_at_service=9)).status_code == 422
    assert (await client.get("/api/reproductive-cycles/999", headers=auth("viewer"))).status_code == 404


async def test_cycle_intervals_recompute_on_edit_and_delete(client, db_session):
    cow = await make_animal(db_session, "C1")
    c1 = await cycle(client, cow, service_date="2023-01-01", actual_calving_date="2023-10-01", calving_outcome="live_calf")
    c2 = await cycle(client, cow, service_date="2024-01-01", actual_calving_date="2024-10-05")
    assert c2["days_to_service"] == (date(2024, 1, 1) - date(2023, 10, 1)).days
    assert c2["calving_interval_days"] == (date(2024, 10, 5) - date(2023, 10, 1)).days
    assert c1["calving_interval_days"] is None
    await put(client, f"/api/reproductive-cycles/{c1['id']}", actual_calving_date="2023-09-01")
    got = (await client.get(f"/api/reproductive-cycles/{c2['id']}", headers=auth("viewer"))).json()
    assert got["calving_interval_days"] == (date(2024, 10, 5) - date(2023, 9, 1)).days
    assert got["days_to_service"] == (date(2024, 1, 1) - date(2023, 9, 1)).days
    await client.delete(f"/api/reproductive-cycles/{c1['id']}", headers=auth("admin"))
    got = (await client.get(f"/api/reproductive-cycles/{c2['id']}", headers=auth("viewer"))).json()
    assert got["calving_interval_days"] is None and got["cycle_number"] == 2


async def test_lifetime_calvings_tracks_cycle_saves(client, db_session):
    cow = await make_animal(db_session, "LC1")
    count = lambda: db_session.scalar(select(Animal.lifetime_calvings).where(Animal.id == cow))  # noqa: E731
    c1 = await cycle(client, cow, service_date="2023-01-01", actual_calving_date="2023-10-01", calving_outcome="live_calf")
    await db_session.commit()  # end the read snapshot so the next read sees the route's write
    assert await count() == 1
    ab = await cycle(client, cow, service_date="2024-01-01", actual_calving_date="2024-10-01", calving_outcome="abortion")
    await db_session.commit()
    assert await count() == 1  # abortions are not calvings
    await put(client, f"/api/reproductive-cycles/{ab['id']}", calving_outcome="stillbirth")
    await db_session.commit()
    assert await count() == 2
    await client.delete(f"/api/reproductive-cycles/{c1['id']}", headers=auth("admin"))
    await db_session.commit()
    assert await count() == 1


async def test_lifetime_calvings_failure_never_raises(client, db_session, monkeypatch):
    cow = await make_animal(db_session, "LC2")

    async def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db_session, "execute", boom, raising=False)
    await server._sync_lifetime_calvings(cow, db_session)  # must swallow and log


async def test_cycle_update_recomputes_expected_date(client, db_session):
    cow = await make_animal(db_session, "C1")
    c = await cycle(client, cow, service_date="2024-01-10")
    r = await put(client, f"/api/reproductive-cycles/{c['id']}", service_date="2024-02-10", notes="re-served")
    assert r.json()["expected_calving_date"] == (date(2024, 2, 10) + timedelta(days=283)).isoformat()
    assert r.json()["notes"] == "re-served"
    keep = await put(client, f"/api/reproductive-cycles/{c['id']}", service_date="2024-03-10", expected_calving_date="2024-12-25")
    assert keep.json()["expected_calving_date"] == "2024-12-25"
    cleared = await put(client, f"/api/reproductive-cycles/{c['id']}", notes=None, status=None)
    assert cleared.json()["notes"] is None and cleared.json()["status"] == "open"


async def test_cycle_list_filters_and_history_summary(client, db_session):
    cow = await make_animal(db_session, "C1")
    other = await make_animal(db_session, "C2")
    await cycle(client, cow, service_date="2023-01-01", actual_calving_date="2023-10-01", calving_outcome="live_calf")
    await cycle(client, cow, service_date="2024-01-01", actual_calving_date="2024-10-05", calving_outcome="assisted_live", status="calved")
    await cycle(client, other, service_date="2024-02-01", status="served")
    get = lambda q: client.get(f"/api/reproductive-cycles?{q}", headers=auth("viewer"))  # noqa: E731
    assert len((await get(f"animal_id={cow}")).json()) == 2
    assert len((await get("status=served")).json()) == 1
    assert len((await get("date_from=2024-01-01&date_to=2024-12-31")).json()) == 2
    assert len((await get("location_id=999")).json()) == 0
    hist = (await client.get(f"/api/animals/{cow}/reproductive-history", headers=auth("viewer"))).json()
    assert hist["total_calvings"] == 2 and hist["tag_number"] == "C1"
    assert hist["avg_interval_days"] == float((date(2024, 10, 5) - date(2023, 10, 1)).days)
    assert hist["last_calving_date"] == "2024-10-05" and hist["current_status"] == "calved"
    assert [c["cycle_number"] for c in hist["cycles"]] == [1, 2]
    empty = (await client.get(f"/api/animals/{other}/reproductive-history", headers=auth("viewer"))).json()
    assert empty["total_calvings"] == 0 and empty["avg_interval_days"] is None


# ---------------- BCS & notes ----------------
async def test_bcs_crud_and_filters(client, db_session):
    cow = await make_animal(db_session, "C1")
    r = await post(client, "/api/bcs-records", "data_entry", animal_id=cow, score_date="2024-05-01", bcs=3.5, scored_by="Vet")
    assert r.status_code == 200 and r.json()["bcs"] == 3.5 and r.json()["animal_tag_number"] == "C1"
    assert (await post(client, "/api/bcs-records", animal_id=cow, score_date="2024-05-01", bcs=0.5)).status_code == 422
    assert (await post(client, "/api/bcs-records", animal_id=999, score_date="2024-05-01", bcs=3)).status_code == 404
    await post(client, "/api/bcs-records", animal_id=cow, score_date="2024-08-01", bcs=2.0)
    rid = r.json()["id"]
    assert (await put(client, f"/api/bcs-records/{rid}", bcs=4.0)).json()["bcs"] == 4.0
    get = lambda q: client.get(f"/api/bcs-records?{q}", headers=auth("viewer"))  # noqa: E731
    assert len((await get(f"animal_id={cow}")).json()) == 2
    assert len((await get("date_from=2024-07-01")).json()) == 1
    assert len((await get("location_id=1")).json()) == 2
    assert (await client.delete(f"/api/bcs-records/{rid}", headers=auth("admin"))).status_code == 200
    assert (await client.delete(f"/api/bcs-records/{rid}", headers=auth("admin"))).status_code == 404


async def test_notes_crud_and_ordering(client, db_session):
    cow = await make_animal(db_session, "C1")
    base = f"/api/animals/{cow}/notes"
    old = (await post(client, base, note_date="2024-01-01", content="older", note_type="weight")).json()
    await post(client, base, "data_entry", note_date="2024-06-01", content="newer")
    notes = (await client.get(base, headers=auth("viewer"))).json()
    assert [n["content"] for n in notes] == ["newer", "older"] and notes[0]["note_type"] == "observation"
    upd = await put(client, f"{base}/{old['id']}", content="edited", note_type="incident")
    assert upd.json()["content"] == "edited" and upd.json()["note_type"] == "incident"
    assert (await post(client, base, note_date="2024-01-01", content="")).status_code == 422
    assert (await put(client, f"/api/animals/{cow}/notes/9999", content="x")).status_code == 404
    assert (await client.delete(f"{base}/{old['id']}", headers=auth("admin"))).status_code == 200
    assert len((await client.get(base, headers=auth("viewer"))).json()) == 1
    assert (await client.get("/api/animals/999/notes", headers=auth("viewer"))).status_code == 404


# ---------------- timeline ----------------
async def test_timeline_merges_and_filters_health_events(client, db_session):
    koo, mitamba = await category_id(db_session, CATTLE), await category_id(db_session, CATTLE, "Mitamba")
    cow = await make_animal(db_session, "C1", cat=koo)
    bull = await make_animal(db_session, "B1", sex=AnimalSex.MALE)
    ba = (await post(client, "/api/bull-assignments", bull_animal_id=bull, location_id=1, assigned_date="2024-01-01")).json()
    await cycle(client, cow, service_date="2024-02-01", bull_assignment_id=ba["id"], pd_check_date="2024-03-20",
                pd_result="pregnant", pd_months_pregnant=2, actual_calving_date="2024-11-10", calving_outcome="live_calf")
    await post(client, "/api/bcs-records", animal_id=cow, score_date="2024-05-01", bcs=3.0)
    await post(client, f"/api/animals/{cow}/notes", note_date="2024-04-01", content="limping")
    for when, species, scope, ids, product in [
        (date(2024, 6, 1), CATTLE, CategoryScope.ALL, None, "Triatix"),
        (date(2024, 7, 1), CATTLE, CategoryScope.SPECIFIC, [mitamba], "WrongCat"),
        (date(2024, 8, 1), CATTLE, CategoryScope.SPECIFIC, [koo], "RightCat"),
        (date(2024, 9, 1), SpeciesType.SHEEP, CategoryScope.ALL, None, "WrongSpecies"),
    ]:
        db_session.add(FarmHealthEvent(location_id=FARM_ID, event_type=HealthEventType.DIPPING, event_date=when,
                                       species=species, category_scope=scope, category_ids=ids, product_name=product))
    await db_session.commit()
    items = (await client.get(f"/api/animals/{cow}/timeline", headers=auth("viewer"))).json()
    assert len(items) == 7
    assert [i["date"] for i in items] == sorted((i["date"] for i in items), reverse=True)
    titles = " | ".join(i["title"] for i in items)
    assert "Triatix" in titles and "RightCat" in titles
    assert "WrongCat" not in titles and "WrongSpecies" not in titles
    assert {i["event_category"] for i in items} == {"REPRODUCTION", "HEALTH", "BCS", "NOTE"}
    service = next(i for i in items if i["title"].endswith("service"))
    assert "bull B1" in service["detail"] and service["source_table"] == "reproductive_cycles"
    assert (await client.get("/api/animals/999/timeline", headers=auth("viewer"))).status_code == 404


# ---------------- photos ----------------
@pytest.fixture
def fake_gcs(monkeypatch):
    calls = {"upload": [], "delete": []}
    monkeypatch.setenv("GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(server, "_gcs_upload", lambda path, data, ct: calls["upload"].append((path, ct)))
    monkeypatch.setattr(server, "_gcs_delete", lambda path: calls["delete"].append(path))
    monkeypatch.setattr(server, "_gcs_sign_urls", lambda paths: {p: f"https://signed.test/{p}" for p in paths})
    return calls


def upload(client, cow, data=PNG, ctype="image/png", role="admin", **form):
    return client.post(f"/api/animals/{cow}/photos", files={"file": ("p.png", data, ctype)},
                       data=form, headers=auth(role))


async def test_photos_without_gcs_configured(client, db_session, monkeypatch):
    monkeypatch.delenv("GCS_BUCKET_NAME", raising=False)
    cow = await make_animal(db_session, "C1")
    assert (await upload(client, cow)).status_code == 503
    db_session.add(AnimalPhoto(animal_id=cow, gcs_path=f"animals/{cow}/x.png", is_primary=True))
    await db_session.commit()
    photos = (await client.get(f"/api/animals/{cow}/photos", headers=auth("viewer"))).json()
    assert len(photos) == 1 and photos[0]["photo_url"] is None and "GCS_BUCKET_NAME" in photos[0]["warning"]
    assert (await client.get("/api/animals/999/photos", headers=auth("viewer"))).status_code == 404


async def test_photo_upload_primary_and_signed_urls(client, db_session, fake_gcs):
    cow = await make_animal(db_session, "C1")
    first = await upload(client, cow, role="data_entry", caption="front", taken_date="2024-05-01")
    assert first.status_code == 200
    body = first.json()
    assert body["is_primary"] is True and body["caption"] == "front" and body["taken_date"] == "2024-05-01"
    assert body["gcs_path"].startswith(f"animals/{cow}/") and body["gcs_path"].endswith(".png")
    assert body["photo_url"].startswith("https://signed.test/") and body["warning"] is None
    second = (await upload(client, cow)).json()
    assert second["is_primary"] is False
    assert [c[1] for c in fake_gcs["upload"]] == ["image/png", "image/png"]
    switched = await put(client, f"/api/animals/{cow}/photos/{second['id']}", is_primary=True, caption="side")
    assert switched.json()["is_primary"] is True and switched.json()["caption"] == "side"
    listed = (await client.get(f"/api/animals/{cow}/photos", headers=auth("viewer"))).json()
    assert [p["is_primary"] for p in listed] == [True, False]
    assert listed[0]["id"] == second["id"]


async def test_photo_upload_rejections(client, db_session, fake_gcs, monkeypatch):
    cow = await make_animal(db_session, "C1")
    assert (await upload(client, cow, data=b"hello", ctype="text/plain")).status_code == 415
    assert (await upload(client, cow, data=b"not really a png", ctype="image/png")).status_code == 415
    assert (await upload(client, cow, role="viewer")).status_code == 403
    assert (await upload(client, cow, caption="x" * 300)).status_code == 422
    monkeypatch.setattr(server, "MAX_PHOTO_BYTES", 16)
    assert (await upload(client, cow)).status_code == 413
    assert fake_gcs["upload"] == []  # nothing reached storage
    assert (await db_session.execute(select(AnimalPhoto))).scalars().all() == []


async def test_photo_delete_removes_object_then_row(client, db_session, fake_gcs, monkeypatch):
    cow = await make_animal(db_session, "C1")
    photo = (await upload(client, cow)).json()
    url = f"/api/animals/{cow}/photos/{photo['id']}"

    def boom(path):
        raise RuntimeError("storage down")
    monkeypatch.setattr(server, "_gcs_delete", boom)
    assert (await client.delete(url, headers=auth("admin"))).status_code == 502
    assert len((await db_session.execute(select(AnimalPhoto))).scalars().all()) == 1  # row kept
    monkeypatch.setattr(server, "_gcs_delete", lambda path: fake_gcs["delete"].append(path))
    assert (await client.delete(url, headers=auth("admin"))).status_code == 200
    assert fake_gcs["delete"] == [photo["gcs_path"]]
    assert (await client.delete(url, headers=auth("admin"))).status_code == 404


# ---------------- analytics ----------------
async def test_reproduction_analytics_metrics(client, db_session):
    koo = await category_id(db_session, CATTLE)
    a, b, c, d = [await make_animal(db_session, tag, cat=koo) for tag in "ABCD"]
    await cycle(client, c, actual_calving_date="2024-09-01", calving_outcome="live_calf", status="calved")
    await cycle(client, a, service_date="2025-02-01", pd_check_date="2025-03-15", pd_result="pregnant", status="pregnant")
    await cycle(client, b, pd_check_date="2025-03-20", pd_result="open")
    await cycle(client, c, pd_check_date="2025-02-10", pd_result="pregnant", actual_calving_date="2025-11-20",
                calving_outcome="live_calf", status="calved")
    await cycle(client, d, pd_check_date="2025-04-01", pd_result="pregnant", status="aborted")
    for animal, when, score in [(a, "2024-06-01", 1.0), (a, "2025-05-01", 2.5), (b, "2025-05-01", 3.0),
                                (c, "2025-05-01", 4.5), (d, "2025-05-01", 1.5)]:
        await post(client, "/api/bcs-records", animal_id=animal, score_date=when, bcs=score)
    m = (await client.get("/api/analytics/reproduction?year=2025", headers=auth("viewer"))).json()
    assert m["year"] == 2025 and m["koo_count"] == 50 and m["live_calvings"] == 1
    assert m["calving_rate"] == 0.02
    assert m["conception_rate"] == 0.75           # 3 of 4 PD results
    assert m["abortion_rate"] == 0.3333           # 1 of 3 confirmed pregnancies
    assert m["avg_calving_interval_days"] == float((date(2025, 11, 20) - date(2024, 9, 1)).days)
    assert (m["pregnant_cows"], m["open_cows"]) == (1, 3)
    assert m["bcs_distribution"] == {"1.0-1.5": 1, "2.0-2.5": 1, "3.0-3.5": 1, "4.0+": 1}
    assert [loc["location_name"] for loc in m["by_location"]] == ["Test Farm"]
    assert m["by_location"][0]["live_calvings"] == 1


async def test_reproduction_analytics_uses_daily_log_births_and_animal_status(client, db_session):
    """Ranch data lives in daily-log events and animal fields, not reproductive_cycles."""
    koo = await category_id(db_session, CATTLE)
    a, b, c = [await make_animal(db_session, tag, cat=koo) for tag in ("PA", "OB", "OC")]
    (await db_session.get(Animal, a)).reproductive_status = "pregnant"
    (await db_session.get(Animal, b)).reproductive_status = "open"
    await db_session.commit()
    log = await make_daily_log(db_session, FARM_ID, date(2025, 3, 10))
    out_of_range = await make_daily_log(db_session, FARM_ID, date(2024, 12, 31))
    calf = await category_id(db_session, CATTLE, "Ndama Jike")  # births add calves, not Koo
    for log_id, count in ((log, 2), (out_of_range, 5)):
        r = await post_event(client, log_id, event_type="birth", species="cattle", category_id=calf, count=count)
        assert r.status_code == 200, r.text
    r = await post_event(client, log, event_type="pd_test", species="cattle", category_id=koo, count=3, pd_result="pregnant")
    assert r.status_code == 200, r.text
    r = await post_event(client, log, event_type="pd_test", species="cattle", category_id=koo, count=1, pd_result="open")
    assert r.status_code == 200, r.text

    m = (await client.get("/api/analytics/reproduction?year=2025", headers=auth("viewer"))).json()
    assert m["live_calvings"] == 2 and m["calving_rate"] == 0.04     # 2 births / 50 Koo; 2024 birth excluded
    assert m["conception_rate"] == 0.75                              # 3 pregnant of 4 PD results
    assert (m["pregnant_cows"], m["open_cows"]) == (1, 2)            # from animals.reproductive_status
    assert m["by_location"][0]["live_calvings"] == 2
    sheep = (await client.get("/api/analytics/reproduction?year=2025&species=sheep", headers=auth("viewer"))).json()
    assert (sheep["live_calvings"], sheep["open_cows"], sheep["pregnant_cows"]) == (0, 0, 0)
    cattle = (await client.get("/api/analytics/reproduction?year=2025&species=cattle", headers=auth("viewer"))).json()
    assert cattle["live_calvings"] == 2 and cattle["open_cows"] == 2
    assert (await client.get("/api/analytics/reproduction?species=dragon", headers=auth("viewer"))).status_code == 422


async def test_reproduction_analytics_does_not_double_count_cycle_and_log_calving(client, db_session):
    koo = await category_id(db_session, CATTLE)
    cow = await make_animal(db_session, "DUP", cat=koo)
    log = await make_daily_log(db_session, FARM_ID, date(2025, 3, 10))
    calf = await category_id(db_session, CATTLE, "Ndama Jike")
    r = await post_event(client, log, event_type="birth", species="cattle", category_id=calf, count=1, mother_tag="DUP")
    assert r.status_code == 200, r.text
    await cycle(client, cow, actual_calving_date="2025-03-10", calving_outcome="live_calf", status="calved")
    m = (await client.get("/api/analytics/reproduction?year=2025", headers=auth("viewer"))).json()
    assert m["live_calvings"] == 1                                   # same calving recorded twice
    await cycle(client, cow, actual_calving_date="2025-09-01", calving_outcome="live_calf", status="calved")
    m = (await client.get("/api/analytics/reproduction?year=2025", headers=auth("viewer"))).json()
    assert m["live_calvings"] == 2                                   # a different, cycle-only calving still counts


async def test_reproduction_analytics_scoping_and_fallback(client, db_session):
    other_loc = await make_location(db_session, "Empty Farm")
    await make_stock(db_session, FARM_ID, CATTLE, await category_id(db_session, CATTLE), 40)
    get = lambda q: client.get(f"/api/analytics/reproduction?{q}", headers=auth("viewer"))  # noqa: E731
    fallback = (await get("year=2023")).json()  # opening balance starts 2024: falls back to StockLevel
    assert fallback["koo_count"] == 40 and fallback["calving_rate"] == 0.0
    scoped = (await get(f"year=2025&location_id={other_loc}")).json()
    assert scoped["koo_count"] == 0 and scoped["calving_rate"] is None and len(scoped["by_location"]) == 1
    both = (await get("year=2025")).json()
    assert {loc["location_name"] for loc in both["by_location"]} == {"Test Farm", "Empty Farm"}
    assert (await get("")).json()["year"] == date.today().year
    assert (await get("year=1900")).status_code == 422


async def test_animal_list_exposes_last_calving_date(client, db_session):
    animal_id = await make_animal(db_session, "CALV-1")
    animal = await db_session.get(Animal, animal_id)
    animal.last_calving_date = date(2026, 3, 4)
    await db_session.commit()
    rows = (await client.get("/api/animals", headers=auth("viewer"))).json()
    row = next(r for r in rows if r["tag_number"] == "CALV-1")
    assert row["last_calving_date"] == "2026-03-04"
    other = await make_animal(db_session, "CALV-2")
    rows = (await client.get("/api/animals", headers=auth("viewer"))).json()
    assert next(r for r in rows if r["id"] == other)["last_calving_date"] is None
