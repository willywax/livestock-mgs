"""Unit tests for registry_sync.py — outbox state transitions with the Registry mocked."""
import asyncio
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from models import EventType, RegistrySyncAction, RegistrySyncOutbox, RegistrySyncState
from registry_client import RegistryConflict, RegistryNotFound, RegistryUnavailable
import registry_sync


def _run(coro):
    return asyncio.run(coro)


def _make_row(action=RegistrySyncAction.STATUS_CHANGE, **kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        source_event_id=str(uuid.uuid4()),
        tag_id="TAG-001",
        action=action,
        intended_status="ACTIVE",
        previous_status=None,
        payload={"foo": "bar"},
        state=RegistrySyncState.PENDING,
        attempts=0,
        last_error=None,
        created_at=datetime.now(timezone.utc),
        sent_at=None,
    )
    defaults.update(kwargs)
    return RegistrySyncOutbox(**defaults)


class FakeClient:
    """Stand-in for RegistryClient: each method returns/raises a canned outcome."""

    def __init__(self, *, post_status=None, post_event=None, revert=None):
        self._post_status = post_status
        self._post_event = post_event
        self._revert = revert
        self.calls = []

    async def post_status(self, actor_name, tag_id, *, event_type, new_status, source_event_id, event_date, expected_current_status=None, note=None):
        self.calls.append(("post_status", actor_name, tag_id, event_type, new_status, source_event_id))
        if isinstance(self._post_status, Exception):
            raise self._post_status
        return self._post_status

    async def post_event(self, actor_name, tag_id, *, event_type, source_event_id, event_date, note=None, value=None):
        self.calls.append(("post_event", actor_name, tag_id, event_type, source_event_id))
        if isinstance(self._post_event, Exception):
            raise self._post_event
        return self._post_event

    async def revert(self, actor_name, *, source_event_id, reason):
        self.calls.append(("revert", actor_name, source_event_id, reason))
        if isinstance(self._revert, Exception):
            raise self._revert
        return self._revert


class ScriptedClient:
    """Like FakeClient, but the outcome is looked up by tag_id — for multi-row drain tests.

    (revert has no tag_id in its real signature, so ScriptedClient keys revert lookups by
    source_event_id instead — tests using revert should key outcomes_by_tag accordingly.)
    """

    def __init__(self, outcomes_by_tag):
        self.outcomes_by_tag = outcomes_by_tag

    async def _resolve(self, key):
        outcome = self.outcomes_by_tag[key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def post_status(self, actor_name, tag_id, *, event_type, new_status, source_event_id, event_date, expected_current_status=None, note=None):
        return await self._resolve(tag_id)

    async def post_event(self, actor_name, tag_id, *, event_type, source_event_id, event_date, note=None, value=None):
        return await self._resolve(tag_id)

    async def revert(self, actor_name, *, source_event_id, reason):
        return await self._resolve(source_event_id)


# ---------------------------------------------------------------------------
# _attempt_delivery
# ---------------------------------------------------------------------------

def test_attempt_delivery_success_marks_sent():
    row = _make_row()
    client = FakeClient(post_status={"ok": True})

    _run(registry_sync._attempt_delivery(client, row))

    assert row.state == RegistrySyncState.SENT
    assert row.sent_at is not None
    assert row.last_error is None
    assert row.attempts == 0
    assert client.calls[0][0] == "post_status"
    assert client.calls[0][1] == registry_sync.SYNC_ACTOR_NAME


def test_attempt_delivery_conflict_marks_conflict_and_stores_current_status():
    row = _make_row(action=RegistrySyncAction.EVENT, intended_status=None)
    client = FakeClient(post_event=RegistryConflict(current_status="SOLD"))

    _run(registry_sync._attempt_delivery(client, row))

    assert row.state == RegistrySyncState.CONFLICT
    assert "SOLD" in row.last_error
    assert row.attempts == 1


def test_attempt_delivery_not_found_marks_failed_immediately():
    row = _make_row(action=RegistrySyncAction.REVERT, previous_status="ACTIVE")
    client = FakeClient(revert=RegistryNotFound(detail={"error": "no such tag"}))

    _run(registry_sync._attempt_delivery(client, row))

    assert row.state == RegistrySyncState.FAILED
    assert row.attempts == 1


def test_attempt_delivery_unavailable_stays_pending_below_max_attempts():
    row = _make_row(attempts=3)
    client = FakeClient(post_status=RegistryUnavailable("timeout"))

    _run(registry_sync._attempt_delivery(client, row))

    assert row.state == RegistrySyncState.PENDING
    assert row.attempts == 4
    assert "timeout" in row.last_error


def test_attempt_delivery_unavailable_moves_to_failed_at_max_attempts():
    row = _make_row(attempts=registry_sync.MAX_ATTEMPTS - 1)
    client = FakeClient(post_status=RegistryUnavailable("still down"))

    _run(registry_sync._attempt_delivery(client, row))

    assert row.state == RegistrySyncState.FAILED
    assert row.attempts == registry_sync.MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# enqueue_and_send
# ---------------------------------------------------------------------------

def test_enqueue_and_send_commits_and_returns_row(monkeypatch):
    row = _make_row()
    fake_client = FakeClient(post_status={"ok": True})
    monkeypatch.setattr(registry_sync, "RegistryClient", lambda: fake_client)

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    result = _run(registry_sync.enqueue_and_send(session, row))

    assert result is row
    assert row.state == RegistrySyncState.SENT
    session.add.assert_called_once_with(row)
    session.commit.assert_awaited_once()


def test_enqueue_and_send_leaves_pending_on_unavailable(monkeypatch):
    row = _make_row()
    fake_client = FakeClient(post_status=RegistryUnavailable("connection refused"))
    monkeypatch.setattr(registry_sync, "RegistryClient", lambda: fake_client)

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    _run(registry_sync.enqueue_and_send(session, row))

    assert row.state == RegistrySyncState.PENDING
    assert row.attempts == 1
    session.commit.assert_awaited_once()


def test_enqueue_and_send_marks_conflict_and_does_not_retry(monkeypatch):
    row = _make_row(action=RegistrySyncAction.EVENT, intended_status=None)
    fake_client = FakeClient(post_event=RegistryConflict(current_status="DEAD"))
    monkeypatch.setattr(registry_sync, "RegistryClient", lambda: fake_client)

    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    _run(registry_sync.enqueue_and_send(session, row))

    assert row.state == RegistrySyncState.CONFLICT
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# drain_outbox
# ---------------------------------------------------------------------------

def test_drain_outbox_applies_per_row_transitions_and_counts(monkeypatch):
    row_sent = _make_row(tag_id="T-SENT")
    row_conflict = _make_row(tag_id="T-CONFLICT", action=RegistrySyncAction.EVENT, intended_status=None)
    row_failed = _make_row(tag_id="T-NOTFOUND", source_event_id="EVT-NOTFOUND", action=RegistrySyncAction.REVERT, previous_status="ACTIVE")
    row_pending = _make_row(tag_id="T-PENDING", attempts=1)

    scripted = ScriptedClient(
        {
            "T-SENT": {"ok": True},
            "T-CONFLICT": RegistryConflict(current_status="SOLD"),
            "EVT-NOTFOUND": RegistryNotFound(detail="gone"),
            "T-PENDING": RegistryUnavailable("timeout"),
        }
    )
    monkeypatch.setattr(registry_sync, "RegistryClient", lambda: scripted)

    rows = [row_sent, row_conflict, row_failed, row_pending]
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock

    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()

    result = _run(registry_sync.drain_outbox(session))

    assert result == {"processed": 4, "sent": 1, "conflict": 1, "failed": 1, "pending": 1}
    assert row_sent.state == RegistrySyncState.SENT
    assert row_conflict.state == RegistrySyncState.CONFLICT
    assert row_failed.state == RegistrySyncState.FAILED
    assert row_pending.state == RegistrySyncState.PENDING
    session.commit.assert_awaited_once()


def test_drain_outbox_moves_exhausted_row_to_failed(monkeypatch):
    row = _make_row(tag_id="T-EXHAUSTED", attempts=registry_sync.MAX_ATTEMPTS - 1)
    scripted = ScriptedClient({"T-EXHAUSTED": RegistryUnavailable("still down")})
    monkeypatch.setattr(registry_sync, "RegistryClient", lambda: scripted)

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [row]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock

    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()

    result = _run(registry_sync.drain_outbox(session))

    assert result == {"processed": 1, "sent": 0, "conflict": 0, "failed": 1, "pending": 0}
    assert row.state == RegistrySyncState.FAILED
    assert row.attempts == registry_sync.MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# build_outbox_row_for_event
# ---------------------------------------------------------------------------

def test_build_outbox_row_returns_none_without_registry_previous_status():
    row = registry_sync.build_outbox_row_for_event(
        event_type=EventType.DEATH,
        event_id=1,
        log_date=date(2026, 8, 26),
        note="found in the field",
        animal_tags="TAG-1",
        mother_tag=None,
        registry_previous_status=None,
    )
    assert row is None


def test_build_outbox_row_for_death():
    row = registry_sync.build_outbox_row_for_event(
        event_type=EventType.DEATH,
        event_id=42,
        log_date=date(2026, 8, 26),
        note="found in the field",
        animal_tags="TAG-1, TAG-2",
        mother_tag=None,
        registry_previous_status="ACTIVE",
    )
    assert row.source_event_id == "death:42"
    assert row.tag_id == "TAG-1"
    assert row.action == RegistrySyncAction.STATUS_CHANGE
    assert row.intended_status == registry_sync.DEATH_STATUS
    assert row.previous_status == "ACTIVE"
    assert row.payload == {
        "registry_event_type": "DEATH",
        "event_date": "2026-08-26T00:00:00+00:00",
        "note": "found in the field",
    }


def test_build_outbox_row_for_sold():
    row = registry_sync.build_outbox_row_for_event(
        event_type=EventType.SOLD,
        event_id=7,
        log_date=date(2026, 8, 26),
        note=None,
        animal_tags="TAG-9",
        mother_tag=None,
        registry_previous_status="ACTIVE",
    )
    assert row.source_event_id == "sold:7"
    assert row.tag_id == "TAG-9"
    assert row.action == RegistrySyncAction.STATUS_CHANGE
    assert row.intended_status == registry_sync.SOLD_STATUS
    assert row.previous_status == "ACTIVE"


def test_build_outbox_row_for_birth_targets_dam_tag():
    row = registry_sync.build_outbox_row_for_event(
        event_type=EventType.BIRTH,
        event_id=100,
        log_date=date(2026, 8, 26),
        note="twins",
        animal_tags=None,
        mother_tag="DAM-1",
        registry_previous_status="ACTIVE",
    )
    assert row.source_event_id == "birth:100"
    assert row.tag_id == "DAM-1"
    assert row.action == RegistrySyncAction.EVENT
    assert row.intended_status is None
    assert row.previous_status is None
    assert row.payload == {"event_type": "CALVED", "event_date": "2026-08-26T00:00:00+00:00", "note": "twins"}


def test_build_outbox_row_returns_none_when_tag_missing():
    row = registry_sync.build_outbox_row_for_event(
        event_type=EventType.BIRTH,
        event_id=1,
        log_date=date(2026, 8, 26),
        note=None,
        animal_tags=None,
        mother_tag="",
        registry_previous_status="ACTIVE",
    )
    assert row is None


def test_build_outbox_row_returns_none_for_other_event_types():
    row = registry_sync.build_outbox_row_for_event(
        event_type=EventType.TRANSFER,
        event_id=1,
        log_date=date(2026, 8, 26),
        note=None,
        animal_tags="TAG-1",
        mother_tag=None,
        registry_previous_status="ACTIVE",
    )
    assert row is None


# ---------------------------------------------------------------------------
# conflict_warning_message
# ---------------------------------------------------------------------------

def test_conflict_warning_message_uses_registry_current_status():
    row = _make_row(action=RegistrySyncAction.STATUS_CHANGE, previous_status="ACTIVE")
    row.current_status_from_registry = "SOLD"

    message = registry_sync.conflict_warning_message(row)

    assert message == "Saved, but the Herd Tag Registry shows this tag as SOLD. It was not updated there."


def test_conflict_warning_message_falls_back_to_previous_status():
    row = _make_row(action=RegistrySyncAction.STATUS_CHANGE, previous_status="ACTIVE")
    # current_status_from_registry not set (e.g. re-loaded row) — falls back
    message = registry_sync.conflict_warning_message(row)
    assert "ACTIVE" in message


# ---------------------------------------------------------------------------
# build_outbox_row_for_tag_assignment
# ---------------------------------------------------------------------------

def test_build_outbox_row_for_tag_assignment():
    row = registry_sync.build_outbox_row_for_tag_assignment(animal_id=55, tag_id="TAG-NEW")

    assert row.source_event_id == "tag_assigned:55"
    assert row.tag_id == "TAG-NEW"
    assert row.action == RegistrySyncAction.EVENT
    assert row.intended_status is None
    assert row.previous_status is None
    assert row.payload["event_type"] == "TAG_ASSIGNED"
    assert "event_date" in row.payload


# ---------------------------------------------------------------------------
# retry_outbox_row
# ---------------------------------------------------------------------------

def test_retry_outbox_row_resets_state_and_attempts():
    row = _make_row(state=RegistrySyncState.FAILED, attempts=10, last_error="still down")

    session = MagicMock()
    session.get = AsyncMock(return_value=row)
    session.commit = AsyncMock()

    result = _run(registry_sync.retry_outbox_row(session, row.id))

    assert result is row
    assert row.state == RegistrySyncState.PENDING
    assert row.attempts == 0
    assert row.last_error is None
    session.commit.assert_awaited_once()


def test_retry_outbox_row_returns_none_when_missing():
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()

    result = _run(registry_sync.retry_outbox_row(session, uuid.uuid4()))

    assert result is None
    session.commit.assert_not_awaited()
