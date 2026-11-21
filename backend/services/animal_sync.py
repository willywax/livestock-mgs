"""Best-effort sync of the animal register from daily-log events (create/transfer/status, temp tags, daily reproduction links, reversal)."""
import logging
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import List, Optional

from models import Animal, AnimalAcquisitionType, AnimalLocationHistory, AnimalSex, AnimalStatus, Category, CategoryTransition, CategoryTransitionRule, DailyLog, Event, EventAnimalLink, EventType, Location, PDResult, ReproductiveEvent, User
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.transitions import _confirm_category_transition

logger = logging.getLogger(__name__)

# ==================== ANIMAL REGISTER SYNC (best-effort) ====================
# Runs AFTER the stock commit. Failures here never roll back stock; they are
# logged and surfaced as sync_warnings on the response. Helpers take plain
# snapshots/values so a rollback (which expires ORM objects) cannot break them.
_FEMALE_CATEGORIES = {"koo", "mitamba", "ndama jike", "achishwa jike", "vichinda jike"}
_MALE_CATEGORIES = {"ndama dume", "achishwa dume", "maksai", "dume mbegu", "dume wadogo", "vichinda dume"}
_SYNC_FAILED_MSG = "Animal register could not be updated automatically (see server logs); stock was saved."


def _split_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    seen, out = set(), []
    for part in raw.split(","):
        tag = part.strip()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _infer_sex(category: Optional[Category]) -> Optional[AnimalSex]:
    """Sex implied by the seeded category name (None when it cannot be told)."""
    if category is None:
        return None
    name = (category.name_sw or "").strip().lower()
    if name in _FEMALE_CATEGORIES:
        return AnimalSex.FEMALE
    if name in _MALE_CATEGORIES:
        return AnimalSex.MALE
    return None


def _event_snapshot(event: Event, location_id: int, log_date: date) -> SimpleNamespace:
    return SimpleNamespace(
        id=event.id, event_type=event.event_type, species=event.species,
        category_id=event.category_id, from_category_id=event.from_category_id,
        to_category_id=event.to_category_id, from_location_id=event.from_location_id,
        to_location_id=event.to_location_id, animal_tags=event.animal_tags,
        offspring_tags=event.offspring_tags, location_id=location_id, log_date=log_date,
    )


async def _find_animal(db: AsyncSession, tag: str, species, prefer_location: Optional[int] = None,
                       prefer_status: Optional[AnimalStatus] = None) -> Optional[Animal]:
    rows = (await db.execute(
        select(Animal).where(and_(Animal.tag_number == tag, Animal.species == species)).order_by(Animal.id)
    )).scalars().all()
    if not rows:
        return None

    def rank(a: Animal):
        return (
            0 if prefer_status is not None and a.status == prefer_status else 1,
            0 if prefer_location is not None and a.location_id == prefer_location else 1,
            0 if a.status == AnimalStatus.ACTIVE else 1,
            a.id,
        )
    return sorted(rows, key=rank)[0]


def _set_status(animal: Animal, status: AnimalStatus) -> None:
    if animal.status != status:
        animal.status = status
        animal.status_changed_at = datetime.now(timezone.utc)


async def _restore_after_rollback(db: AsyncSession, *objs) -> None:
    """rollback() expires ORM objects; reload the ones the caller still uses."""
    for obj in objs:
        try:
            await db.refresh(obj)
        except Exception:
            logger.warning("Could not refresh %r after register-sync rollback", obj, exc_info=True)


_MAX_TEMP_ANIMALS_PER_EVENT = 50
_TEMP_PLACEHOLDERS = {"", "new", "temp"}


def _offspring_entries(raw: Optional[str], count: Optional[int]) -> List[str]:
    """Offspring entries for a birth, empties preserved ('KK-001, , KK-003' -> middle is untagged).

    A blank field means the newborns are untagged: one placeholder entry per head of `count`.
    """
    if raw is None or not raw.strip():
        return [""] * min(max(count or 0, 0), _MAX_TEMP_ANIMALS_PER_EVENT)
    return [part.strip() for part in raw.split(",")]


