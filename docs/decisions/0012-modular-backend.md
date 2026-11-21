# 0012: Split server.py and models.py into routers, services and models packages

Date: 2026-11-21. Status: accepted.

## Context
`backend/server.py` had grown to 7,437 lines (all routes, startup DDL/seed, stock accounting, animal-register sync, transitions) and `backend/models.py` to 708 lines. Humans and AI agents had to load or grep a huge file to change one domain, and line-number anchors in the docs went stale on every edit.

## Decision
- `server.py` is wiring only (env, CORS, startup/shutdown, router registration). `uvicorn server:app` and the Dockerfile are unchanged.
- Endpoints move verbatim to `backend/routers/<domain>.py` (28 modules, each `router = APIRouter()`), registered in `routers/__init__.py` `ROUTERS`, then mounted under the `/api` prefix. Order is significant: `transitions` precedes `animals`.
- Helpers used by more than one router, or by startup, live in `backend/services/` (stock, stock_snapshot, animal_sync, transitions, reproduction, mortality, common, seed). Dependency direction is `routers -> services -> models`; no router imports another router.
- Startup DDL and seeding move to `backend/bootstrap.py` (`apply_additive_ddl`, `seed_initial_data`, `run_startup`). The statements are unchanged and still additive only.
- `models.py` becomes the `backend/models/` package (enums, core, animals, health, reproduction, reconciliation, sales, mortality). `models/__init__.py` re-exports every class so `from models import X` keeps working.
- `schemas.py` (1,399 lines) becomes the `backend/schemas/` package, 14 domain modules, re-exported from `__init__.py` (added later the same day; OpenAPI still identical).
- No logic was changed. Function names are unchanged, so OpenAPI operation ids are unchanged.

## Verification (2026-11-21)
- OpenAPI JSON before/after: identical. 137 routes; the relative order of every pair of overlapping paths is unchanged.
- PostgreSQL `CREATE TABLE`/`CREATE INDEX` output compiled from old and new models: identical (80 statements).
- SQLite suite (all mocked test modules, live-HTTP ones excluded): 246 passed before and after.
- Not verifiable here: startup against PostgreSQL (DDL/seed code was moved, not edited) and the live deployment.

## Consequences
- Tests must monkeypatch the module that uses a name (for example `routers.animal_photos._gcs_upload`, `services.animal_sync._find_animal`), not `server`. Existing tests were updated.
- Underscore-prefixed helpers are imported across modules by name; they were not renamed to avoid logic churn.
- Still large: `routers/daily_logs.py` (818), `routers/reports.py` (729), `routers/animals.py` (678), `services/animal_sync.py` (587). See ROADMAP R14.
- Docs that cite `backend/server.py:NNN` or `backend/models.py:NNN` and were written before this date refer to the old files (git commit 5ddbe1b); use docs/context/backend-map.md to find the current location.
