# Backend module map

Read this first for any backend task. Since decision 0012 (2026-11-21) the former 7,437-line `backend/server.py` and 708-line `backend/models.py` are split by domain. Behaviour, URLs, OpenAPI and DDL are unchanged (verified: identical OpenAPI JSON, identical PostgreSQL `CREATE TABLE`/`CREATE INDEX` output, same 246 SQLite tests).

## Layout
```
backend/
  server.py        app wiring only: env, CORS, startup/shutdown, router registration (~70 lines)
  bootstrap.py     startup: create_all + additive DDL (ADD COLUMN/VALUE/INDEX IF NOT EXISTS) + seed data
  routers/         HTTP endpoints, one module per domain; each exposes `router = APIRouter()`
    __init__.py    ROUTERS list = registration ORDER (matters, see below)
  services/        helpers shared by several routers (no endpoints)
  models/          ORM tables + enums by domain; `from models import X` still works
  schemas/         Pydantic contracts by domain; `from schemas import X` still works (re-exported in __init__.py)
  reports_router.py  read-only reproduction reports, prefix /api/reports (included after ROUTERS)
  auth.py, database.py, seed_data.py   unchanged
```

## routers/ (all under `/api`)
| Module | Lines | Routes | Owns |
|---|---|---|---|
| `routers/animal_identifiers.py` | 216 | 5 | Animal identifiers (EID, brand, ...) and the identifier import. `/admin/import/animal-identifiers`, `/animals/{id}/identifiers` |
| `routers/animal_notes.py` | 82 | 4 | Animal notes |
| `routers/animal_photos.py` | 232 | 4 | Photos in Google Cloud Storage (`_gcs_*` helpers, `MAX_PHOTO_BYTES` live here) |
| `routers/animal_timeline.py` | 117 | 2 | Animal activity timelines |
| `routers/animals.py` | 678 | 12 | Animal register: list/create/update, bulk import, lookup, repeat breeders, transfer, replace-tag, location history, `/templates/animals` |
| `routers/auth.py` | 108 | 6 | Login, `/auth/me`, user CRUD |
| `routers/bcs_records.py` | 98 | 4 | Body-condition scores |
| `routers/bull_assignments.py` | 123 | 4 | Bull assignments |
| `routers/daily_logs.py` | 818 | 8 | Daily logs, add/edit/delete events, lock. Calls `services/stock` + `services/animal_sync` in one transaction |
| `routers/dashboard.py` | 274 | 1 | `/dashboard` |
| `routers/farm_health.py` | 484 | 12 | Farm-health events, intervals, upcoming, last events |
| `routers/imports.py` | 259 | 4 | CSV templates and imports (locations, opening balances) |
| `routers/locations.py` | 74 | 4 | Locations |
| `routers/mortality.py` | 203 | 7 | Death causes, mortality thresholds, `/reports/mortality` |
| `routers/opening_balances.py` | 128 | 3 | Opening balances |
| `routers/pd_import.py` | 99 | 1 | `/admin/import/pd-tests` |
| `routers/reconciliation.py` | 162 | 4 | Physical tag reconciliation sessions |
| `routers/reference_data.py` | 114 | 5 | Categories, diseases |
| `routers/reports.py` | 729 | 4 | `/reports/daily`, `/range`, `/analytics` (about 500 lines), `/detailed` |
| `routers/reproduction_analytics.py` | 196 | 1 | `/analytics/reproduction` |
| `routers/reproductive_cycles.py` | 255 | 6 | Cycles, `/animals/{id}/reproductive-history`, `_sync_lifetime_calvings` |
| `routers/reproductive_events.py` | 109 | 4 | Standalone reproductive events/summary, `/admin/tasks/sync-reproductive-status` |
| `routers/sales.py` | 230 | 9 | Customers, sale details, `/reports/sales` |
| `routers/status_board.py` | 107 | 1 | `/reproduction/status-board` |
| `routers/stock_levels.py` | 62 | 2 | `/stock-levels`, `/stock-levels/recompute` |
| `routers/system.py` | 8 | 1 | `GET /api/` |
| `routers/transitions.py` | 126 | 7 | Category-transition rules, queue, confirm endpoints |
| `routers/vaccine_types.py` | 159 | 5 | Vaccine types, `/farm-health-events/last-vaccinations` |