async def _generate_temp_tag(location_name: Optional[str], log_date: date, db: AsyncSession) -> str:
    """TEMP-<LOC>-<YYYYMMDD>-NNN: next free sequence for this prefix and date.

    Optimistic: the unique constraint (tag, species, location) still arbitrates concurrent writers.
    """
    prefix = re.sub(r"[^A-Za-z0-9]", "", location_name or "")[:3].upper() or "UNK"
    base = f"TEMP-{prefix}-{log_date.strftime('%Y%m%d')}"
    used = (await db.execute(
        select(func.count()).select_from(Animal).where(Animal.tag_number.like(f"{base}-%"))
    )).scalar() or 0
    seq = used + 1
    while True:  # skip past tags that already exist (e.g. after deletions)
        tag = f"{base}-{seq:03d}"
        taken = (await db.execute(select(Animal.id).where(Animal.tag_number == tag).limit(1))).first()
        if taken is None:
            return tag
        seq += 1


_REPRO_FIELDS = ('reproductive_status', 'last_calving_date', 'last_pd_date',
                 'months_pregnant', 'services_without_conception')
_DAILY_REPRO_TYPES = {EventType.BIRTH, EventType.ABORTION, EventType.PD_TEST, EventType.SERVICE}


async def _linked_animal(db, event_id, tag, species, location_id, role='subject'):
    # An event's original tag remains meaningful after the registered tag changes.
    linked = (await db.execute(select(Animal).join(EventAnimalLink, EventAnimalLink.animal_id == Animal.id).where(
        EventAnimalLink.event_id == event_id, EventAnimalLink.tag_at_link == tag,
        EventAnimalLink.role == role, Animal.species == species))).scalars().first()
    if linked is not None:
        return linked
    rows = (await db.execute(select(Animal).where(Animal.tag_number == tag, Animal.species == species))).scalars().all()
    local = [animal for animal in rows if animal.location_id == location_id]
    candidates = local or rows
    if len(candidates) > 1:
        raise ValueError(f"Tag {tag}: ambiguous animal; register sync skipped")
    return await _find_animal(db, tag, species, prefer_location=location_id)


async def _ensure_repro_baseline(db, animal, link):
    existing = (await db.execute(select(EventAnimalLink.id).where(
        EventAnimalLink.animal_id == animal.id,
        EventAnimalLink.reproductive_baseline.is_not(None)))).first()
    # JSON NULL can differ from SQL NULL across databases: inspect actual values below.
    baselines = (await db.execute(select(EventAnimalLink).where(
        EventAnimalLink.animal_id == animal.id))).scalars().all() if existing else []
    if any(row.reproductive_baseline for row in baselines):
        return
    state = {field: getattr(animal, field) for field in _REPRO_FIELDS}
    for field in ('last_calving_date', 'last_pd_date'):
        state[field] = state[field].isoformat() if state[field] else None
    known_dates = [value for key, value in state.items() if key in ('last_pd_date', 'last_calving_date') and value]
    latest = await db.scalar(select(func.max(ReproductiveEvent.event_date)).where(ReproductiveEvent.animal_id == animal.id))
    if latest:
        known_dates.append(latest.isoformat())
    state['_through_date'] = max(known_dates) if known_dates else None
    link.reproductive_baseline = state


def _repro_step(state, payload):
    kind, day = payload['type'], payload['date']
    if kind == 'service':
        if not payload.get('only_open') or state.get('reproductive_status') in (None, 'open', 'unknown'):
            state['services_without_conception'] = (state.get('services_without_conception') or 0) + 1
    elif kind == 'pd_test':
        state['last_pd_date'] = day
        state['reproductive_status'] = payload['result']
        state['months_pregnant'] = payload.get('months') if payload['result'] == 'pregnant' else None
        if payload['result'] == 'pregnant':
            state['services_without_conception'] = 0
    elif kind == 'birth' or kind == 'calving':
        state.update(reproductive_status='open', last_calving_date=day, months_pregnant=None,
                     services_without_conception=0)
    elif kind == 'abortion':
        state.update(reproductive_status='open', months_pregnant=None)
        if payload.get('clear_calving'):
            state['last_calving_date'] = None


