"""Physical tag reconciliation sessions."""
from datetime import date
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Animal, AnimalIdentifier, AnimalIdentifierType, AnimalStatus, Location, ReconciliationEntry, ReconciliationSession, User, UserRole
from schemas import ReconciliationResultResponse, ReconciliationSessionCreate, ReconciliationSessionSummary
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.common import _ANY_ROLE

router = APIRouter()

# ---------- Physical tag reconciliation ----------
async def _load_reconciliation_session(db, session_id):
    session = await db.get(ReconciliationSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Reconciliation session not found")
    return session


async def _reconciliation_result(db, session):
    entries = (await db.execute(select(ReconciliationEntry).where(
        ReconciliationEntry.session_id == session.id,
    ).order_by(ReconciliationEntry.id))).scalars().all()
    matched_ids = {e.matched_animal_id for e in entries if e.matched_animal_id is not None}
    animals = (await db.execute(select(Animal).where(
        or_(Animal.id.in_(matched_ids), and_(
            Animal.location_id == session.location_id, Animal.status == AnimalStatus.ACTIVE,
        )),
    ).options(selectinload(Animal.category)).order_by(Animal.id))).scalars().all()
    # The entry schema stores the match, but not its provenance. Infer the
    # displayed match method from the currently active identifiers.
    identifiers = (await db.execute(select(AnimalIdentifier).where(
        AnimalIdentifier.animal_id.in_(matched_ids), AnimalIdentifier.is_active.is_(True),
    ))).scalars().all()
    identifier_keys = {(i.animal_id, i.id_type, i.id_value) for i in identifiers}
    via_identifier = {e.matched_animal_id for e in entries
                      if e.id_type != AnimalIdentifierType.VISUAL_TAG
                      or (e.matched_animal_id, e.id_type, e.raw_value) in identifier_keys}
    matched = [dict(animal_id=a.id, tag_number=a.tag_number, species=a.species,
                    matched_via="identifier" if a.id in via_identifier else "tag_number")
               for a in animals if a.id in matched_ids]
    missing = [dict(animal_id=a.id, tag_number=a.tag_number, species=a.species,
                    category=a.category.name_sw) for a in animals if a.id not in matched_ids]
    unmatched = [dict(raw_value=e.raw_value, id_type=e.id_type)
                 for e in entries if e.matched_animal_id is None]
    denominator = len(matched) + len(missing)
    location = await db.get(Location, session.location_id)
    return ReconciliationResultResponse(
        session_id=session.id, location_name=location.name,
        session_date=session.session_date, input_type=session.input_type,
        total_scanned=len(entries), matched=matched, unmatched_scan=unmatched,
        in_system_not_seen=missing, matched_count=len(matched),
        unmatched_scan_count=len(unmatched), in_system_not_seen_count=len(missing),
        coverage_pct=100.0 * len(matched) / denominator if denominator else 0.0,
    )


async def _process_reconciliation_session(db, session_id):
    session = await _load_reconciliation_session(db, session_id)
    entries = (await db.execute(select(ReconciliationEntry).where(
        ReconciliationEntry.session_id == session_id,
    ).order_by(ReconciliationEntry.id))).scalars().all()
    for entry in entries:
        ids = set((await db.execute(select(AnimalIdentifier.animal_id).where(
            AnimalIdentifier.id_type == entry.id_type,
            AnimalIdentifier.id_value == entry.raw_value,
            AnimalIdentifier.is_active.is_(True),
        ))).scalars().all())
        if not ids and entry.id_type == AnimalIdentifierType.VISUAL_TAG:
            ids = set((await db.execute(select(Animal.id).where(
                Animal.tag_number == entry.raw_value,
            ))).scalars().all())
        if len(ids) > 1:
            raise HTTPException(status_code=409, detail=f"Ambiguous tag: {entry.raw_value}")
        entry.matched_animal_id = next(iter(ids), None)
        entry.match_status = "matched" if ids else "unmatched_scan"
    await db.flush()
    return await _reconciliation_result(db, session)


@router.post("/reconciliation/sessions", response_model=ReconciliationResultResponse)
async def create_reconciliation_session(
    data: ReconciliationSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    if await db.get(Location, data.location_id) is None:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        session = ReconciliationSession(
            **data.model_dump(exclude={"entries"}), recorded_by=current_user.id,
        )
        db.add(session)
        await db.flush()
        db.add_all([ReconciliationEntry(session_id=session.id, **entry.model_dump())
                    for entry in data.entries])
        await db.flush()
        result = await _process_reconciliation_session(db, session.id)
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


@router.get("/reconciliation/sessions", response_model=List[ReconciliationSessionSummary])
async def list_reconciliation_sessions(
    location_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    query = select(ReconciliationSession)
    if location_id is not None:
        query = query.where(ReconciliationSession.location_id == location_id)
    if date_from is not None:
        query = query.where(ReconciliationSession.session_date >= date_from)
    if date_to is not None:
        query = query.where(ReconciliationSession.session_date <= date_to)
    sessions = (await db.execute(query.order_by(
        ReconciliationSession.session_date.desc(), ReconciliationSession.id.desc(),
    ))).scalars().all()
    summaries = []
    for session in sessions:
        result = await _reconciliation_result(db, session)
        summaries.append(ReconciliationSessionSummary(
            id=session.id, created_at=session.created_at,
            **result.model_dump(exclude={"session_id", "matched", "unmatched_scan", "in_system_not_seen"}),
        ))
    return summaries


@router.get("/reconciliation/sessions/{session_id}", response_model=ReconciliationResultResponse)
async def get_reconciliation_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    return await _reconciliation_result(db, await _load_reconciliation_session(db, session_id))


@router.post("/reconciliation/sessions/{session_id}/reprocess", response_model=ReconciliationResultResponse)
async def reprocess_reconciliation_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        result = await _process_reconciliation_session(db, session_id)
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise
