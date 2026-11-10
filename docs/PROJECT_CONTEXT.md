# ShambaManager — Project Context (handoff file)

> 2026-11-10 update: daily-log reproductive synchronization and the Daily Log Timeline are implemented locally. See [current behavior, migration and validation](DAILY_REPRODUCTIVE_SYNC.md). The older repository snapshot below is historical.

Refreshed 2026-11-10 from the repo (`main` at `b999dc8` plus an uncommitted working tree). Sections 2, 4-6, 8-11 and 14 were rewritten; the rest was re-checked.

## 1. How to use this file
This is a standalone briefing on the ShambaManager repo (folder name `livestock-mgs`). You (the AI reading it) cannot see the code. Use it to understand the project and to write accurate prompts for Claude Code, which can see the repo.
If a prompt depends on a file's real contents (a function body, a schema, exact line numbers), do not guess: ask the user to paste that file or part of it. Anything marked "Unverified" was inferred, not confirmed by code or a command.
Line numbers quoted from the repo analysis drift quickly; treat them as hints and have Claude Code re-locate them.

## 2. Snapshot
- Project: ShambaManager (a.k.a. SRC stock; repo folder `livestock-mgs`).
- Purpose: multi-location livestock stock and farm-operations app for a ranching business in Tanzania. Livestock are tracked mainly as COUNTS per location + species + category, driven by daily-log events; an individual-animal register, reproduction tracking, farm-health scheduling and reporting sit alongside.
- Users (roles): `admin`, `data_entry` (office staff entering logs), `viewer` (read-only). Login is by phone number + password (JWT).
- Status: actively developed and in use. `docs/KNOWN_ISSUES.md` (K22) records a production check on 2026-11-08 and `git log` records a GCP release of `816dac4` on 2026-11-09; current live state is Unverified.
- Last updated: 2026-11-10.
- Branch/commit: `main` at `b999dc8` ("docs: record GCP release of 816dac4"), 3 commits ahead of `origin/main` per `git rev-list` (push state beyond that is Unverified). The working tree is NOT clean: 23 modified and 11 untracked paths (listed in section 10), nothing of it committed. Older local branches (`ft/*`, `chore/*`, `ft-edit-event`, `ft-schedule`, `new-ft`) were not re-inspected (Unverified).
- Recent feature history (newest first, from `git log` and the working tree): category transitions (rules, queue, confirm, audit; decision 0010, uncommitted); register CSV export, sex filter, event-form category auto-fill (uncommitted); reproductive status board `/reproduction/status` and sidebar navigation (uncommitted); unified event forms (`816dac4`); mortality dashboard, tag reconciliation and date-range filters (`5beb38e`); standalone reproductive events with frontend recording (`ff6314c`); animal identifiers; sales/customers; temp tags; event-to-register sync (decision 0009); animal profile page; reproduction/photos backend (decision 0008); Registry removal (decision 0007); auth hardening of 13 GET routes.
- Event-to-register sync (decision 0009): daily-log events update matching `animals` rows (status, location, category, auto-created animals) and write `animal_location_history`, best-effort after the stock commit; `EventResponse.sync_warnings` reports skipped tags. Birth events with blank/`NEW`/`TEMP` offspring tags auto-create `TEMP-<LOC>-<YYYYMMDD>-NNN` animals; `POST /api/animals/{id}/replace-tag` swaps in the real tag.
- Category transitions (decision 0010, uncommitted): animals move up a sex-specific chain by age (7 and 18 months by default) or on first calving. Confirming changes `animals.category_id` and moves one head between `stock_levels` rows in one transaction; it writes no daily-log event, so do not also log a `category_change` for the same move.

