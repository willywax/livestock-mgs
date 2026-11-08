# ShambaManager task map
Use this after CLAUDE.md; inspect referenced source before edits. Paths are repository-relative. No changes were made by this analysis.
| Task | Files and anchor | Contract / verification |
|---|---|---|
| Add nullable operational field | backend/models.py:140; backend/schemas.py:104; backend/server.py:98 | Explicit nullable ADD COLUMN IF NOT EXISTS; no create_all reliance |
| Add endpoint | backend/server.py:166; backend/schemas.py:1; frontend/src/lib/api.js:34 | Choose auth explicitly; add request/response models |
| Add page/navigation | frontend/src/App.js:65; frontend/src/components/Layout.jsx:1 | Route + role gate + nav |
| Change daily-log create | backend/server.py:927; frontend/src/pages/NewDailyLog.jsx:560 | Preserve atomic event/stock/outbox transaction |
| Change event edit | backend/server.py:1266; frontend/src/pages/DailyLogDetail.jsx:312 | Stock reversal and immutable integration intent |
| Change event deletion | backend/server.py:1446; backend/registry_sync.py:57 | Currently no revert producer; cover sent/pending cases |
| Add operational event type | backend/models.py:14; backend/schemas.py:104; backend/server.py:2655 | Native enum plan; apply/reverse/replay and both forms |
| Change stock accounting | backend/server.py:2589; backend/server.py:2655; backend/server.py:2812 | Atomic updates, baseline replay, concurrent adjustments |
| Add livestock category | backend/seed_data.py:5; backend/models.py:56; backend/registry_client.py:36 | Seed only runs on empty table; existing DB needs explicit plan |
| Add species | backend/models.py:27; backend/seed_data.py:18; frontend/src/pages/Animals.jsx:1 | Enum migration hazard; Registry has separate Species table |
| Change analytics/birth-sex split | backend/server.py:1990; backend/schemas.py:340; frontend/src/pages/Reports.jsx:1 | Validate actual counts, date boundaries, category naming |
| Change opening balances/import | backend/server.py:439; backend/server.py:695; frontend/src/pages/OpeningBalances.jsx:1 | Recompute affected stock; rollback invalid rows |
| Change local animal fields | backend/models.py:212; backend/schemas.py:454; backend/server.py:3071; frontend/src/pages/Animals.jsx:1 | Do not add competing DOB/cohort/status authority |
| Assign canonical Registry tag | backend/server.py:3280; backend/registry_sync.py:255; frontend/src/pages/RegistrySync.jsx:1 | Validate link and uniqueness before commit |
| Add health event type | backend/models.py:243; backend/schemas.py:558; backend/server.py:3790; frontend/src/pages/FarmHealth.jsx:1 | Native enum + due-date semantics |
| Change dipping/deworming schedule | backend/server.py:3489; backend/server.py:3635; backend/models.py:254 | Rotation policy is not implemented |
| Add vaccine/schedule | backend/models.py:302; backend/server.py:3952; backend/server.py:3814 | Manual due date vs vaccine default vs health interval |
| Change authentication/roles | backend/auth.py:37; backend/server.py:193; frontend/src/context/AuthContext.js:48 | Backend enforcement, not only navigation |
| Change Registry picker/aliases | frontend/src/components/RegistryTagPicker.jsx:17; backend/server.py:4106; backend/registry_client.py:36 | Preserve tag/status pair; confirm sex/category mapping |
| Change outbox/drain/retry | backend/registry_sync.py:30; backend/server.py:4095; backend/tests/test_registry_sync.py:93 | Stable immutable keys, failure taxonomy, concurrent delivery |
| Change reconciliation | backend/registry_report.py:56; frontend/src/pages/RegistrySync.jsx:1 | Consume every page and compare event IDs |
| Change deployment/env | backend/Dockerfile:1; frontend/cloudbuild.yaml:1; README_DEPLOY_GCP.md:19 | Region disagreement; configure env by name, no secrets in docs |
| Add notifications or dairy | backend/models.py:254; backend/server.py:3635; frontend/src/pages/FarmHealth.jsx:1 | New operational module; Registry identity reference only |

## Cross-cutting cautions
High: event creation and individual Animal registration are separate flows; a birth log does not create a calf identity (`backend/server.py:970`, `:3089`).
High: the current wire birth action is CALVED, not the Registry's BIRTH; use mirrored integration.md before changing either side (`backend/registry_sync.py:212`).
Medium: user/status/entity enums and existing non-null fields cannot be safely changed by editing only Python (`backend/models.py:9`).

