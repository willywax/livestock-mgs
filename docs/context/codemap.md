# ShambaManager task map

> **Updated 2026-11-08:** the Herd Tag Registry integration was removed from the application (docs/decisions/0007). Content below was trimmed accordingly; line numbers are from the 2026-10-08 snapshot and have shifted. Treat anything still mentioning the Registry as historical.

Use this after CLAUDE.md; inspect referenced source before edits. Paths are repository-relative. No changes were made by this analysis.
| Task | Files and anchor | Contract / verification |
|---|---|---|
| Add nullable operational field | backend/models.py:140; backend/schemas.py:104; backend/server.py:98 | Explicit nullable ADD COLUMN IF NOT EXISTS; no create_all reliance |
| Add endpoint | backend/server.py:166; backend/schemas.py:1; frontend/src/lib/api.js:34 | Choose auth explicitly; add request/response models |
| Add page/navigation | frontend/src/App.js:65; frontend/src/components/Layout.jsx:1 | Route + role gate + nav |
| Change daily-log create | backend/server.py:927; frontend/src/pages/NewDailyLog.jsx:560 | Preserve atomic event/stock transaction |
| Change event edit | backend/server.py:1266; frontend/src/pages/DailyLogDetail.jsx:312 | Stock reversal and immutable integration intent |
| Change event deletion | backend/server.py (delete_event) | Stock reversal only; no external side effects |
| Add operational event type | backend/models.py:14; backend/schemas.py:104; backend/server.py:2655 | Native enum plan; apply/reverse/replay and both forms |
| Change stock accounting | backend/server.py:2589; backend/server.py:2655; backend/server.py:2812 | Atomic updates, baseline replay, concurrent adjustments |
| Add livestock category | backend/seed_data.py:5; backend/models.py:56 | Seed only runs on empty table; existing DB needs explicit plan |
| Add species | backend/models.py:27; backend/seed_data.py:18; frontend/src/pages/Animals.jsx:1 | Enum migration hazard |
| Change analytics/birth-sex split | backend/server.py:1990; backend/schemas.py:340; frontend/src/pages/Reports.jsx:1 | Validate actual counts, date boundaries, category naming |
| Change opening balances/import | backend/server.py:439; backend/server.py:695; frontend/src/pages/OpeningBalances.jsx:1 | Recompute affected stock; rollback invalid rows |
| Change local animal fields | backend/models.py:212; backend/schemas.py:454; backend/server.py:3071; frontend/src/pages/Animals.jsx:1 | Do not add competing DOB/cohort/status authority |
| Add health event type | backend/models.py:243; backend/schemas.py:558; backend/server.py:3790; frontend/src/pages/FarmHealth.jsx:1 | Native enum + due-date semantics |
| Change dipping/deworming schedule | backend/server.py:3489; backend/server.py:3635; backend/models.py:254 | Rotation policy is not implemented |
| Add vaccine/schedule | backend/models.py:302; backend/server.py:3952; backend/server.py:3814 | Manual due date vs vaccine default vs health interval |
| Change authentication/roles | backend/auth.py:37; backend/server.py:193; frontend/src/context/AuthContext.js:48 | Backend enforcement, not only navigation |
| Change deployment/env | backend/Dockerfile:1; frontend/cloudbuild.yaml:1; README_DEPLOY_GCP.md:19 | Region disagreement; configure env by name, no secrets in docs |
| Add notifications or dairy | backend/models.py:254; backend/server.py:3635; frontend/src/pages/FarmHealth.jsx:1 | New operational module |

| Change reproduction / animal profile (cycles, bulls, BCS, photos, notes, timeline, analytics) | backend/models.py (REPRODUCTION block at end); backend/schemas.py (same heading at end); backend/server.py (block above `include_router`); backend/tests/test_reproduction.py | New routes must stay above `app.include_router(api_router)`; photos need `GCS_BUCKET_NAME` + google-cloud-storage (lazy import) |
| Change the reproduction reports (calving, reproductive status, abortions) or the Reports page tabs | backend/reports_router.py; backend/tests/test_reports_router.py; frontend/src/components/ReportTabs.jsx; frontend/src/pages/Reports.jsx; frontend/src/lib/api.js (report wrappers at end) | Do not add paths that collide with `/api/reports/*` in server.py; `animals.lifetime_calvings` is kept by `_sync_lifetime_calvings` in server.py |
| Change the reproduction dashboard / dialogs | frontend/src/pages/Reproduction.jsx; frontend/src/components/ReproductionDialogs.jsx; frontend/src/lib/api.js (reproduction block at end) | Species constants (gestation, terms, interval thresholds) keyed cattle/sheep/goat; no frontend tests, verify with `npm run build` |
| Change the animal profile page (photos, timeline, tabs) | frontend/src/pages/AnimalDetail.jsx; frontend/src/pages/Animals.jsx (row navigation, `?edit=`/`?transfer=` handoff); frontend/src/lib/api.js (animal profile block at end) | Photos need `GCS_BUCKET_NAME`; reuses ReproductionDialogs.jsx |
| Change the animal register list (filters, count, CSV export) | frontend/src/pages/Animals.jsx (`filteredAnimals`, `countLabel`, `handleExportCsv`, `csvCell`); backend/server.py `_animal_response` + backend/schemas.py `AnimalResponse` (export columns come from these fields) | Export is client-side from `GET /api/animals`; a new column needs the field on `AnimalResponse` first. Sex filter has only male/female (enum) |
| Change event entry forms (daily log add/edit, tag picker, category auto-fill) | frontend/src/components/EventForm.jsx (`handleAnimalsPicked`, `applyEventChange`, `category_auto_filled`); frontend/src/components/AnimalTagPicker.jsx (`onAnimalsPicked`); frontend/src/pages/DailyLogDetail.jsx, NewDailyLog.jsx; frontend/src/components/EventForm.test.jsx | `category_auto_filled` is UI-only and must stay out of the create/update payload builders. Event-type detail blocks in DailyLogDetail use the module-level `typeSpecificTypes` list |
| Change category transitions UI (queue, rules, history) | frontend/src/pages/TransitionQueue.jsx (helpers `groupQueue`, `sexForItem`, `overdueTone`; route `/animals/transitions` in App.js, ADMIN/DATA_ENTRY); frontend/src/pages/Settings.jsx (`TransitionRulesSettings`); frontend/src/pages/AnimalDetail.jsx (`CategoryHistory`); frontend/src/lib/api.js (category transitions block at end); frontend/src/pages/TransitionQueue.test.jsx; backend routes in server.py "Category transitions" block | Queue items have no sex/threshold: join to the rules list by `rule_id`. Confirmed transitions move stock directly and cannot be undone from the UI |

## Cross-cutting cautions
High: event creation and individual Animal registration are separate flows; a birth log does not create a calf identity (`backend/server.py:970`, `:3089`).
Medium: user/status/entity enums and existing non-null fields cannot be safely changed by editing only Python (`backend/models.py:9`).