## services/
| Module | Lines | Owns |
|---|---|---|
| `services/stock.py` | 385 | `check_stock_availability`, `apply_event_to_stock`, `reverse_event_stock`, `adjust_stock`, `recompute_stock_levels`. Keep apply/reverse symmetric |
| `services/stock_snapshot.py` | 101 | `build_stock_snapshot`, `build_location_totals_from_snapshot` (dashboard, reports) |
| `services/animal_sync.py` | 587 | Daily-log event -> animal register sync, temp tags, daily reproduction replay/backfill, reversal. Best-effort: failures are logged and never break the log save |
| `services/transitions.py` | 286 | Seed rules, build queue, `_confirm_category_transition`, age helpers |
| `services/reproduction.py` | 44 | `_apply_reproductive_status`, `_sync_cycle_calving_status` |
| `services/mortality.py` | 14 | `_validate_death_cause` |
| `services/common.py` | 41 | `_ANY_ROLE`, gestation/breeding constants, `_require_animal`, `_require_location`, `_CYCLE_LOAD` |
| `services/seed.py` | 10 | `_seed_death_causes` (raw SQL, used by bootstrap) |

## models/
| Module | Owns |
|---|---|
| `models/enums.py` | every enum (native PostgreSQL enums; see /db-change before editing members) |
| `models/core.py` | User, Location, Category, OpeningBalance, DailyLog, Disease, Event, EventAnimalLink, StockLevel |
| `models/animals.py` | Animal, AnimalLocationHistory, AnimalPhoto, AnimalNote, AnimalIdentifier, CategoryTransitionRule, CategoryTransition |
| `models/health.py` | HealthInterval, FarmHealthEvent, VaccineType |
| `models/reproduction.py` | BullAssignment, ReproductiveCycle, BCSRecord, ReproductiveEvent |
| `models/reconciliation.py` | ReconciliationSession, ReconciliationEntry |
| `models/sales.py` | Customer, SaleDetail |
| `models/mortality.py` | DeathCause, MortalityThreshold |

`models/__init__.py` imports every module (required so `create_all` and string `relationship()` targets see all tables) and re-exports every class, so route code keeps `from models import Animal`.

## schemas/
`auth`, `reference` (locations, categories, opening balances, diseases), `daily_logs` (events + logs), `stock`, `dashboard`, `reports`, `animals`, `animal_profile` (photos, notes, timelines), `health`, `reproduction` (cycles, BCS, analytics, repro events, PD import, status board), `reconciliation`, `sales`, `mortality`, `transitions`. A new schema goes into the matching module and into the import list in `schemas/__init__.py`. Only dependency between modules: `reports -> dashboard`.

## Rules for working in this layout
- **Dependency direction:** `routers -> services -> models`. Services never import routers; routers never import each other. If two routers need a helper, move it to `services/`. A dependency cycle check was clean at split time.
- **Route order:** `routers/__init__.py` `ROUTERS` is the registration order. Static paths must be registered before a dynamic sibling (`transitions` before `animals` because of `/animals/transition-queue` vs `/animals/{animal_id}`). New router: create `routers/<domain>.py` with `router = APIRouter()`, add it to the import and to `ROUTERS` in a safe position, and keep the explicit auth (`require_roles` / `get_current_user`) on every route.
- **Tests patch where a name is used**, not where it is defined: monkeypatch `routers.animal_photos._gcs_upload`, `services.animal_sync._find_animal`, `services.transitions._confirm_category_transition`, never `server.*`.
- **Imports are by name** (`from services.stock import apply_event_to_stock`). Patching the source module will not affect an already-imported name in another module.
- New table: add to the matching `models/<domain>.py` and to the lists in `models/__init__.py`; additive DDL goes in `bootstrap.py` via `/db-change`.
- Biggest files, candidates for a later split (no urgency): `routers/daily_logs.py`, `routers/reports.py` (the analytics handler), `routers/animals.py`, and `services/animal_sync.py`.
- Names with a leading underscore are still imported across modules (kept as-is to avoid touching logic). Treat them as module-internal to `services/` and the owning router.

## Where to change what
| Task | Files |
|---|---|
| Add endpoint to an existing domain | `routers/<domain>.py` + `schemas/<domain>.py` + `frontend/src/lib/api.js` |
| Daily-log create/edit/delete | `routers/daily_logs.py`, `services/stock.py`, `services/animal_sync.py` |
| Stock accounting | `services/stock.py` (+ `tests/test_stock.py`) |
| Register sync from events | `services/animal_sync.py` (+ `tests/test_sync.py`) |
| Category transitions | `services/transitions.py`, `routers/transitions.py` |
| Reproduction | `routers/reproductive_*.py`, `routers/bull_assignments.py`, `routers/bcs_records.py`, `services/reproduction.py`, `reports_router.py` |
| Reports / dashboard | `routers/reports.py`, `routers/dashboard.py`, `services/stock_snapshot.py` |
| Startup DDL / seeds | `bootstrap.py`, `services/seed.py`, `seed_data.py` |
| Auth / roles | `auth.py`, `routers/auth.py` (needs explicit approval, see CLAUDE.md) |
