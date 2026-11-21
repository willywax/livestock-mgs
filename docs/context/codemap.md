# ShambaManager task map

> **2026-11-21:** `backend/server.py` and `backend/models.py` were split (decision 0012). File and line anchors below that cite `backend/server.py:NNN` or `backend/models.py:NNN` describe the pre-split files (git `5ddbe1b`); find the current location in [backend-map.md](backend-map.md).

> **Updated 2026-11-08:** the Herd Tag Registry integration was removed from the application (docs/decisions/0007). Content below was trimmed accordingly; line numbers are from the 2026-10-08 snapshot and have shifted. Treat anything still mentioning the Registry as historical.

Use this after CLAUDE.md and [backend-map.md](backend-map.md); inspect referenced source before edits. Paths are repository-relative. No changes were made by this analysis.
| Task | Files and anchor | Contract / verification |
|---|---|---|
| Add nullable operational field | backend/models/<domain>.py; backend/schemas/; backend/bootstrap.py (`apply_additive_ddl`) | Explicit nullable ADD COLUMN IF NOT EXISTS; no create_all reliance |
| Add endpoint | backend/routers/<domain>.py (register in routers/__init__.py); backend/schemas/; frontend/src/lib/api.js | Choose auth explicitly; add request/response models |
| Add page/navigation | frontend/src/App.js:65; frontend/src/components/Layout.jsx:1 | Route + role gate + nav |
| Change daily-log create | backend/routers/daily_logs.py (create_daily_log); frontend/src/pages/NewDailyLog.jsx:560 | Preserve atomic event/stock transaction |
| Change event edit | backend/routers/daily_logs.py (update_event); frontend/src/pages/DailyLogDetail.jsx:312 | Stock reversal and immutable integration intent |
| Change event deletion | backend/routers/daily_logs.py (delete_event) | Stock reversal only; no external side effects |
| Add operational event type | backend/models/enums.py; backend/schemas/; backend/services/stock.py | Native enum plan; apply/reverse/replay and both forms |
| Change stock accounting | backend/services/stock.py; backend/services/stock_snapshot.py | Atomic updates, baseline replay, concurrent adjustments |
| Add livestock category | backend/seed_data.py; backend/models/core.py | Seed only runs on empty table; existing DB needs explicit plan |
| Add species | backend/models/enums.py; backend/seed_data.py; frontend/src/pages/Animals.jsx:1 | Enum migration hazard |
| Change analytics/birth-sex split | backend/routers/reports.py (get_analytics_report); backend/schemas/; frontend/src/pages/Reports.jsx:1 | Validate actual counts, date boundaries, category naming |
| Change opening balances/import | backend/routers/imports.py; backend/routers/opening_balances.py; frontend/src/pages/OpeningBalances.jsx:1 | Recompute affected stock; rollback invalid rows |
| Change local animal fields | backend/models/animals.py; backend/schemas/; backend/routers/animals.py; frontend/src/pages/Animals.jsx:1 | Do not add competing DOB/cohort/status authority |
| Add health event type | backend/models/enums.py, models/health.py; backend/schemas/; backend/routers/farm_health.py; frontend/src/pages/FarmHealth.jsx:1 | Native enum + due-date semantics |
| Change dipping/deworming schedule | backend/routers/farm_health.py; backend/models/health.py | Rotation policy is not implemented |
| Add vaccine/schedule | backend/models/health.py; backend/routers/vaccine_types.py; backend/routers/farm_health.py | Manual due date vs vaccine default vs health interval |
| Change authentication/roles | backend/auth.py; backend/routers/auth.py; frontend/src/context/AuthContext.js:48 | Backend enforcement, not only navigation |
| Change deployment/env | backend/Dockerfile:1; frontend/cloudbuild.yaml:1; README_DEPLOY_GCP.md:19 | Region disagreement; configure env by name, no secrets in docs |
| Add notifications or dairy | backend/models/health.py; backend/routers/farm_health.py; frontend/src/pages/FarmHealth.jsx:1 | New operational module |

