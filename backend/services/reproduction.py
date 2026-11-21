"""Reproductive-status helpers shared by cycles, events and imports."""
from types import SimpleNamespace

from models import Animal, CalvingOutcome, PDResult, ReproductiveEventType

from services.animal_sync import _record_external_reproduction

async def _apply_reproductive_status(db, animal_id, event):
    """Update the animal from a saved event; the caller owns the transaction."""
    animal = await db.get(Animal, animal_id)
    if animal is None:
        return
    if await _record_external_reproduction(db, animal, event):
        await db.flush()
        return
    if event.event_type == ReproductiveEventType.SERVICE:
        animal.services_without_conception = (animal.services_without_conception or 0) + 1
    elif event.event_type == ReproductiveEventType.PD_TEST:
        animal.last_pd_date = event.event_date
        if event.pd_result == PDResult.PREGNANT:
            animal.reproductive_status = "pregnant"
            animal.months_pregnant = event.months_pregnant
            animal.services_without_conception = 0
        else:
            animal.reproductive_status = "open"
            animal.months_pregnant = None
    elif event.event_type == ReproductiveEventType.CALVING:
        animal.reproductive_status = "open"
        animal.last_calving_date = event.event_date
        animal.months_pregnant = None
        animal.services_without_conception = 0
    elif event.event_type == ReproductiveEventType.ABORTION:
        animal.reproductive_status = "open"
        animal.months_pregnant = None
    await db.flush()


async def _sync_cycle_calving_status(db, cycle):
    # Adapt the existing cycle without inserting a duplicate standalone event.
    event_type = (ReproductiveEventType.ABORTION if cycle.calving_outcome == CalvingOutcome.ABORTION
                  else ReproductiveEventType.CALVING)
    await _apply_reproductive_status(db, cycle.animal_id, SimpleNamespace(
        event_type=event_type, event_date=cycle.actual_calving_date, source_key=f"cycle:{cycle.id}",
    ))