## 3. Tech stack
| Layer | Technology (versions from `backend/requirements.txt`, `frontend/package.json`) |
|---|---|
| Backend language | Python (Dockerfile uses 3.11-slim; local `.venv` ran 3.13 and tests passed) |
| Backend framework | FastAPI 0.110.1, uvicorn 0.25.0, Pydantic 2.12.5 |
| ORM / DB driver | SQLAlchemy 2.0.46 async, asyncpg 0.31.0 |
| Database | PostgreSQL (Neon, per `README_DEPLOY_GCP.md`). Historical PRD said SQLite; the code now targets Postgres |
| Auth libs | python-jose 3.5.0 (JWT HS256, 24h), passlib + bcrypt 3.2.2 |
| Frontend | React 19, react-router-dom 7, CRA 5 (react-scripts 5.0.1) with CRACO 7, Tailwind 3.4, Radix/shadcn-style components, Axios, Recharts 3, Sonner toasts; JSX (no TypeScript) |
| Package managers | pip (backend); yarn.lock committed for frontend, but `npm start` / `npm run build` are the documented scripts |
| Hosting | Google Cloud Run, two services (API container, Nginx-served React build), images via Cloud Build / Container Registry. Checked-in region is `us-central1`; the intended target is `africa-south1` (Unverified which is live) |
| CI/CD | None (no `.github/`, no pipeline files) |
| Alembic | Installed but unused: no migration directory or config |
| Test deps | Backend: `pytest` 9.0.2, `pytest-asyncio` 1.4.1, `aiosqlite`, `httpx`. Frontend: Jest through CRACO with `react-dom` `act` (`@testing-library/react` is NOT installed). Optional runtime dep `google-cloud-storage` (lazy import, animal photos; env `GCS_BUCKET_NAME`) |

## 4. Repo structure
```
livestock-mgs/
  CLAUDE.md                 project instructions for Claude Code (commands, never-list, definition of done)
  docker-compose.test.yml   throwaway PostgreSQL for tests (loopback port 5433; not verified, Docker was off)
  README.md                 placeholder only
  README_DEPLOY_GCP.md      Cloud Run deploy notes (region and one frontend command are out of date)
  backend/
    server.py               ~6,900 lines (129 route handlers): FastAPI app, ALL routes, startup DDL+seed, stock logic, health logic,
                            reproduction, reconciliation, mortality, sales, category-transition blocks (all above `include_router`)
    models.py               SQLAlchemy models and enums (26 tables)
    schemas.py              Pydantic request/response models
    database.py             async engine/session, DATABASE_URL normalisation
    auth.py                 JWT, password hashing, require_roles
    seed_data.py            default categories (Swahili names), bootstrap data
    requirements.txt, Dockerfile, .dockerignore
    tests/                  conftest.py + 13 offline modules (test_auth, test_stock, test_events, test_reproduction, test_repro_events,
                            test_identifiers, test_date_ranges, test_mortality, test_pd_import, test_reconciliation, test_sales,
                            test_reproductive_status_board, test_transitions; SQLite in-memory, runnable)
                            + 3 live-HTTP modules (test_csv_import, test_disease_events, test_dashboard_analytics; off-limits)
  frontend/
    src/App.js              all routes; src/index.js entry
    src/pages/              Dashboard, Locations, LocationDetail, Animals, AnimalDetail, TransitionQueue, RepeatBreeders, Reconciliation,
                            Reproduction, ReproductiveStatusBoard, MortalityDashboard, FarmHealth, DailyLogs, DailyLogDetail,
                            NewDailyLog, OpeningBalances, Reports, Users, Settings, Login
    src/components/         Layout.jsx, SidebarNavigation.jsx, EventForm.jsx, AnimalTagPicker.jsx, DateRangePicker.jsx,
                            ReproductionDialogs.jsx, ReproductiveEventDialog.jsx, ui/ (shadcn-style primitives)
    src/context/AuthContext.js   session/role state
    src/lib/                api.js (Axios wrapper, token interceptor), utils.js, registerCoverage.js
    *.test.jsx              5 frontend test files (EventForm, ReproductiveEventDialog, SidebarNavigation, ReproductiveStatusBoard, TransitionQueue)
    plugins/                CRACO dev plugins (health-check, visual-edits)
    craco.config.js, tailwind.config.js, nginx.conf, Dockerfile, cloudbuild.yaml
  memory/PRD.md             historical product requirements (partly stale; validate against code)
  docs/                     ARCHITECTURE, DATA_MODEL, DEPLOYMENT, DOMAIN, KNOWN_ISSUES, ROADMAP,
                            decisions/ (0001-0010), PROJECT_CONTEXT.md (this file)
  docs/context/             detailed references: architecture, data-model, api, integration, codemap, glossary
  .claude/settings.json     permissions (allow/deny) + one PreToolUse hook
  .claude/hooks/protect-files.py   blocks edits to .env/.db/.log files
  .claude/rules/            backend.md, database.md, frontend.md (path-scoped)
  .claude/agents/reviewer.md       read-only diff reviewer
  .claude/skills/           plan-feature, fix-bug, db-change, ship-check, release, update-docs, update-context, next-improvement
  backend_test.py, backend_test_results.json, test_result.md, commands.txt, design_guidelines.json
                            legacy/ad-hoc root files (not part of the app)
```
Omitted: `.venv`, `node_modules`, `frontend/build`, caches, `.git`. Also present but not source: local DB/log files under `backend/` and `frontend/`; do not read them.