| Change reproduction / animal profile (cycles, bulls, BCS, photos, notes, timeline, analytics) | backend/models/reproduction.py, models/animals.py; backend/schemas/ (same heading at end); backend/routers/reproductive_*.py, bull_assignments.py, bcs_records.py, animal_photos.py, animal_notes.py, animal_timeline.py, reproduction_analytics.py; backend/tests/test_reproduction.py | New routers go into `ROUTERS` in routers/__init__.py; photos need `GCS_BUCKET_NAME` + google-cloud-storage (lazy import) |
| Change the reproduction reports (calving, reproductive status, abortions) or the Reports page tabs | backend/reports_router.py; backend/tests/test_reports_router.py; frontend/src/components/ReportTabs.jsx; frontend/src/pages/Reports.jsx; frontend/src/lib/api.js (report wrappers at end) | Do not add paths that collide with `/api/reports/*` in routers/reports.py, sales.py, mortality.py; `animals.lifetime_calvings` is kept by `_sync_lifetime_calvings` in routers/reproductive_cycles.py |
| Change the reproduction dashboard / dialogs | frontend/src/pages/Reproduction.jsx; frontend/src/components/ReproductionDialogs.jsx; frontend/src/lib/api.js (reproduction block at end) | Species constants (gestation, terms, interval thresholds) keyed cattle/sheep/goat; no frontend tests, verify with `npm run build` |
| Change the animal profile page (photos, timeline, tabs) | frontend/src/pages/AnimalDetail.jsx; frontend/src/pages/Animals.jsx (row navigation, `?edit=`/`?transfer=` handoff); frontend/src/lib/api.js (animal profile block at end) | Photos need `GCS_BUCKET_NAME`; reuses ReproductionDialogs.jsx |
| Change the animal register list (filters, count, CSV export) | frontend/src/pages/Animals.jsx (`filteredAnimals`, `countLabel`, `handleExportCsv`, `csvCell`); backend/routers/animals.py `_animal_response` + backend/schemas/ `AnimalResponse` (export columns come from these fields) | Export is client-side from `GET /api/animals`; a new column needs the field on `AnimalResponse` first. Sex filter has only male/female (enum) |
| Change event entry forms (daily log add/edit, tag picker, category auto-fill) | frontend/src/components/EventForm.jsx (`handleAnimalsPicked`, `applyEventChange`, `category_auto_filled`); frontend/src/components/AnimalTagPicker.jsx (`onAnimalsPicked`); frontend/src/pages/DailyLogDetail.jsx, NewDailyLog.jsx; frontend/src/components/EventForm.test.jsx | `category_auto_filled` is UI-only and must stay out of the create/update payload builders. Event-type detail blocks in DailyLogDetail use the module-level `typeSpecificTypes` list |
| Change category transitions UI (queue, rules, history) | frontend/src/pages/TransitionQueue.jsx (helpers `groupQueue`, `sexForItem`, `overdueTone`; route `/animals/transitions` in App.js, ADMIN/DATA_ENTRY); frontend/src/pages/Settings.jsx (`TransitionRulesSettings`); frontend/src/pages/AnimalDetail.jsx (`CategoryHistory`); frontend/src/lib/api.js (category transitions block at end); frontend/src/pages/TransitionQueue.test.jsx; backend routers/transitions.py + services/transitions.py | Queue items have no sex/threshold: join to the rules list by `rule_id`. Confirmed transitions move stock directly and cannot be undone from the UI |

## Cross-cutting cautions
High: event creation and individual Animal registration are separate flows; a birth log does not create a calf identity (`backend/routers/daily_logs.py`, `backend/routers/animals.py`).
Medium: user/status/entity enums and existing non-null fields cannot be safely changed by editing only Python (`backend/models/enums.py`).

