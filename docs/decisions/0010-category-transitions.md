# 0010: Configurable category transitions

Date: 2026-11-10. Status: accepted.

## Context
Animals age into the next category (calf -> weaner -> heifer/young bull -> cow) but the register and stock only changed through hand-logged events.

## Decision
- New tables `category_transition_rules` (configurable, seeded at startup, idempotent) and `category_transitions` (audit log). Added by `create_all` with a new PG enum; no existing table changed.
- Transitions are confirmed by staff from a read-only queue (age rules) or fired automatically on a first calving. `_confirm_category_transition` runs in a savepoint and updates the animal, `stock_levels` (guarded decrement, upsert increment) and the audit row together; the route commits.
- Source stock of 0 is refused (409) so stock never goes negative; the calving hook is best-effort so it never blocks a calving record.
- Stock helpers (`apply_event_to_stock`, `reverse_event_stock`, `check_stock_availability`), `_sync_animals_from_event`, auth, `database.py` and `seed_data.py` are unchanged; the seed lives in `server.py` startup.
- Rules use the real category names: the chain is sex-specific (Ndama/Vichinda Dume|Jike -> Achishwa Dume|Jike -> Dume Wadogo / Mitamba -> Koo).

## Consequences
No event row is written, so event-derived reports omit transitions, and a duplicate `category_change` event would double-move stock. Only the standalone calving route triggers the hook (see KNOWN_ISSUES).
