# 0009: Wire daily-log events to the individual animal register

Date: 2026-11-08. Status: accepted.

## Context
Daily-log events change aggregate stock only; the individual `animals` register had to be edited by hand and drifted from stock.

## Decision
- After the stock commit, `_sync_animals_from_event` updates animals named in `events.animal_tags` / `offspring_tags` (status, location, category, auto-create for bought/gift_in/birth). It runs in its own try/except and transaction, never raises, and returns warnings surfaced as `EventResponse.sync_warnings`.
- `_reverse_animal_sync` undoes the old event's register effects (status back to active, transfer moved back and its history row removed, category restored) before an event is edited or deleted; it never deletes auto-created animals.
- New table `animal_location_history` records TRANSFER moves. New read routes: location history per animal and a register-vs-stock reconciliation.
- Stock helpers (`apply_event_to_stock`, `reverse_event_stock`, `check_stock_availability`) are unchanged.
- Sex for auto-created animals is inferred from the seeded category name; when it cannot be, the animal is not created and a warning is returned (`animals.sex` is NOT NULL and cannot be relaxed under the additive-schema policy, decision 0005).
- bought/gift_in never reactivates a dead or sold animal (warning instead).

## Consequences
Register changes are not atomic with the stock change (by design); see KNOWN_ISSUES K26. No frontend change yet.
