"""Animal notes."""
from typing import List

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import AnimalNote, User, UserRole
from schemas import AnimalNoteCreate, AnimalNoteResponse, AnimalNoteUpdate
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common import _ANY_ROLE, _require_animal

router = APIRouter()

# ---------- Animal notes ----------
async def _load_note(db: AsyncSession, animal_id: int, note_id: int) -> AnimalNote:
    result = await db.execute(
        select(AnimalNote).where(and_(AnimalNote.id == note_id, AnimalNote.animal_id == animal_id))
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.get("/animals/{animal_id}/notes", response_model=List[AnimalNoteResponse])
async def list_animal_notes(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*_ANY_ROLE)),
):
    await _require_animal(db, animal_id)
    result = await db.execute(
        select(AnimalNote).where(AnimalNote.animal_id == animal_id)
        .order_by(AnimalNote.note_date.desc(), AnimalNote.id.desc())
    )
    return [AnimalNoteResponse.model_validate(n) for n in result.scalars().all()]


@router.post("/animals/{animal_id}/notes", response_model=AnimalNoteResponse)
async def create_animal_note(
    animal_id: int,
    data: AnimalNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    await _require_animal(db, animal_id)
    note = AnimalNote(animal_id=animal_id, **data.model_dump(), created_by=current_user.id)
    db.add(note)
    await db.commit()
    return AnimalNoteResponse.model_validate(note)


@router.put("/animals/{animal_id}/notes/{note_id}", response_model=AnimalNoteResponse)
async def update_animal_note(
    animal_id: int,
    note_id: int,
    data: AnimalNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    note = await _load_note(db, animal_id, note_id)
    for key in data.model_fields_set:
        value = getattr(data, key)
        if value is not None:  # all three note fields are non-nullable
            setattr(note, key, value)
    await db.commit()
    return AnimalNoteResponse.model_validate(note)


@router.delete("/animals/{animal_id}/notes/{note_id}")
async def delete_animal_note(
    animal_id: int,
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    await db.delete(await _load_note(db, animal_id, note_id))
    await db.commit()
    return {"message": "Note deleted"}