async def _replay_daily_reproduction(db, animal_id):
    animal = (await db.execute(select(Animal).where(Animal.id == animal_id).with_for_update())).scalar_one()
    links = (await db.execute(select(EventAnimalLink).where(
        EventAnimalLink.animal_id == animal_id).order_by(EventAnimalLink.id))).scalars().all()
    baseline = next((link.reproductive_baseline for link in links if link.reproductive_baseline), None)
    if baseline is None:
        return
    state = dict(baseline)
    sources = [link for link in links if link.is_active and link.reproductive_payload]
    sources.sort(key=lambda link: (link.reproductive_payload['date'], link.id))
    for link in sources:
        if baseline.get('_through_date') and link.reproductive_payload['date'] < baseline['_through_date']:
            continue  # historical events must not overwrite a newer pre-journal observation
        _repro_step(state, link.reproductive_payload)
    for field in _REPRO_FIELDS:
        value = state[field]
        if field in ('last_pd_date', 'last_calving_date') and value:
            value = date.fromisoformat(value)
        setattr(animal, field, value)
    db.add(animal)


async def _record_external_reproduction(db, animal, event):
    """Keep later standalone/cycle observations in the daily-log replay journal."""
    links = (await db.execute(select(EventAnimalLink).where(EventAnimalLink.animal_id == animal.id))).scalars().all()
    if not any(link.reproductive_baseline for link in links):
        return False
    source = getattr(event, 'source_key', None) or f"reproductive:{event.id}"
    link = next((link for link in links if link.source_key == source), None)
    if link is None:
        link = EventAnimalLink(animal_id=animal.id, role='external', source_key=source, is_active=True)
        db.add(link)
    result = getattr(event, 'pd_result', None)
    link.reproductive_payload = dict(type=event.event_type.value, date=event.event_date.isoformat(),
        result='pregnant' if result == PDResult.PREGNANT else 'open', months=getattr(event, 'months_pregnant', None))
    await db.flush()
    await _replay_daily_reproduction(db, animal.id)
    return True


async def _sync_daily_links(db, event, log, user, warnings):
    """Caller isolates this block in a savepoint; retained baselines make edits/deletes replayable."""
    await db.execute(select(Event.id).where(Event.id == event.id).with_for_update())
    previous = (await db.execute(select(EventAnimalLink).where(EventAnimalLink.event_id == event.id))).scalars().all()
    affected = {link.animal_id for link in previous if link.reproductive_payload}
    for link in previous:
        link.is_active = False
        link.reproductive_payload = None
    targets = []
    for tag in _split_tags(event.animal_tags):
        targets.append((tag, 'subject'))
    if event.event_type in (EventType.BIRTH, EventType.ABORTION) and event.mother_tag:
        targets.extend((tag, 'mother') for tag in _split_tags(event.mother_tag))
    if event.event_type == EventType.BIRTH:
        targets.extend((tag, 'offspring') for tag in _split_tags(event.offspring_tags)
                       if tag.lower() not in _TEMP_PLACEHOLDERS)
        temporary = (await db.execute(select(Animal).where(
            Animal.notes == f"Auto-created temp tag from birth event #{event.id}", Animal.is_temp_tag.is_(True)))).scalars().all()
        targets.extend((animal.tag_number, 'offspring') for animal in temporary)
    transitioned = set()
    for tag, role in dict.fromkeys(targets):
        location = event.from_location_id or log.location_id if event.event_type == EventType.TRANSFER else log.location_id
        animal = await _linked_animal(db, event.id, tag, event.species, location, role)
        if animal is None:
            warnings.append(f"Tag {tag}: not found; daily-log link skipped")
            continue
        # Lock before baseline capture so concurrent reproductive saves are serialized per animal.
        animal = (await db.execute(select(Animal).where(Animal.id == animal.id).with_for_update()
                                  .execution_options(populate_existing=True))).scalar_one()
        link = next((row for row in previous if row.animal_id == animal.id and row.role == role), None)
        if link is None:
            link = EventAnimalLink(event_id=event.id, animal_id=animal.id, role=role, tag_at_link=tag)
            db.add(link)
            previous.append(link)
        link.tag_at_link = tag
        link.is_active = True
        reproductive = (event.event_type in (EventType.PD_TEST, EventType.SERVICE) and role == 'subject') or (
            event.event_type in (EventType.BIRTH, EventType.ABORTION) and role == 'mother') or (
            event.event_type == EventType.ABORTION and not event.mother_tag and role == 'subject')
        if not reproductive:
            continue
        if animal.sex != AnimalSex.FEMALE:
            warnings.append(f"Tag {tag}: reproductive sync requires a female animal")
            continue
        await _ensure_repro_baseline(db, animal, link)
        link.reproductive_payload = dict(type=event.event_type.value, date=log.log_date.isoformat(),
            result=event.pd_result, months=event.months_pregnant, only_open=True, clear_calving=True)
        affected.add(animal.id)
        if event.event_type == EventType.BIRTH and animal.id not in transitioned:
            transitioned.add(animal.id)
            try:
                async with db.begin_nested():
                    prior = await db.scalar(select(func.count(CategoryTransition.id)).where(
                        CategoryTransition.animal_id == animal.id, CategoryTransition.trigger == 'first_calving'))
                    rule = (await db.execute(select(CategoryTransitionRule).where(
                        CategoryTransitionRule.species == animal.species,
                        CategoryTransitionRule.from_category_id == animal.category_id,
                        CategoryTransitionRule.is_active.is_(True),
                        CategoryTransitionRule.trigger_event == 'first_calving'))).scalars().first()
                    if not prior and rule and rule.to_category_id_f:
                        transition = await _confirm_category_transition(db, animal.id, rule.to_category_id_f,
                            'first_calving', rule.id, 'Auto from daily log calving event', user.id)
                        link.category_transition_id = transition.id
            except Exception:
                warnings.append(f"Tag {tag}: first-calving category transition skipped")
                logger.warning("Daily-log first-calving category transition skipped", exc_info=True)
    await db.flush()
    for animal_id in sorted(affected):
        await _replay_daily_reproduction(db, animal_id)
    for link in previous:
        if link.category_transition_id and (not link.is_active or event.event_type != EventType.BIRTH):
            warnings.append("Prior first-calving category transition retained; review the animal category manually")


async def _remove_daily_reproduction(db, event_id, warnings):
    links = (await db.execute(select(EventAnimalLink).where(EventAnimalLink.event_id == event_id))).scalars().all()
    affected = {link.animal_id for link in links if link.reproductive_payload}
    for link in links:
        link.is_active = False
        link.reproductive_payload = None
        if link.category_transition_id:
            warnings.append("First-calving category transition retained; review the animal category manually")
    await db.flush()
    for animal_id in sorted(affected):
        await _replay_daily_reproduction(db, animal_id)


async def _backfill_daily_event_links(db, apply=False):
    """Explicit migration only: exact, unambiguous links; no reproductive/stock updates."""
    counts = dict(events=0, links=0, unresolved=0)
    after_id = 0
    while True:
        events = (await db.execute(select(Event).options(selectinload(Event.daily_log)).where(
            Event.id > after_id).order_by(Event.id).limit(200))).scalars().all()
        if not events:
            break
        for event in events:
            counts['events'] += 1
            after_id = event.id
            # Already-synced events (including edits/removals) must not regain stale links.
            if await db.scalar(select(EventAnimalLink.id).where(EventAnimalLink.event_id == event.id).limit(1)):
                continue
            targets = [(tag, 'subject') for tag in _split_tags(event.animal_tags)]
            if event.event_type in (EventType.BIRTH, EventType.ABORTION):
                targets.extend((tag, 'mother') for tag in _split_tags(event.mother_tag))
            if event.event_type == EventType.BIRTH:
                targets.extend((tag, 'offspring') for tag in _split_tags(event.offspring_tags)
                               if tag.lower() not in _TEMP_PLACEHOLDERS)
            resolved = {}
            for tag, role in targets:
                # Never guess between duplicate historical tags at different farms.
                animals = (await db.execute(select(Animal).where(Animal.tag_number == tag,
                    Animal.species == event.species))).scalars().all()
                if len(animals) != 1:
                    counts['unresolved'] += 1
                    continue
                resolved[(animals[0].id, role)] = tag
            history = (await db.execute(select(AnimalLocationHistory).where(
                AnimalLocationHistory.event_id == event.id))).scalars().all()
            for movement in history:
                animal = await db.get(Animal, movement.animal_id)
                if animal:
                    resolved[(animal.id, 'subject')] = animal.tag_number
            if event.event_type == EventType.BIRTH:
                temporary = (await db.execute(select(Animal).where(
                    Animal.notes == f"Auto-created temp tag from birth event #{event.id}",
                    Animal.is_temp_tag.is_(True)))).scalars().all()
                for animal in temporary:
                    resolved[(animal.id, 'offspring')] = animal.tag_number
            counts['links'] += len(resolved)
            if apply:
                for (animal_id, role), tag in resolved.items():
                    db.add(EventAnimalLink(event_id=event.id, animal_id=animal_id, role=role,
                                          tag_at_link=tag, is_active=True))
        if apply:
            await db.commit()
    return counts


async def _sync_animals_from_event(db: AsyncSession, event: Event, daily_log: DailyLog,
                                   current_user: User) -> List[str]:
    """Apply an event to the individual animal register. Never raises; returns warnings."""
    warnings: List[str] = []
    event_id = None
    try:
        et = event.event_type
        species = event.species
        event_id = event.id
        category_id = event.category_id
        to_location_id = event.to_location_id
        to_category_id = event.to_category_id
        log_location_id = daily_log.location_id
        log_date = daily_log.log_date
        user_id = current_user.id
        tags = _split_tags(event.animal_tags)
        offspring = _offspring_entries(event.offspring_tags, event.count) if et == EventType.BIRTH else []

        def warn(msg: str) -> None:
            logger.warning("Animal register sync (event %s): %s", event_id, msg)
            warnings.append(msg)

        async def create_animal_row(tag: str, acquisition: AnimalAcquisitionType,
                                    is_temp_tag: bool = False, notes: Optional[str] = None) -> Optional[Animal]:
            if not category_id:
                warn(f"Tag {tag}: no category on event, animal not created")
                return None
            sex = _infer_sex(await db.get(Category, category_id))
            if sex is None:
                warn(f"Tag {tag}: sex cannot be inferred from category, animal not created")
                return None
            animal = Animal(
                tag_number=tag, species=species, category_id=category_id,
                location_id=log_location_id, sex=sex, status=AnimalStatus.ACTIVE,
                acquisition_type=acquisition, acquisition_date=log_date, created_by=user_id,
                is_temp_tag=is_temp_tag, notes=notes,
            )
            db.add(animal)
            await db.flush()
            return animal

        for tag in tags:
            animal = await _linked_animal(db, event_id, tag, species,
                                          event.from_location_id or log_location_id if et == EventType.TRANSFER else log_location_id)
            if animal is None:
                if et in (EventType.BOUGHT, EventType.GIFT_IN):
                    await create_animal_row(tag, AnimalAcquisitionType.BOUGHT)
                else:
                    warn(f"Tag {tag}: not found in the animal register, skipped")
                continue

            if et in (EventType.BOUGHT, EventType.GIFT_IN):
                if animal.status in (AnimalStatus.DEAD, AnimalStatus.SOLD):
                    warn(f"Tag {tag}: register shows it as {animal.status.value}; not reactivated")
                else:
                    _set_status(animal, AnimalStatus.ACTIVE)
            elif et == EventType.DEATH:
                _set_status(animal, AnimalStatus.DEAD)
            elif et in (EventType.SOLD, EventType.GIFT_OUT):
                _set_status(animal, AnimalStatus.SOLD)
            elif et == EventType.MISSING:
                _set_status(animal, AnimalStatus.MISSING)
            elif et in (EventType.TRANSFER, EventType.CATEGORY_CHANGE, EventType.WEANING):
                if animal.status in (AnimalStatus.DEAD, AnimalStatus.SOLD):
                    warn(f"Tag {tag}: register shows it as {animal.status.value}; {et.value} not applied")
                    continue
                _set_status(animal, AnimalStatus.ACTIVE)
                if et == EventType.TRANSFER:
                    if not to_location_id:
                        warn(f"Tag {tag}: transfer has no destination, location unchanged")
                    elif animal.location_id != to_location_id:
                        clash = (await db.execute(select(Animal.id).where(and_(
                            Animal.tag_number == tag, Animal.species == species,
                            Animal.location_id == to_location_id, Animal.id != animal.id,
                        )))).first()
                        if clash:
                            warn(f"Tag {tag}: same tag already registered at the destination, location unchanged")
                        else:
                            db.add(AnimalLocationHistory(
                                animal_id=animal.id, from_location_id=animal.location_id,
                                to_location_id=to_location_id, moved_date=log_date,
                                event_id=event_id, created_by=user_id,
                            ))
                            animal.location_id = to_location_id
                elif to_category_id:
                    animal.category_id = to_category_id
            # BIRTH / ABORTION: nothing to change on the mother's record

        # Placeholders (blank / NEW / TEMP) get generated temp tags. Re-saving the event must not
        # duplicate them, so only the shortfall against temp animals already stamped with this
        # event's marker is created. Typed TEMP-* tags are kept as typed (flagged temp).
        temp_needed = sum(1 for t in offspring if t.lower() in _TEMP_PLACEHOLDERS)
        temp_stamp = f"Auto-created temp tag from birth event #{event_id}"
        temp_missing = temp_needed
        if temp_needed:
            already = (await db.execute(
                select(func.count()).select_from(Animal).where(
                    and_(Animal.is_temp_tag == True, Animal.notes == temp_stamp)  # noqa: E712
                )
            )).scalar() or 0
            temp_missing = max(0, temp_needed - already)
        location_name = None
        if temp_missing:
            location = await db.get(Location, log_location_id)
            location_name = location.name if location else "UNK"

        for tag in offspring:
            if tag.lower() in _TEMP_PLACEHOLDERS:
                if temp_missing <= 0:
                    continue
                temp_missing -= 1
                new_tag = await _generate_temp_tag(location_name, log_date, db)
                await create_animal_row(new_tag, AnimalAcquisitionType.BORN, is_temp_tag=True, notes=temp_stamp)
                continue
            existing = await _find_animal(db, tag, species)
            if existing is not None:
                warn(f"Offspring tag {tag}: already in the animal register, skipped")
                continue
            await create_animal_row(
                tag, AnimalAcquisitionType.BORN, is_temp_tag=tag.upper().startswith("TEMP-")
            )

        # Isolate new linking/reproductive work from the existing register effects.
        try:
            async with db.begin_nested():
                await _sync_daily_links(db, event, daily_log, current_user, warnings)
        except Exception:
            logger.warning("Daily-log reproductive/link sync skipped for event %s", event_id, exc_info=True)
            warnings.append("Daily-log reproductive/link sync failed; event saved, review the animal register")
        await db.commit()
    except Exception:
        logger.warning("Animal register sync failed for event %s", event_id, exc_info=True)
        try:
            await db.rollback()
        except Exception:
            logger.warning("Rollback after animal register sync failure also failed", exc_info=True)
        try:
            await _restore_after_rollback(db, event, daily_log, current_user)
        except Exception:
            logger.warning("Could not restore objects after register sync failure", exc_info=True)
        warnings.append(_SYNC_FAILED_MSG)
    return warnings


_REVERSIBLE_STATUS = {
    EventType.DEATH: AnimalStatus.DEAD,
    EventType.SOLD: AnimalStatus.SOLD,
    EventType.GIFT_OUT: AnimalStatus.SOLD,
    EventType.MISSING: AnimalStatus.MISSING,
}


async def _reverse_animal_sync(db: AsyncSession, snap: SimpleNamespace, deleting: bool = False,
                               restore: tuple = ()) -> List[str]:
    """Undo an event's register effects (snapshot of the OLD event). Never raises; returns warnings.

    Animals auto-created by bought/gift_in/birth events are never deleted (they may already
    have photos, notes or history); a warning is returned when the event is being deleted.
    """
    warnings: List[str] = []
    try:
        et = snap.event_type
        tags = _split_tags(snap.animal_tags)

        def warn(msg: str) -> None:
            logger.warning("Animal register reverse (event %s): %s", snap.id, msg)
            warnings.append(msg)

        if et == EventType.TRANSFER:
            rows = (await db.execute(
                select(AnimalLocationHistory).where(AnimalLocationHistory.event_id == snap.id)
            )).scalars().all()
            for row in rows:
                animal = await db.get(Animal, row.animal_id)
                if animal is not None and animal.location_id == row.to_location_id and row.from_location_id:
                    clash = (await db.execute(select(Animal.id).where(and_(
                        Animal.tag_number == animal.tag_number, Animal.species == animal.species,
                        Animal.location_id == row.from_location_id, Animal.id != animal.id,
                    )))).first()
                    if clash:
                        warn(f"Tag {animal.tag_number}: same tag exists at the original location, not moved back")
                    else:
                        animal.location_id = row.from_location_id
                elif animal is not None:
                    warn(f"Tag {animal.tag_number}: moved again since this event, location left unchanged")
                await db.delete(row)
        elif et in _REVERSIBLE_STATUS:
            expected = _REVERSIBLE_STATUS[et]
            for tag in tags:
                animal = await _linked_animal(db, snap.id, tag, snap.species, snap.location_id)
                if animal is None:
                    continue
                if animal.status == expected:
                    _set_status(animal, AnimalStatus.ACTIVE)
                else:
                    warn(f"Tag {tag}: status is {animal.status.value} (changed since this event), left unchanged")
        elif et in (EventType.CATEGORY_CHANGE, EventType.WEANING):
            old_cat = snap.from_category_id or snap.category_id
            for tag in tags:
                animal = await _linked_animal(db, snap.id, tag, snap.species, snap.location_id)
                if animal is not None and old_cat and animal.category_id == snap.to_category_id:
                    animal.category_id = old_cat
        elif deleting and et in (EventType.BOUGHT, EventType.GIFT_IN, EventType.BIRTH):
            if tags or (et == EventType.BIRTH and snap.offspring_tags):
                warn("Animals created by this event were left in the register; remove them manually if wrong")

        if deleting:
            try:
                async with db.begin_nested():
                    await _remove_daily_reproduction(db, snap.id, warnings)
            except Exception:
                logger.warning("Reproductive reversal failed for deleted event %s", snap.id, exc_info=True)
                warnings.append("Reproductive reversal failed; review the animal register")
        await db.commit()
    except Exception:
        logger.exception("Animal register reverse failed for event %s", snap.id)
        try:
            await db.rollback()
        except Exception:
            logger.exception("Rollback after animal register reverse failure also failed")
        await _restore_after_rollback(db, *restore)
        warnings.append(_SYNC_FAILED_MSG)
    return warnings
