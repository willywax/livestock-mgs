"""Death-cause validation shared by daily-log event routes."""
from fastapi import HTTPException
from models import DeathCause, EventType

async def _validate_death_cause(db, event_type, cause_id, existing_id=None):
    if cause_id is None:
        return
    if event_type != EventType.DEATH:
        raise HTTPException(status_code=400, detail="Structured death causes apply only to DEATH events")
    cause = await db.get(DeathCause, cause_id)
    if cause is None:
        raise HTTPException(status_code=404, detail="Death cause not found")
    if not cause.is_active and cause_id != existing_id:
        raise HTTPException(status_code=400, detail="Death cause is inactive")
