"""Unit tests for registry_report.py — the Registry's reconcile call is mocked."""
import asyncio
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from models import RegistrySyncAction, RegistrySyncOutbox, RegistrySyncState
from registry_client import RegistryUnavailable
import registry_report


def _run(coro):
    return asyncio.run(coro)


def _make_row(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        source_event_id=str(uuid.uuid4()),
        tag_id="TAG-1",
        action=RegistrySyncAction.STATUS_CHANGE,
        intended_status="DECEASED",
        previous_status="ACTIVE",
        payload={},
        state=RegistrySyncState.SENT,
        attempts=1,
        last_error=None,
        created_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return RegistrySyncOutbox(**defaults)


def _session_returning(outbox_rows_by_query):
    """outbox_rows_by_query: a list of row-lists, consumed in call order of session.execute."""
    calls = iter(outbox_rows_by_query)

    async def _execute(*args, **kwargs):
        rows = next(calls)
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)
    return session


class FakeReconcileClient:
    def __init__(self, *, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def reconcile(self, actor_name, *, since):
        if self._exc is not None:
            raise self._exc
        return self._response


def test_report_includes_conflict_and_failed_outbox_rows(monkeypatch):
    conflict_row = _make_row(state=RegistrySyncState.CONFLICT)
    failed_row = _make_row(state=RegistrySyncState.FAILED, tag_id="TAG-2")
    sent_row = _make_row(state=RegistrySyncState.SENT, tag_id="TAG-3")  # should be excluded

    session = _session_returning([
        [conflict_row, failed_row],  # outbox_issues query
        [sent_row],                  # local status-change rows since `since`
    ])
    monkeypatch.setattr(registry_report, "RegistryClient", lambda: FakeReconcileClient(response=[]))

    report = _run(registry_report.build_sync_report(session, date(2026, 1, 1)))

    assert report.outbox_issues == [conflict_row, failed_row]


def test_report_flags_registry_record_with_no_local_row(monkeypatch):
    session = _session_returning([
        [],  # no outbox issues
        [],  # no local status-change rows
    ])
    monkeypatch.setattr(
        registry_report, "RegistryClient",
        lambda: FakeReconcileClient(response=[{"tag_id": "TAG-9", "status": "DECEASED"}]),
    )

    report = _run(registry_report.build_sync_report(session, date(2026, 1, 1)))

    assert len(report.reconcile_mismatches) == 1
    mismatch = report.reconcile_mismatches[0]
    assert mismatch.tag_id == "TAG-9"
    assert mismatch.kind == "registry_no_local"
    assert mismatch.registry_status == "DECEASED"
    assert not report.reconcile_unavailable


def test_report_flags_local_row_with_no_registry_record(monkeypatch):
    local_row = _make_row(tag_id="TAG-5", intended_status="DECEASED")
    session = _session_returning([
        [],
        [local_row],
    ])
    monkeypatch.setattr(registry_report, "RegistryClient", lambda: FakeReconcileClient(response=[]))

    report = _run(registry_report.build_sync_report(session, date(2026, 1, 1)))

    assert len(report.reconcile_mismatches) == 1
    mismatch = report.reconcile_mismatches[0]
    assert mismatch.tag_id == "TAG-5"
    assert mismatch.kind == "local_no_registry"
    assert mismatch.local_status == "DECEASED"


def test_report_flags_status_mismatch(monkeypatch):
    local_row = _make_row(tag_id="TAG-7", intended_status="DECEASED")
    session = _session_returning([
        [],
        [local_row],
    ])
    monkeypatch.setattr(
        registry_report, "RegistryClient",
        lambda: FakeReconcileClient(response=[{"tag_id": "TAG-7", "status": "SOLD"}]),
    )

    report = _run(registry_report.build_sync_report(session, date(2026, 1, 1)))

    assert len(report.reconcile_mismatches) == 1
    mismatch = report.reconcile_mismatches[0]
    assert mismatch.kind == "status_mismatch"
    assert mismatch.local_status == "DECEASED"
    assert mismatch.registry_status == "SOLD"


def test_report_matching_records_produce_no_mismatch(monkeypatch):
    local_row = _make_row(tag_id="TAG-8", intended_status="DECEASED")
    session = _session_returning([
        [],
        [local_row],
    ])
    monkeypatch.setattr(
        registry_report, "RegistryClient",
        lambda: FakeReconcileClient(response=[{"tag_id": "TAG-8", "status": "DECEASED"}]),
    )

    report = _run(registry_report.build_sync_report(session, date(2026, 1, 1)))

    assert report.reconcile_mismatches == []


def test_report_surfaces_reconcile_unavailable_without_swallowing(monkeypatch):
    local_row = _make_row(tag_id="TAG-8", intended_status="DECEASED")
    session = _session_returning([
        [],
        [local_row],
    ])
    monkeypatch.setattr(
        registry_report, "RegistryClient",
        lambda: FakeReconcileClient(exc=RegistryUnavailable("timeout")),
    )

    report = _run(registry_report.build_sync_report(session, date(2026, 1, 1)))

    assert report.reconcile_unavailable is True
    assert "timeout" in report.reconcile_error
    # Cross-check is skipped entirely rather than silently reporting false mismatches.
    assert report.reconcile_mismatches == []


def test_report_accepts_items_wrapped_reconcile_response(monkeypatch):
    session = _session_returning([
        [],
        [],
    ])
    monkeypatch.setattr(
        registry_report, "RegistryClient",
        lambda: FakeReconcileClient(response={"items": [{"tag_id": "TAG-9", "status": "SOLD"}]}),
    )

    report = _run(registry_report.build_sync_report(session, date(2026, 1, 1)))

    assert len(report.reconcile_mismatches) == 1
    assert report.reconcile_mismatches[0].tag_id == "TAG-9"
