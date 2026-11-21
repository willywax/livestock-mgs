"""Category-transition helpers: seed rules, build queue, confirm transitions."""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException
from models import Animal, AnimalSex, AnimalStatus, Category, CategoryTransition, CategoryTransitionRule, Location, SpeciesType, StockLevel, TransitionTriggerType, User
from schemas import CategoryTransitionResponse, CategoryTransitionRuleResponse, TransitionQueueItem, TransitionQueueResponse
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# ---------- Category transitions ----------
# Rules say when an animal is due to move to its next category (by age, or on first calving). Confirming a
# transition changes animals.category_id AND moves one head between stock_levels rows in the same transaction.
# It writes no Event row, so staff must not also log a category_change event for the same move.
_TRANSITION_SEED_CHAIN = {
    # species: (youngest male category, youngest female category)
    SpeciesType.CATTLE: ("Ndama Dume", "Ndama Jike"),
    SpeciesType.SHEEP: ("Vichinda Dume", "Vichinda Jike"),
    SpeciesType.GOAT: ("Vichinda Dume", "Vichinda Jike"),
}


async def _seed_category_transition_rules(db: AsyncSession) -> int:
    """Insert the default rules that do not exist yet (never overwrites edited rules). Returns rows added."""
    cats = {(c.species, c.name_sw): c.id for c in (await db.execute(select(Category))).scalars().all()}
    added = 0
    for species, (young_m, young_f) in _TRANSITION_SEED_CHAIN.items():
        # (from, to_f, to_m, trigger, age_months, event)
        chain = [
            (young_m, None, "Achishwa Dume", TransitionTriggerType.AGE, 7, None),
            (young_f, "Achishwa Jike", None, TransitionTriggerType.AGE, 7, None),
            ("Achishwa Dume", None, "Dume Wadogo", TransitionTriggerType.AGE, 18, None),
            ("Achishwa Jike", "Mitamba", None, TransitionTriggerType.AGE, 18, None),
            ("Mitamba", "Koo", None, TransitionTriggerType.EVENT, None, "first_calving"),
        ]
        for from_sw, to_f_sw, to_m_sw, trigger, age, event in chain:
            ids = [cats.get((species, n)) for n in (from_sw, to_f_sw, to_m_sw) if n]
            if any(i is None for i in ids):
                logger.warning("Transition seed skipped for %s %s: category missing", species.value, from_sw)
                continue
            from_id = cats[(species, from_sw)]
            exists = (await db.execute(select(CategoryTransitionRule.id).where(
                CategoryTransitionRule.species == species,
                CategoryTransitionRule.from_category_id == from_id,
                CategoryTransitionRule.trigger_type == trigger,
            ))).first()
            if exists:
                continue
            db.add(CategoryTransitionRule(
                species=species, from_category_id=from_id,
                to_category_id_f=cats.get((species, to_f_sw)) if to_f_sw else None,
                to_category_id_m=cats.get((species, to_m_sw)) if to_m_sw else None,
                trigger_type=trigger, trigger_age_months=age, trigger_event=event, is_active=True,
            ))
            added += 1
    await db.commit()
    return added


def _age_in_months(birth_date: date, today: date) -> int:
    months = (today.year - birth_date.year) * 12 + (today.month - birth_date.month)
    if today.day < birth_date.day:
        months -= 1
    return max(months, 0)


def _months_ago(today: date, months: int) -> date:
    """`today` minus whole calendar months, day clamped to the target month's length."""
    year, month0 = divmod(today.year * 12 + today.month - 1 - months, 12)
    month = month0 + 1
    next_first = date(year + (month == 12), month % 12 + 1, 1)
    return date(year, month, min(today.day, (next_first - timedelta(days=1)).day))


def _rule_trigger_label(rule: CategoryTransitionRule) -> str:
    if rule.trigger_type == TransitionTriggerType.AGE:
        return f"age_{rule.trigger_age_months}m"
    return rule.trigger_event or "event"


async def _to_transition_responses(db: AsyncSession, rows) -> List[CategoryTransitionResponse]:
    if not rows:
        return []
    cat_ids = {r.from_category_id for r in rows} | {r.to_category_id for r in rows}
    cat_names = {c.id: c.name_sw for c in (await db.execute(select(Category).where(Category.id.in_(cat_ids)))).scalars()}
    tags = {a.id: a.tag_number for a in (await db.execute(
        select(Animal).where(Animal.id.in_({r.animal_id for r in rows})))).scalars()}
    user_ids = {r.confirmed_by for r in rows if r.confirmed_by}
    users = {}
    if user_ids:
        users = {u.id: u.name for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars()}
    return [CategoryTransitionResponse(
        id=r.id, animal_id=r.animal_id, tag_number=tags.get(r.animal_id, ""),
        from_category=cat_names.get(r.from_category_id, ""), to_category=cat_names.get(r.to_category_id, ""),
        transition_date=r.transition_date, trigger=r.trigger, notes=r.notes,
        confirmed_by_name=users.get(r.confirmed_by),
    ) for r in rows]


