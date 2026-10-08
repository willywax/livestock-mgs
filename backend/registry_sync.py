"""Delivers registry_sync_outbox rows to the external tag Registry.

Write-side syncs (status changes / events / reverts) are performed on behalf of
ShambaManager itself, not any one logged-in user, so they're all attributed to a
fixed actor name — distinct from the interactive picker lookup in server.py, which
uses the real logged-in user's name.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import EventType, RegistrySyncOutbox, RegistrySyncAction, RegistrySyncState
from registry_client import RegistryClient, RegistryConflict, RegistryNotFound, RegistryUnavailable

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 10
SYNC_ACTOR_NAME = "ShambaManager Sync"

# The Registry's own status vocabulary for these terminal ShambaManager events.
# Configurable since the Registry may not use the same strings as our AnimalStatus enum.
DEATH_STATUS = os.environ.get("REGISTRY_DEATH_STATUS", "DECEASED")
SOLD_STATUS = os.environ.get("REGISTRY_SOLD_STATUS", "SOLD")


async def _attempt_delivery(client: RegistryClient, row: RegistrySyncOutbox) -> None:
    """Attempts one Registry call for `row` and mutates its state fields in place.

    Does not commit — the caller owns the transaction.
    """
    payload = row.payload or {}
    try:
        if row.action == RegistrySyncAction.STATUS_CHANGE:
            await client.post_status(
                SYNC_ACTOR_NAME,
                row.tag_id,
                event_type=payload.get("registry_event_type", "DEATH"),
                new_status=row.intended_status,
                source_event_id=row.source_event_id,
                event_date=payload.get("event_date"),
                expected_current_status=row.previous_status,
                note=payload.get("note"),
            )
        elif row.action == RegistrySyncAction.EVENT:
            await client.post_event(
                SYNC_ACTOR_NAME,
                row.tag_id,
                event_type=payload.get("event_type", "EVENT"),
                source_event_id=row.source_event_id,
                event_date=payload.get("event_date"),
                note=payload.get("note"),
            )
        elif row.action == RegistrySyncAction.REVERT:
            await client.revert(
                SYNC_ACTOR_NAME,
                source_event_id=row.source_event_id,
                reason=payload.get("reason", "Reverted by ShambaManager"),
            )
        else:
            raise ValueError(f"Unknown outbox action: {row.action}")

    except RegistryConflict as exc:
        row.attempts += 1
        row.state = RegistrySyncState.CONFLICT
        row.last_error = f"conflict: current_status={exc.current_status}"
        # Transient, not a mapped column — lets the caller build a user-facing message
        # without re-parsing last_error, within this same request only.
        row.current_status_from_registry = exc.current_status
        return

    except RegistryNotFound as exc:
        # Retrying won't make a missing tag appear — terminal, not retried.
        row.attempts += 1
        row.state = RegistrySyncState.FAILED
        row.last_error = f"not found: {exc.detail}"
        return

    except RegistryUnavailable as exc:
        row.attempts += 1
        row.last_error = str(exc)
        if row.attempts >= MAX_ATTEMPTS:
            row.state = RegistrySyncState.FAILED
        # else: leave PENDING for the next drain
        return

    row.state = RegistrySyncState.SENT
    row.sent_at = datetime.now(timezone.utc)
    row.last_error = None


async def enqueue_and_send(session: AsyncSession, outbox_row: RegistrySyncOutbox) -> RegistrySyncOutbox:
    """Attempts immediate delivery of an outbox row right after its insert transaction committed.

    State transitions:
      success             -> SENT (+ sent_at)
      RegistryConflict     -> CONFLICT, not retried
      RegistryNotFound     -> FAILED, not retried
      RegistryUnavailable  -> stays PENDING (attempts incremented); retried by /sync/drain
    """
    client = RegistryClient()
    await _attempt_delivery(client, outbox_row)
    session.add(outbox_row)
    await session.commit()
    return outbox_row


async def drain_outbox(session: AsyncSession, limit: int = 50) -> dict:
    """Retries up to `limit` PENDING rows (attempts < MAX_ATTEMPTS), oldest first."""
    result = await session.execute(
        select(RegistrySyncOutbox)
        .where(
            RegistrySyncOutbox.state == RegistrySyncState.PENDING,
            RegistrySyncOutbox.attempts < MAX_ATTEMPTS,
        )
        .order_by(RegistrySyncOutbox.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = result.scalars().all()

    client = RegistryClient()
    counts = {"sent": 0, "conflict": 0, "failed": 0, "pending": 0}
    for row in rows:
        await _attempt_delivery(client, row)
        if row.state == RegistrySyncState.SENT:
            counts["sent"] += 1
        elif row.state == RegistrySyncState.CONFLICT:
            counts["conflict"] += 1
        elif row.state == RegistrySyncState.FAILED:
            counts["failed"] += 1
        else:
            counts["pending"] += 1

    await session.commit()
    return {"processed": len(rows), **counts}


def build_outbox_row_for_event(
    *,
    event_type: EventType,
    event_id: int,
    log_date,
    note: Optional[str],
    animal_tags: Optional[str],
    mother_tag: Optional[str],
    registry_previous_status: Optional[str],
) -> Optional[RegistrySyncOutbox]:
    """Builds (but does not insert or send) an outbox row for a just-created domain event.

    Only builds a row when `registry_previous_status` is present — that's the signal from
    the frontend that RegistryTagPicker was actually used to select the tag for this event,
    as opposed to (for death/sold) free-text animal_tags entry or (for birth) a hand-typed
    mother_tag that doesn't necessarily correspond to a real Registry tag.

    Caller is responsible for inserting the row in the same transaction as the domain event
    and, once that transaction commits, calling enqueue_and_send.
    """
    if not registry_previous_status:
        return None

    # The Registry's schemas require a full date-time, not a bare date.
    event_date_str = datetime.combine(log_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()

    if event_type == EventType.DEATH:
        tag_id = (animal_tags or "").split(",")[0].strip()
        if not tag_id:
            return None
        return RegistrySyncOutbox(
            source_event_id=f"death:{event_id}",
            tag_id=tag_id,
            action=RegistrySyncAction.STATUS_CHANGE,
            intended_status=DEATH_STATUS,
            previous_status=registry_previous_status,
            payload={
                "registry_event_type": "DEATH",
                "event_date": event_date_str,
                "note": note,
            },
        )

    if event_type == EventType.SOLD:
        tag_id = (animal_tags or "").split(",")[0].strip()
        if not tag_id:
            return None
        return RegistrySyncOutbox(
            source_event_id=f"sold:{event_id}",
            tag_id=tag_id,
            action=RegistrySyncAction.STATUS_CHANGE,
            intended_status=SOLD_STATUS,
            previous_status=registry_previous_status,
            payload={
                "registry_event_type": "SALE",
                "event_date": event_date_str,
                "note": note,
            },
        )

    if event_type == EventType.BIRTH:
        tag_id = (mother_tag or "").strip()
        if not tag_id:
            return None
        return RegistrySyncOutbox(
            source_event_id=f"birth:{event_id}",
            tag_id=tag_id,
            action=RegistrySyncAction.EVENT,
            intended_status=None,
            previous_status=None,
            payload={"event_type": "CALVED", "event_date": event_date_str, "note": note},
        )

    return None


def conflict_warning_message(outbox_row: RegistrySyncOutbox) -> str:
    """User-facing warning for the success screen when an outbox row landed in CONFLICT."""
    current_status = getattr(outbox_row, "current_status_from_registry", None) or outbox_row.previous_status or "a different status"
    return (
        f"Saved, but the Herd Tag Registry shows this tag as {current_status}. "
        "It was not updated there."
    )


async def upsert_outbox_row(session: AsyncSession, new_row: RegistrySyncOutbox) -> RegistrySyncOutbox:
    """Inserts `new_row`, or — if a row with the same source_event_id already exists (e.g.
    correcting a previously-linked tag via edit) — updates that row in place and re-queues
    it instead of violating the unique constraint on source_event_id.

    Caller adds the returned row to the session (already tracked if updated in place, or
    freshly added here if new) and commits.
    """
    result = await session.execute(
        select(RegistrySyncOutbox).where(RegistrySyncOutbox.source_event_id == new_row.source_event_id)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        session.add(new_row)
        return new_row

    existing.tag_id = new_row.tag_id
    existing.action = new_row.action
    existing.intended_status = new_row.intended_status
    existing.previous_status = new_row.previous_status
    existing.payload = new_row.payload
    existing.state = RegistrySyncState.PENDING
    existing.attempts = 0
    existing.last_error = None
    existing.sent_at = None
    return existing


def build_outbox_row_for_tag_assignment(*, animal_id: int, tag_id: str) -> RegistrySyncOutbox:
    """Outbox row for assigning a Registry tag to a calf once it's been physically tagged
    (see POST /api/animals/{id}/assign-registry-tag). Always built — unlike the
    death/sold/birth rows, this endpoint only runs once a tag has actually been picked."""
    return RegistrySyncOutbox(
        source_event_id=f"tag_assigned:{animal_id}",
        tag_id=tag_id,
        action=RegistrySyncAction.EVENT,
        intended_status=None,
        previous_status=None,
        payload={"event_type": "TAG_ASSIGNED", "event_date": datetime.now(timezone.utc).isoformat(), "note": None},
    )


async def retry_outbox_row(session: AsyncSession, outbox_id) -> Optional[RegistrySyncOutbox]:
    """Manual retry from the admin Registry Sync page: re-queues one row to PENDING with
    attempts reset. Does not attempt delivery inline — the next /sync/drain cycle sends it."""
    row = await session.get(RegistrySyncOutbox, outbox_id)
    if row is None:
        return None
    row.state = RegistrySyncState.PENDING
    row.attempts = 0
    row.last_error = None
    await session.commit()
    return row
