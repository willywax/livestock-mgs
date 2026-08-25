"""Builds the admin-facing Registry sync report (GET /api/internal/sync/report).

Combines two independent checks:
  1. Local trouble: registry_sync_outbox rows stuck in CONFLICT or FAILED.
  2. Cross-check: our death/sale status-change outbox rows since `since` against the
     Registry's own /api/integration/reconcile feed, to catch drift that isn't visible
     from our side alone (e.g. the Registry shows a tag DECEASED that ShambaManager never
     recorded an outbox row for at all).

NOTE: the Registry's exact /api/integration/reconcile response shape isn't available in
this repo (see registry_client.reconcile) — this assumes a list of
{"tag_id": ..., "status": ...} dicts (or {"items": [...]}) covering tags whose status
changed since `since`. Adjust `_parse_reconcile_response` if the real shape differs.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import RegistrySyncAction, RegistrySyncOutbox, RegistrySyncState
from registry_client import RegistryClient, RegistryUnavailable

logger = logging.getLogger(__name__)


@dataclass
class ReconcileMismatch:
    tag_id: str
    kind: str  # "local_no_registry" | "registry_no_local" | "status_mismatch"
    detail: str
    local_status: Optional[str] = None
    registry_status: Optional[str] = None


@dataclass
class SyncReport:
    since: date
    generated_at: datetime
    outbox_issues: list = field(default_factory=list)  # list[RegistrySyncOutbox]
    reconcile_mismatches: list = field(default_factory=list)  # list[ReconcileMismatch]
    reconcile_unavailable: bool = False
    reconcile_error: Optional[str] = None


def _parse_reconcile_response(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("items", [])
    return []


async def build_sync_report(
    session: AsyncSession,
    since: date,
    actor_name: str = "ShambaManager Sync",
) -> SyncReport:
    outbox_result = await session.execute(
        select(RegistrySyncOutbox)
        .where(RegistrySyncOutbox.state.in_([RegistrySyncState.CONFLICT, RegistrySyncState.FAILED]))
        .order_by(RegistrySyncOutbox.created_at.asc())
    )
    outbox_issues = list(outbox_result.scalars().all())

    since_dt = _combine_since(since)
    status_change_result = await session.execute(
        select(RegistrySyncOutbox)
        .where(
            RegistrySyncOutbox.action == RegistrySyncAction.STATUS_CHANGE,
            RegistrySyncOutbox.created_at >= since_dt,
        )
    )
    local_by_tag = {row.tag_id: row for row in status_change_result.scalars().all()}

    reconcile_mismatches = []
    reconcile_unavailable = False
    reconcile_error = None
    registry_by_tag = {}

    client = RegistryClient()
    try:
        raw = await client.reconcile(actor_name, since=since.isoformat())
        for rec in _parse_reconcile_response(raw):
            tag_id = rec.get("tag_id")
            if tag_id:
                registry_by_tag[tag_id] = rec
    except RegistryUnavailable as exc:
        reconcile_unavailable = True
        reconcile_error = str(exc)
        logger.warning("Registry reconcile call failed, report will omit cross-checks: %s", exc)

    if not reconcile_unavailable:
        for tag_id, rec in registry_by_tag.items():
            if tag_id not in local_by_tag:
                reconcile_mismatches.append(ReconcileMismatch(
                    tag_id=tag_id,
                    kind="registry_no_local",
                    registry_status=rec.get("status"),
                    detail="Registry shows a status change for this tag with no matching ShambaManager sync record.",
                ))

        for tag_id, row in local_by_tag.items():
            rec = registry_by_tag.get(tag_id)
            if rec is None:
                reconcile_mismatches.append(ReconcileMismatch(
                    tag_id=tag_id,
                    kind="local_no_registry",
                    local_status=row.intended_status,
                    detail="ShambaManager recorded a status-change sync for this tag, but the Registry has no matching record.",
                ))
            elif rec.get("status") != row.intended_status:
                reconcile_mismatches.append(ReconcileMismatch(
                    tag_id=tag_id,
                    kind="status_mismatch",
                    local_status=row.intended_status,
                    registry_status=rec.get("status"),
                    detail="ShambaManager and the Registry disagree on this tag's current status.",
                ))

    return SyncReport(
        since=since,
        generated_at=datetime.now(timezone.utc),
        outbox_issues=outbox_issues,
        reconcile_mismatches=reconcile_mismatches,
        reconcile_unavailable=reconcile_unavailable,
        reconcile_error=reconcile_error,
    )


def _combine_since(since: date) -> datetime:
    return datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)