async def _confirm_category_transition(
    db: AsyncSession, animal_id: int, to_category_id: int, trigger: str, rule_id: Optional[int],
    notes: Optional[str], confirmed_by_id: Optional[int],
) -> CategoryTransitionResponse:
    """Move one animal to a new category and shift one head of stock, all-or-nothing.

    Everything runs in a SAVEPOINT: any failure leaves animal, stock and audit rows untouched even if the
    caller swallows the exception. The caller owns the outer transaction and commits.
    Stock uses stock_levels.current_count (written directly; apply/reverse_event_stock are not involved).
    """
    try:
        async with db.begin_nested():
            animal = (await db.execute(
                select(Animal).where(Animal.id == animal_id).with_for_update()
            )).scalar_one_or_none()
            if animal is None:
                raise HTTPException(status_code=404, detail="Animal not found")
            if animal.status != AnimalStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="Only active animals can change category")
            if animal.category_id == to_category_id:
                raise HTTPException(status_code=400, detail="Animal is already in that category")
            to_cat = await db.get(Category, to_category_id)
            if to_cat is None:
                raise HTTPException(status_code=404, detail="Target category not found")
            if to_cat.species != animal.species or not to_cat.is_active:
                raise HTTPException(status_code=400, detail="Target category must be an active category of the animal's species")
            from_category_id = animal.category_id
            now = datetime.now(timezone.utc)

            same_row = and_(StockLevel.location_id == animal.location_id, StockLevel.species == animal.species)
            dec = await db.execute(
                update(StockLevel)
                .where(same_row, StockLevel.category_id == from_category_id, StockLevel.current_count >= 1)
                .values(current_count=StockLevel.current_count - 1, last_updated=now)
                .execution_options(synchronize_session=False)
            )
            if dec.rowcount != 1:
                raise HTTPException(
                    status_code=409,
                    detail="Stock for the current category is 0 at this location; correct stock before changing category",
                )
            inc_stmt = (
                update(StockLevel)
                .where(same_row, StockLevel.category_id == to_category_id)
                .values(current_count=StockLevel.current_count + 1, last_updated=now)
                .execution_options(synchronize_session=False)
            )
            if (await db.execute(inc_stmt)).rowcount == 0:
                try:
                    async with db.begin_nested():
                        db.add(StockLevel(location_id=animal.location_id, species=animal.species,
                                          category_id=to_category_id, current_count=1, last_updated=now))
                        await db.flush()
                except IntegrityError:  # another request created the row first
                    if (await db.execute(inc_stmt)).rowcount != 1:
                        raise HTTPException(status_code=409, detail="Could not update stock for the new category")

            transition = CategoryTransition(
                animal_id=animal.id, rule_id=rule_id, from_category_id=from_category_id,
                to_category_id=to_category_id, transition_date=date.today(), trigger=trigger,
                notes=notes, confirmed_by=confirmed_by_id,
            )
            db.add(transition)
            animal.category_id = to_category_id
            await db.flush()
        return (await _to_transition_responses(db, [transition]))[0]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Category transition failed for animal %s", animal_id)
        raise HTTPException(status_code=500, detail="Category transition failed; nothing was changed")


async def _resolve_transition(db: AsyncSession, animal_id: int, to_category_id: int):
    """(trigger, rule_id) for a confirm: the matching active rule, else a manual transition."""
    animal = await db.get(Animal, animal_id)
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal not found")
    rule = (await db.execute(select(CategoryTransitionRule).where(
        CategoryTransitionRule.species == animal.species,
        CategoryTransitionRule.from_category_id == animal.category_id,
        CategoryTransitionRule.is_active.is_(True),
        or_(CategoryTransitionRule.to_category_id_f == to_category_id,
            CategoryTransitionRule.to_category_id_m == to_category_id),
    ).order_by(CategoryTransitionRule.id))).scalars().first()
    if rule is None:
        return "manual", None
    return _rule_trigger_label(rule), rule.id


