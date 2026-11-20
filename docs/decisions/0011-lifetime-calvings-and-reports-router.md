# 0011: lifetime_calvings counter and a separate reports router

Date: 2026-11-20. Status: accepted.

## Context
Reproduction reports needed a per-animal calving count, and a set of read-only reports. `/api/reports/sales` and `/api/reports/mortality` already existed with their own shapes and consumers.

## Decision
- Add nullable `animals.lifetime_calvings INTEGER` through the startup `ADD COLUMN IF NOT EXISTS` list (additive only). It counts `reproductive_cycles` rows with outcome LIVE_CALF, STILLBIRTH, ASSISTED_LIVE or ASSISTED_DEAD; abortions are excluded.
- Backfill once with a manual UPDATE, then keep it current with `_sync_lifetime_calvings`: best-effort, savepoint-wrapped, warnings only, called from the cycle create/update/delete routes. `_sync_animals_from_event` is not modified.
- New read-only routes live in `backend/reports_router.py` (`reports_router`, prefix `/api/reports`), registered after `api_router`. Only `/calving`, `/reproductive-status` and `/abortions` were added; the existing sales and mortality routes are untouched and must not be shadowed.
- Queries use SQLAlchemy Core and a `row_number()` window (not LATERAL) so the SQLite test suite can run them.

## Consequences
The counter can drift if the recount fails (see KNOWN_ISSUES). A router outside `server.py` is a deliberate exception to "all routes in server.py" for this read-only report family. The column is not exposed by any other API yet.