## 5. Architecture
**Request flow:** React pages -> `frontend/src/lib/api.js` (Axios, attaches JWT from localStorage, redirects to login on 401) -> FastAPI `api_router` in `backend/server.py` (prefix `/api`) -> Pydantic schemas -> `AsyncSession` -> PostgreSQL. All business logic lives in `server.py`; there is no service/repository layer.

**Key flows**
1. Daily log: one location + date container with events. Creating a log validates stock, creates events and adjusts `stock_levels` in ONE local commit.
2. Event edit: reverse the old event's stock effect, apply the new one. Event delete: reverse stock and remove the event.
3. Stock: opening balances + events are the history; `stock_levels` is a mutable projection that a recompute endpoint can rebuild. The Animal register is separate from aggregate stock.
4. Farm health: `health_intervals` and `farm_health_events` compute next-due dates; `vaccine_types` can override the interval.
5. Reproduction and animal profile (decisions 0008 and later): `reproductive_cycles`, `reproductive_events` (standalone service/PD/calving/abortion events that update the animal's reproductive status), `bull_assignments`, `bcs_records`, `animal_notes`, `animal_photos` (GCS paths only). Frontend: `/reproduction` dashboard, `/reproduction/status` status board, `/animals/:id` profile, shared species-aware constants in `ReproductionDialogs.jsx`. The backend still defaults expected calving to 283 days for every species (K23).
6. Identity and reconciliation: `animal_identifiers` (several IDs per animal) and `reconciliation_sessions/entries` (tag reconciliation against reader data), pages `/reconciliation` and the PD-test import.
7. Mortality and sales: `death_causes`, `mortality_thresholds` (Settings), `/reports/mortality`; `customers` and `sale_details` back sold events. Pages for `/stock`, `/reports/sales`, `/customers` are linked in the sidebar but NOT implemented (catch-all redirects to Dashboard).
8. Category transitions (decision 0010): `category_transition_rules` (seeded at startup, editable in Settings) and `category_transitions` (audit log). Queue page `/animals/transitions` (admin, data entry) calls the bulk-confirm route; recording a calving auto-moves a heifer to cow once (best-effort).
9. Startup: `server.py` runs `create_all`, nullable `ADD COLUMN IF NOT EXISTS` additions, and seeds categories/default data/vaccines/death causes/transition rules. Starting the backend therefore writes to whatever DB `DATABASE_URL` points at.

**External integrations:** none. The Herd Tag Registry integration was removed 2026-11-08 (`docs/decisions/0007-remove-registry-integration.md`). Table `registry_sync_outbox` and column `animals.registry_tag_id` remain in the database as inert legacy data; no code references the table or writes the column.

**Auth and roles**
- JWT bearer (HS256, 24h) from `/api/auth/login`. Backend helper `require_roles(...)` in `backend/auth.py`; roles are `admin`, `data_entry`, `viewer`.
- Typical split: admins manage users/locations/categories/opening balances/settings/rules; admin + data_entry create logs/events/animals and confirm transitions; viewers read. Not every route follows this; the per-route truth is `docs/context/api.md`.
- Frontend route guards (`App.js`, `Layout.jsx`, `SidebarNavigation.jsx`) are UI-only; backend enforcement is what counts.
- Every business endpoint requires a JWT; public: health, login, three CSV templates (`docs/KNOWN_ISSUES.md` K21).

**Frontend routes** (`frontend/src/App.js`): `/login`, `/`, `/locations`, `/locations/:id`, `/animals`, `/animals/repeat-breeders`, `/animals/transitions`, `/animals/:id`, `/reproduction`, `/reproduction/status`, `/farm-health`, `/daily-logs`, `/daily-logs/new`, `/daily-logs/:id`, `/opening-balances`, `/reports`, `/reports/mortality`, `/reconciliation`, `/admin/users`, `/settings`; redirects `/repeat-breeders`, `/mortality`, `/users`; `*` -> `/`.

## 6. Data model
Tables (all in `backend/models.py`; columns in `docs/context/data-model.md`), 26 in total: `users`, `locations`, `categories`, `opening_balances`, `daily_logs`, `diseases`, `events`, `stock_levels`, `animals`, `health_intervals`, `farm_health_events`, `vaccine_types`, `bull_assignments`, `reproductive_cycles`, `bcs_records`, `animal_photos`, `animal_notes`, `animal_location_history`, `animal_identifiers`, `reconciliation_sessions`, `reconciliation_entries`, `reproductive_events`, `customers`, `sale_details`, `death_causes`, `mortality_thresholds`, `category_transition_rules`, `category_transitions` (plus the legacy `registry_sync_outbox` in the database without a model: inert, never drop).

Relationships (summary): a DailyLog belongs to a Location and has many Events; Events, OpeningBalances and StockLevels reference Location + Category + species; Animals reference Location + Category and carry a nullable inert `registry_tag_id`; transitions reference an animal, a rule and two categories; FarmHealthEvents reference Location (and categories as JSON).

Enums (native PostgreSQL enums; Python/API values are lowercase but the database stores the uppercase member NAMES): UserRole, EventType, SpeciesType {cattle,sheep,goat}, AnimalStatus, AnimalSex {male,female}, HealthEventType, ServiceType, PDResult, ReproductiveCycleStatus, CalvingOutcome, NoteType, ReproductiveEventType, AnimalIdentifierType, CustomerType, TransitionTriggerType {age,event} and others; exact members in `backend/models.py`.

Rules that must always hold
- Stock is per Location + Species + Category; `stock_levels` must equal opening balance + applied events (recompute is the repair path). Category transitions are the one direct writer besides events (guarded atomic UPDATE, no event row).
- Event create/edit/delete must adjust stock symmetrically (apply/reverse), in the same transaction as the event write.
- Transfer subtracts from source and adds to destination atomically; category change stays in one location and moves count between categories atomically.
- Negative stock is blocked for non-admins (admin override exists per PRD; Unverified exact enforcement).
- A locked daily log should not accept changes (Unverified exact enforcement paths).
- Tag identity is local free text (event tag fields, `animals.tag_number`). `animals.registry_tag_id` is inert legacy data: never write it, never drop it.
- `animal_tags` / `offspring_tags` on events are comma-separated text, not normalised tables.
- Schema policy: nullable `ADD COLUMN IF NOT EXISTS` and reviewed new tables only. Never drop, rename, retype or tighten existing columns in routine work. `create_all` does NOT migrate existing tables, enum members, indexes or constraints.

## 7. Business rules and glossary
Domain: counts-based livestock inventory for cattle, sheep and goats across multiple farm locations; categories are shown in Swahili. Event types: birth, death, sold, missing, gift in/out, bought, transfer, category change, abortion (early/mid/late), weaning. Farm health: dipping, deworming, vaccination, each with configurable intervals. Chemical rotation policy/inventory and outbound notifications are NOT implemented.

| Term | Meaning in this code |
|---|---|
| Koo | Breeding females: cows (cattle), does/ewes (goats/sheep) |
| Mitamba | Heifers (the seed also reuses the label for small stock) |
| Achishwa | Weaners (local categories split Dume/Jike) |
| Ndama | Calves; Ndama Dume = bull calves, Ndama Jike = heifer calves |
| Vichinda | Kids/lambs, split Dume/Jike |
| Maksai | Steers / castrated small-stock males |
| Dume Mbegu | Breeding males |
| Dume Wadogo | Young males, separate from breeding males |
| Dume / Jike | Male / Female |
| Shamba | Farm |
| tag_number | Local per-animal tag, unique only within species/location |
| Transition chain | Ndama/Vichinda Dume|Jike -> Achishwa Dume|Jike (7 months) -> Dume Wadogo / Mitamba (18 months) -> Koo (first calving); editable in Settings |
| Opening balance | Starting count per location/species/category/period |
| Daily log | One location+date container of events, lockable |

Conventions: lowercase local enums; sex-specific categories. Persisted category names come from `backend/seed_data.py`: do not rename casually. More terms: `docs/context/glossary.md`.

## 8. Commands
Never put real values for env vars into commands or docs. Names: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL`, `GCS_BUCKET_NAME` (optional; animal photos); frontend tooling `ENABLE_HEALTH_CHECK`, `ENABLE_VISUAL_EDITS`, `WDS_SOCKET_PORT`; container `PORT`. Obsolete and inert (owner may remove from Cloud Run): `REGISTRY_BASE_URL`, `REGISTRY_AUDIENCE`, `REGISTRY_DEATH_STATUS`, `REGISTRY_SOLD_STATUS`, `INTERNAL_SYNC_AUDIENCE`, `SYNC_ALLOWED_SERVICE_ACCOUNTS`.

| Purpose | Command (from) | Status |
|---|---|---|
| Backend install | `python -m pip install -r requirements.txt` (backend) | not verified (an existing `.venv` already had the packages) |
| Import smoke test | `python -c "import server"` (backend; dummy `DATABASE_URL`/`JWT_SECRET` set in the shell) | **verified** 2026-11-10 on the current tree (exit 0; starts nothing, connects to nothing) |
| Backend tests (core) | `cd backend && python -m pytest tests/test_auth.py tests/test_stock.py tests/test_events.py tests/test_reproduction.py -q` | **verified** 2026-11-10: 105 passed. SQLite in-memory, `httpx.ASGITransport`, fixed test `JWT_SECRET`. Not valid evidence for PG enums/JSONB/locking |
| Backend tests (all offline) | same, adding `tests/test_identifiers.py test_repro_events.py test_date_ranges.py test_mortality.py test_pd_import.py test_reconciliation.py test_sales.py test_reproductive_status_board.py test_transitions.py` | **verified** 2026-11-10: 202 passed (~70s). Never run the whole `tests/` folder: it contains the live-HTTP modules |
| Python syntax-level lint | `python -m flake8 --select=E9,F63,F7,F82 .` (backend) | **verified** 2026-11-10: 0 findings. Full `flake8 .` reports ~1,270 style findings, so there is no baseline |
| Test database | `docker compose -f docker-compose.test.yml up -d --wait`, later `... down -v` (repo root) | not verified: Docker daemon was not running. Loopback port 5433, no password |
| Backend run | `python -m uvicorn server:app --reload --port 8000` (backend) | not verified; runs DDL + seeding; denied for Claude in settings, the user runs it, test DB only |
| Live-HTTP tests | `backend/tests/test_disease_events.py`, `test_csv_import.py`, `test_dashboard_analytics.py`, root `backend_test.py` | do not run: they call HTTP at `REACT_APP_BACKEND_URL` and one falls back to a hardcoded remote host if unset |
| Frontend install | `yarn install --frozen-lockfile` (frontend) | not verified (`node_modules` exists) |
| Frontend run | `npm start` (frontend) | not verified |
| Frontend build / lint | `npm run build` (frontend; CRACO includes ESLint) | **verified** 2026-11-10 after the last frontend change: compiled with the same 6 pre-existing `react-hooks/exhaustive-deps` warnings (`DailyLogs`, `Dashboard`, `LocationDetail`, `OpeningBalances`, `Reports`); overwrites the ignored `frontend/build` |
| Frontend tests | `CI=true npx craco test --watchAll=false <path>` (frontend) | ran 2026-11-10 for `EventForm`, `SidebarNavigation`, `TransitionQueue` (passing). `npm test -- --watchAll=false` itself, and the full 5-file set in one run, were not run in this refresh. No DOM testing library: tests use pure helpers or `react-dom` `act` |
| DB migrations | none. Schema changes are startup `create_all` + nullable `ADD COLUMN IF NOT EXISTS` in `backend/server.py` | n/a |
| Backend build/deploy | `gcloud builds submit --tag <image> .` then `gcloud run deploy shamba-backend ...` (backend), see `README_DEPLOY_GCP.md` | not verified; secrets must be bound via env/secret config, not typed into docs |
| Frontend build/deploy | `gcloud builds submit --config cloudbuild.yaml .` then `gcloud run deploy srcstock ...` (frontend) | not verified. The README's `--build-arg` form is out of date; the YAML is authoritative |

## 9. Claude Code workflow
Everything below exists in the repo. Slash commands live in `.claude/skills/<name>/SKILL.md`.

| Command | Use it when | Side effects |
|---|---|---|
| `/plan-feature <idea>` | Starting any feature or change. Clarifies, explores, writes a plan, WAITS for approval | none until approved |
| `/fix-bug <bug or K-id>` | A defect: reproduce, failing test first, fix root cause, verify, update `docs/KNOWN_ISSUES.md` | edits code/tests/docs |
| `/db-change <desc>` | Any schema change (nullable column / new table). Plan, Docker test DB check, rollback, data checks | manual only |
| `/ship-check` | Before committing/merging: runs checks, reviews the diff, checks docs. Reports PASS/FAIL | read-only + runs checks |
| `/release` | Preparing a Cloud Run release: prints the commands, user runs them | manual only; settings deny `gcloud` |
| `/update-docs` | After code changes: syncs `docs/` and `CLAUDE.md` with the diff | edits docs only |
| `/update-context` | Refreshes this file from the repo | manual only; edits this file only |
| `/next-improvement` | Takes the top open `docs/ROADMAP.md` item into `/plan-feature` | none until approved |

- Subagent: `reviewer` (`.claude/agents/reviewer.md`), read-only (Read/Grep/Glob + git diff/log/status/show); checks a diff against `CLAUDE.md`, `.claude/rules/`, `docs/DOMAIN.md`.
- Rules (`.claude/rules/`, loaded by `paths:`): `backend.md`, `database.md`, `frontend.md`.
- Hook (`.claude/settings.json` -> `.claude/hooks/protect-files.py`): PreToolUse on Edit/Write/NotebookEdit; blocks `.env*` (except `*.example`), `*.db`/`*.sqlite*`, `*.log`.
- Permissions: allow = syntax-level flake8, the import smoke test, `npm run build`, `npm test -- --watchAll=false`, the test-DB compose file, read-only git. Deny = reading `.env`/`.db`/`.log`/`node_modules`/`.venv`/`build`, `gcloud`, `git push`, `git reset --hard`, `git clean`, `rm -rf`, the live-HTTP tests, and starting the backend server. If a legitimate command is blocked, ask the user.
- Gitignored local overrides: `CLAUDE.local.md`, `.claude/settings.local.json`.
- Definition of done (from `CLAUDE.md`): syntax lint + import smoke test for backend, `npm run build` for frontend; backend tests when touching auth/stock/events; state what was verified only by reading code; schema via `/db-change` on the test DB only; update affected docs (`docs/*`, `docs/context/*`); update KNOWN_ISSUES / ROADMAP / decisions; run `/update-context` when stack, commands, structure or roadmap change; finish with `/ship-check`.
- Not set up: CI, a format-on-edit hook, a migration-protection hook (no migrations exist).

## 10. Current work
Recent commits on `main` (newest first): `b999dc8` docs: record GCP release of 816dac4; `816dac4` unify event forms and fix event type updates; `5beb38e` mortality dashboard, tag reconciliation, date-range filters; `ff6314c` standalone reproductive events and frontend recording; `9077b23` checkpoint of the animal identifier work; `57199a2` temp-tag UI; `c08f9db` events wired to the animal register.

Uncommitted working tree (23 modified, 11 untracked as of this refresh; nothing is committed or pushed by Claude):
- Reproductive status board: backend route + `ReproductiveStatusBoard.jsx`, `SidebarNavigation.jsx`, `ReproductiveEventDialog.jsx`, tests.
- Animal register: sex filter, "X of Y" count, client-side CSV export (`last_calving_date` now exposed on `AnimalResponse`); event-form category auto-fill (`EventForm.jsx`, `AnimalTagPicker.jsx`); the `DailyLogDetail.jsx` crash fix (undefined `typeSpecificTypes`).
- Category transitions: backend tables/routes/hook (`models.py`, `schemas.py`, `server.py`, `tests/test_transitions.py`, decision 0010) and frontend (`TransitionQueue.jsx`, Settings rules card, AnimalDetail "Category history", `api.js` additions).
- Docs touched along the way: ARCHITECTURE, DATA_MODEL, DOMAIN, KNOWN_ISSUES, ROADMAP, context/api, context/codemap, context/data-model, this file.

Open follow-ups: commit and review the working tree; browser verification of the new pages (transition queue, Settings rules, status board, register export, event-form auto-fill); sidebar links `/stock`, `/reports/sales`, `/customers` lead to unimplemented pages; the first-calving transition hook covers only the standalone reproductive-events route (see KNOWN_ISSUES); no undo exists for a confirmed transition.
Known issues: `docs/KNOWN_ISSUES.md` (open: K01, K07, K11, K14-K26, plus un-numbered sections for the status-board navigation, register CSV export and category transitions; K02-K06, K08-K10, K12-K13 resolved). Headline themes: credential hygiene, public CSV templates (K21), stock concurrency (K07, no row lock on `stock_levels`), thin Postgres-level test coverage (the SQLite suite cannot check enums/locking), GCS and several new UIs unverified in a browser, a species-blind gestation default (K23), and inert legacy Registry data. Credentials that were once committed must be rotated by the owner.

## 11. Roadmap
Full table: `docs/ROADMAP.md` (sizes are estimates, Unverified). Dairy is out of scope (owner decision).
1. R2 Fail-closed secret/bootstrap handling; owner rotates credentials — medium.
2. R4 Backend tests: an offline SQLite suite of 13 modules (202 tests) exists; remaining: verify the Docker test DB, Postgres-backed and concurrency tests — medium.
3. R6 Atomic stock updates + positive-count validation — medium.
4. R8 Align deployment config; owner removes obsolete Registry env vars/scheduler — small.
5. R10 Frontend CI (needs approval); a few frontend test files now exist but there is no pipeline and no DOM testing library — medium.
6. R11 Chemical rotation and notifications — large.
7. R12 done (animal profile page); remaining is browser verification (K25) — small.
8. R13 Backend species filter/gestation for reproduction (K23) — small.

## 12. Constraints
Never, or only with explicit owner approval:
- Deploy, run `gcloud`, or touch production data/credentials; run live-HTTP tests against anything unverified; send real messages.
- Print, log, commit or paste secret values or connection strings; edit tracked `.env` files.
- Start the backend purely to "look around" (it runs DDL/seeding).
- Drop/rename/retype/tighten columns, or edit enum Python classes without a PostgreSQL enum plan. Only nullable additive columns and reviewed new tables.
- Add or rely on Alembic without a separate, reviewed decision.
- Reintroduce Registry/outbox/sync code, write `animals.registry_tag_id`, or drop the legacy outbox table/column.
- Rename persisted category names in `backend/seed_data.py`.
- Change auth/session code (`backend/auth.py`, `frontend/src/lib/api.js`, `context/AuthContext.js`) without explicit approval and tests (the owner has approved append-only additions to `api.js` for specific features).
- Change Dockerfiles, `cloudbuild.yaml`, `nginx.conf`.
- Change the stock helpers (`apply_event_to_stock`, `reverse_event_stock`, `check_stock_availability`) or `_sync_animals_from_event` unless the task is about them.
Must never break: stock arithmetic and the atomic event+stock commit; role enforcement on the backend.

## 13. How to write prompts for this repo
Structure every prompt: goal in one sentence; area (backend/frontend/both); files to read first; constraints from section 12; required checks; "plan first, wait for approval" for anything touching stock, events or schema.
- Start from a slash command: `/plan-feature` for features, `/fix-bug` for defects, `/db-change` for schema, `/next-improvement` for the top roadmap item, `/ship-check` to finish, `/update-docs` then `/update-context` after docs-relevant changes. Tell Claude Code to run the command by name.
- Files to name: use `docs/context/codemap.md` rows. Common sets: stock/events -> `backend/server.py`, `backend/models.py`, `backend/schemas.py`, `frontend/src/pages/NewDailyLog.jsx`, `DailyLogDetail.jsx`, `frontend/src/components/EventForm.jsx`; health -> `backend/server.py` (health section), `frontend/src/pages/FarmHealth.jsx`; auth -> `backend/auth.py`, `frontend/src/context/AuthContext.js`; transitions -> `backend/server.py` ("Category transitions" block), `frontend/src/pages/TransitionQueue.jsx`.
- Checks to require: `flake8 --select=E9,F63,F7,F82` and `python -c "import server"` (dummy env) in `backend/`, `npm run build` for frontend work, the backend pytest command for auth/stock/event work (name modules explicitly, never the whole `tests/` folder), docs updated per the definition of done. State which behaviours were verified only by reading code (Postgres-specific behaviour is outside the SQLite suite).
- Tell it what NOT to do: run live-HTTP tests, start the server against anything but the Docker test DB, run `gcloud`, push, or touch `.env` files.
- Gotcha: scripts with long quoted heredocs can fail in the Bash tool here; Claude Code works around it by writing a script file first.

Example prompt:
> Run /plan-feature: make the daily-log event editor reject non-positive counts. Area: backend + `frontend/src/pages/DailyLogDetail.jsx`. Read `backend/schemas.py` (EventCreate/EventUpdate), the event-update route in `backend/server.py`, `docs/context/api.md` and `docs/KNOWN_ISSUES.md` (K07). Do not change stock apply/reverse logic or the schema. Wait for my approval of the plan. After approval: implement, then run /ship-check and report each step as pass/fail/skipped.

## 14. Open questions / Unverified
1. Which region/environment is live (`us-central1` vs `africa-south1`), and is there staging? Owner has not answered; Unverified.
2. Real deployment process and secret configuration; `docs/DEPLOYMENT.md` release/rollback steps are standard-practice guesses. What the 2026-11-09 GCP release (`816dac4`) actually included beyond the commit message is not re-checked.
3. The Docker test DB (`docker-compose.test.yml`) and running anything against it: not verified because Docker was not running.
4. Whether `pip install -r backend/requirements.txt` and `yarn install --frozen-lockfile` work on a clean machine; `npm start` and plain `npm test` not run.
5. PostgreSQL-specific behaviour is outside the SQLite suite: native enum creation (including the new transition enum and two new tables), `FOR UPDATE` locks, the savepoint race path for creating a missing stock row, negative-stock override, locked-log edits.
6. GCS signed URLs on Cloud Run (needs a signing-capable service account and `GCS_BUCKET_NAME`) and real photo upload/delete: K22 records a production check on 2026-11-08; not re-checked.
7. Browser behaviour of recent pages (`/animals/transitions`, Settings rules card, AnimalDetail category history, `/reproduction/status`, register CSV export, event-form category auto-fill, `/reproduction`, `/animals/:id`): verified by `npm run build` and unit tests only, never exercised in a browser.
8. Whether older local branches (`ft-schedule`, `new-ft`, `origin/fx-changes`, merged `ft/*`/`chore/*`) hold unmerged work or can be deleted.
9. Whether the working tree should be split into several commits and when it is pushed; the push state of `main` beyond "3 commits ahead of origin/main".
10. Owner's must-never-break list beyond what the code and `memory/PRD.md` imply (guess used: stock never negative without admin override, atomic transfers/category changes, locked logs immutable).
11. Whether CI should be added; roadmap sizes and priorities are estimates; whether sheep/goat transition ages (copied from cattle: 7 and 18 months) are right for the farm.
12. Whether exposed credentials in git history have been rotated (assumed not).