async def _build_transition_queue(db: AsyncSession, species=None, location_id=None) -> TransitionQueueResponse:
    """Animals past an active AGE rule's threshold. Read-only."""
    rule_query = select(CategoryTransitionRule).where(
        CategoryTransitionRule.is_active.is_(True),
        CategoryTransitionRule.trigger_type == TransitionTriggerType.AGE,
        CategoryTransitionRule.trigger_age_months.isnot(None),
    ).order_by(CategoryTransitionRule.id)
    if species is not None:
        rule_query = rule_query.where(CategoryTransitionRule.species == species)
    rules = (await db.execute(rule_query)).scalars().all()
    if not rules:
        return TransitionQueueResponse(pending=[], total=0)
    cat_names = {c.id: c.name_sw for c in (await db.execute(select(Category))).scalars()}
    today = date.today()
    recent = {(r.animal_id, r.from_category_id, r.to_category_id) for r in (await db.execute(
        select(CategoryTransition).where(CategoryTransition.transition_date >= today - timedelta(days=7))
    )).scalars()}
    # One query for all rules: each rule contributes (species, category, born on/before cutoff). The cutoff
    # is "today minus N whole months" (day clamped), which is exactly age_in_months >= N.
    rule_by_key = {}
    conditions = []
    for index, rule in enumerate(rules):
        rule_by_key.setdefault((rule.species, rule.from_category_id), (index, rule))
        conditions.append(and_(
            Animal.species == rule.species, Animal.category_id == rule.from_category_id,
            Animal.birth_date <= _months_ago(today, rule.trigger_age_months),
        ))
    query = select(Animal).options(
        selectinload(Animal.location).load_only(Location.id, Location.name),
    ).where(Animal.status == AnimalStatus.ACTIVE, Animal.birth_date.isnot(None), or_(*conditions))
    if location_id is not None:
        query = query.where(Animal.location_id == location_id)
    candidates = []
    for animal in (await db.execute(query)).scalars().all():
        index, rule = rule_by_key[(animal.species, animal.category_id)]
        candidates.append((index, animal.tag_number, animal.id, animal, rule))
    candidates.sort(key=lambda c: c[:3])  # rule order, then tag: same order as the old per-rule loop
    pending = []
    for _, _, _, animal, rule in candidates:
        age = _age_in_months(animal.birth_date, today)
        if age < rule.trigger_age_months:
            continue
        target = rule.to_category_id_f if animal.sex == AnimalSex.FEMALE else rule.to_category_id_m
        if target is None or (animal.id, rule.from_category_id, target) in recent:
            continue
        pending.append(TransitionQueueItem(
            animal_id=animal.id, tag_number=animal.tag_number, species=animal.species,
            current_category=cat_names.get(animal.category_id, ""), to_category_id=target,
            to_category=cat_names.get(target, ""), age_months=age,
            location_name=animal.location.name if animal.location else None,
            rule_id=rule.id, trigger=_rule_trigger_label(rule),
        ))
    return TransitionQueueResponse(pending=pending, total=len(pending))


async def _maybe_first_calving_transition(db: AsyncSession, animal_id: int, user_id: Optional[int]) -> None:
    """After a CALVING event: move a heifer to the cow category once. Best-effort: never blocks the calving record."""
    animal = await db.get(Animal, animal_id)
    if animal is None:
        return
    rule = (await db.execute(select(CategoryTransitionRule).where(
        CategoryTransitionRule.species == animal.species,
        CategoryTransitionRule.trigger_type == TransitionTriggerType.EVENT,
        CategoryTransitionRule.trigger_event == "first_calving",
        CategoryTransitionRule.is_active.is_(True),
        CategoryTransitionRule.from_category_id == animal.category_id,
    ))).scalars().first()
    target = rule.to_category_id_f if rule else None
    if rule is None or target is None or animal.sex != AnimalSex.FEMALE:
        return
    prior = (await db.execute(select(func.count(CategoryTransition.id)).where(
        CategoryTransition.animal_id == animal_id, CategoryTransition.trigger == "first_calving",
    ))).scalar_one()
    if prior:
        return
    try:
        await _confirm_category_transition(db, animal_id, target, "first_calving", rule.id, None, user_id)
    except Exception as exc:  # the savepoint already rolled back; the calving event still saves
        logger.warning("First-calving transition skipped for animal %s: %s", animal_id, getattr(exc, "detail", exc))


async def _rule_response(db: AsyncSession, rule: CategoryTransitionRule) -> CategoryTransitionRuleResponse:
    ids = {i for i in (rule.from_category_id, rule.to_category_id_f, rule.to_category_id_m) if i}
    names = {c.id: c.name_sw for c in (await db.execute(select(Category).where(Category.id.in_(ids)))).scalars()}
    return CategoryTransitionRuleResponse(
        id=rule.id, species=rule.species, from_category_id=rule.from_category_id,
        from_category_name=names.get(rule.from_category_id, ""),
        to_category_id_f=rule.to_category_id_f, to_category_name_f=names.get(rule.to_category_id_f),
        to_category_id_m=rule.to_category_id_m, to_category_name_m=names.get(rule.to_category_id_m),
        trigger_type=rule.trigger_type.value, trigger_age_months=rule.trigger_age_months,
        trigger_event=rule.trigger_event, is_active=rule.is_active, notes=rule.notes,
    )
