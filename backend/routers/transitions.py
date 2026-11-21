"""Category-transition rules, queue and confirmation endpoints."""
from typing import List, Optional

from auth import require_roles
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models import Animal, Category, CategoryTransition, CategoryTransitionRule, SpeciesType, TransitionTriggerType, User, UserRole
from schemas import BulkConfirmRequest, BulkConfirmResponse, BulkConfirmResult, CategoryTransitionResponse, CategoryTransitionRuleResponse, CategoryTransitionRuleUpdate, ConfirmTransitionRequest, TransitionQueueResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.transitions import _build_transition_queue, _confirm_category_transition, _resolve_transition, _rule_response, _to_transition_responses

router = APIRouter()

@router.get("/admin/transition-rules", response_model=List[CategoryTransitionRuleResponse])
async def list_transition_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    rules = (await db.execute(select(CategoryTransitionRule).order_by(
        CategoryTransitionRule.species, CategoryTransitionRule.id))).scalars().all()
    return [await _rule_response(db, r) for r in rules]


@router.put("/admin/transition-rules/{rule_id}", response_model=CategoryTransitionRuleResponse)
async def update_transition_rule(
    rule_id: int,
    data: CategoryTransitionRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    rule = await db.get(CategoryTransitionRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Transition rule not found")
    changes = data.model_dump(exclude_unset=True)
    if "trigger_age_months" in changes:
        if rule.trigger_type != TransitionTriggerType.AGE:
            raise HTTPException(status_code=400, detail="trigger_age_months only applies to age rules")
        if changes["trigger_age_months"] is None:
            raise HTTPException(status_code=400, detail="An age rule needs trigger_age_months")
    if "is_active" in changes and changes["is_active"] is None:
        raise HTTPException(status_code=400, detail="is_active cannot be null")
    for key in ("to_category_id_f", "to_category_id_m"):
        if changes.get(key) is not None:
            cat = await db.get(Category, changes[key])
            if cat is None or cat.species != rule.species or not cat.is_active:
                raise HTTPException(status_code=400, detail="Target category must be an active category of the rule's species")
            if cat.id == rule.from_category_id:
                raise HTTPException(status_code=400, detail="Target category must differ from the source category")
    for key, value in changes.items():
        setattr(rule, key, value)
    await db.commit()
    return await _rule_response(db, rule)


@router.get("/animals/transition-queue", response_model=TransitionQueueResponse)
async def get_transition_queue(
    species: Optional[SpeciesType] = None,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    return await _build_transition_queue(db, species, location_id)


@router.post("/admin/tasks/sync-category-transitions", response_model=TransitionQueueResponse)
async def sync_category_transitions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    # Finds eligible animals only: staff confirm each transition separately.
    return await _build_transition_queue(db)


@router.post("/animals/bulk-confirm-transitions", response_model=BulkConfirmResponse)
async def bulk_confirm_transitions(
    data: BulkConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    # Each animal is its own savepoint: one failure does not undo the others. One commit at the end.
    results = []
    for item in data.transitions:
        try:
            trigger, rule_id = await _resolve_transition(db, item.animal_id, item.to_category_id)
            transition = await _confirm_category_transition(
                db, item.animal_id, item.to_category_id, trigger, rule_id, data.notes, current_user.id)
            results.append(BulkConfirmResult(animal_id=item.animal_id, success=True, transition=transition))
        except HTTPException as exc:
            results.append(BulkConfirmResult(animal_id=item.animal_id, success=False, error=str(exc.detail)))
    await db.commit()
    ok = sum(1 for r in results if r.success)
    return BulkConfirmResponse(results=results, succeeded=ok, failed=len(results) - ok)


@router.post("/animals/{animal_id}/confirm-transition", response_model=CategoryTransitionResponse)
async def confirm_transition(
    animal_id: int,
    data: ConfirmTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY)),
):
    trigger, rule_id = await _resolve_transition(db, animal_id, data.to_category_id)
    try:
        transition = await _confirm_category_transition(
            db, animal_id, data.to_category_id, trigger, rule_id, data.notes, current_user.id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return transition


@router.get("/animals/{animal_id}/transition-history", response_model=List[CategoryTransitionResponse])
async def get_transition_history(
    animal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)),
):
    if await db.get(Animal, animal_id) is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    rows = (await db.execute(select(CategoryTransition).where(CategoryTransition.animal_id == animal_id)
                             .order_by(CategoryTransition.transition_date.desc(), CategoryTransition.id.desc()))).scalars().all()
    return await _to_transition_responses(db, rows)
