# ShambaManager — Project Context (handoff file)

## 1. How to use this file
This is a standalone briefing on the ShambaManager repo (folder name `livestock-mgs`). You (the AI reading it) cannot see the code. Use it to understand the project and to write accurate prompts for Claude Code, which can see the repo.
If a prompt depends on a file's real contents (a function body, a schema, exact line numbers), do not guess: ask the user to paste that file or part of it. Anything marked "Unverified" was inferred, not confirmed by code or a command.
Line numbers quoted from the repo analysis drift quickly; treat them as hints and have Claude Code re-locate them.

## 2. Snapshot
- Project: ShambaManager (a.k.a. SRC stock; repo folder `livestock-mgs`).
- Purpose: multi-location livestock stock and farm-operations app for a ranching business in Tanzania. Livestock are tracked mainly as COUNTS per location + species + category, driven by daily-log events; an individual-animal register, farm-health scheduling and reporting sit alongside.
- Users (roles): `admin`, `data_entry` (office staff entering logs), `viewer` (read-only). Login is by phone number + password (JWT).
- Status: actively developed, in use (Unverified: the repo's deploy guide names live domains, but no deployment was inspected).
- Last updated: 2026-11-08.
- Branch/commit: `main` at `2f11adf` ("feat: animal profile page ..."), working tree clean as of this refresh, 20 commits ahead of `origin/main`; NOTHING IS PUSHED (the owner pushes manually after rotating the exposed credentials, K01/K20). The housekeeping branches (`chore/claude-setup`, `chore/remove-registry`, `ft/r1-auth-hardening`) and the feature branches (`ft/repro-schema`, `ft/repro-frontend`, `ft/animal-detail`) are all merged into local `main` (the repro branches via `--no-ff` merge commits) and can be deleted; `ft-edit-event`, `ft-schedule`, `new-ft` appear stale/merged (Unverified).
- Event-to-register sync (decision 0009, uncommitted at time of writing): saving, editing or deleting a daily-log event now updates matching `animals` rows (status, location, category, auto-created animals) and writes `animal_location_history`, best-effort after the stock commit; `EventResponse.sync_warnings` reports skipped tags. New routes `GET /api/animals/{id}/location-history` and `GET /api/animals/register-reconciliation`.
- Changes since the Claude setup, all on `main`: Registry removal (decision 0007), auth hardening on 13 GET routes (R1), a SQLite in-memory backend test suite, the reproduction/animal-profile backend (5 new tables, 5 new enums, 24 routes; decision 0008, no existing class/column/route/enum modified), and the frontend `/reproduction` dashboard plus `/animals/:id` profile page.

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
| Optional / test deps | `google-cloud-storage` (lazy import, animal photos only; needs env `GCS_BUCKET_NAME`); `pytest`, `pytest-asyncio`, `aiosqlite`, `httpx` for the SQLite test suite |

## 4. Repo structure
```
livestock-mgs/
  CLAUDE.md                 project instructions for Claude Code (commands, never-list, definition of done)
  docker-compose.test.yml   throwaway PostgreSQL for tests (loopback port 5433; not verified, Docker was off)
  README.md                 placeholder only
  README_DEPLOY_GCP.md      Cloud Run deploy notes (region and one frontend command are out of date)
  backend/
    server.py               ~4,860 lines (86 route handlers): FastAPI app, ALL routes, startup DDL+seed, stock logic, health logic, reproduction block (above `include_router`)
    models.py               SQLAlchemy models and enums
    schemas.py              Pydantic request/response models
    database.py             async engine/session, DATABASE_URL normalisation
    auth.py                 JWT, password hashing, require_roles
    seed_data.py            default categories (Swahili names), bootstrap data
    requirements.txt, Dockerfile, .dockerignore
    tests/                  conftest.py + test_auth/test_stock/test_events/test_reproduction (SQLite in-memory, runnable) + 3 live-HTTP modules (off-limits)
  frontend/
    src/App.js              all routes; src/index.js entry
    src/pages/              Dashboard, Locations, LocationDetail, Animals, AnimalDetail, Reproduction, FarmHealth, DailyLogs,
                            DailyLogDetail, NewDailyLog, OpeningBalances, Reports, Users, Settings,
                            Login
    src/components/         Layout.jsx, ReproductionDialogs.jsx, ui/ (46 shadcn-style primitives)
    src/context/AuthContext.js   session/role state
    src/lib/api.js          Axios wrapper, token interceptor
    plugins/                CRACO dev plugins (health-check, visual-edits)
    craco.config.js, tailwind.config.js, nginx.conf, Dockerfile, cloudbuild.yaml
  memory/PRD.md             historical product requirements (partly stale; validate against code)
  docs/                     ARCHITECTURE, DATA_MODEL, DEPLOYMENT, DOMAIN, KNOWN_ISSUES, ROADMAP,
                            decisions/ (0001-0008), PROJECT_CONTEXT.md (this file)
  docs/context/             detailed references: architecture, data-model, api, integration, codemap, glossary
  .claude/settings.json     permissions (allow/deny) + one PreToolUse hook
  .claude/hooks/protect-files.py   blocks edits to .env/.db/.log files
  .claude/rules/            backend.md, database.md, frontend.md (path-scoped)
  .claude/agents/reviewer.md       read-only diff reviewer
  .claude/skills/           plan-feature, fix-bug, db-change, ship-check, release, update-docs,
                            update-context, next-improvement
  backend_test.py, backend_test_results.json, test_result.md, commands.txt, design_guidelines.json
                            legacy/ad-hoc root files (not part of the app)
```
Omitted: `.venv`, `node_modules`, `frontend/build`, caches, `.git`. Also present but not source: local DB/log files under `backend/` and `frontend/`; do not read them.

## 5. Architecture
**Request flow:** React pages -> `frontend/src/lib/api.js` (Axios, attaches JWT from localStorage, redirects to login on 401) -> FastAPI `api_router` in `backend/server.py` (prefix `/api`) -> Pydantic schemas -> `AsyncSession` -> PostgreSQL. All business logic lives in `server.py`; there is no service/repository layer.

**Key flows**
1. Daily log: a log is one location + date container with events. Creating a log validates stock, creates events and adjusts `stock_levels` in ONE local commit.
2. Event edit: reverse the old event's stock effect, apply the new one. Event delete: reverse stock and remove the event.
3. Stock: opening balances + events are the history; `stock_levels` is a mutable projection that a recompute endpoint can rebuild. The Animal register is separate from aggregate stock.
4. Farm health: `health_intervals` (per event type/species/location) and `farm_health_events` compute next-due dates; `vaccine_types` can override the interval; "upcoming/overdue" views feed the UI.
5. Reproduction and animal profile (decision 0008): `reproductive_cycles` (one row per service/pregnancy/calving of a FEMALE animal, derived intervals), `bull_assignments`, `bcs_records`, `animal_notes`, `animal_photos` (GCS object paths only, signed URLs on read). Frontend: `/reproduction` dashboard and `/animals/:id` profile share `frontend/src/components/ReproductionDialogs.jsx`, which holds the species-aware gestation days, terminology and calving-interval thresholds (cattle/sheep/goat). The backend still defaults expected calving to 283 days for every species (K23).
6. Startup: `server.py` runs `create_all`, a few nullable `ADD COLUMN IF NOT EXISTS` additions, and seeds categories/default data/vaccines. Starting the backend therefore writes to whatever DB `DATABASE_URL` points at.

**External integrations:** none. The Herd Tag Registry integration was removed 2026-11-08 (`docs/decisions/0007-remove-registry-integration.md`, `docs/context/integration.md`). Table `registry_sync_outbox` and column `animals.registry_tag_id` remain in the database as inert legacy data; no code references the table or writes the column.

**Auth and roles**
- JWT bearer (HS256, 24h) from `/api/auth/login` (phone + password). Backend helper `require_roles(...)` in `backend/auth.py`; roles are `admin`, `data_entry`, `viewer`.
- Typical split: admins manage users/locations/categories/opening balances/settings/health config and updates; admin + data_entry create logs/events/animals; viewers read. Not every route follows this; the per-route truth is in `docs/context/api.md`.
- Frontend route guards (in `App.js`/`Layout.jsx`) are UI-only; backend enforcement is what counts.
- Every business endpoint requires a JWT; public: health, login, three CSV templates (`docs/KNOWN_ISSUES.md` K21). Per-route auth: `docs/context/api.md`.

**Frontend routes** (`frontend/src/App.js`): `/login`, `/`, `/locations`, `/locations/:id`, `/animals`, `/animals/:id`, `/reproduction`, `/farm-health`, `/daily-logs`, `/daily-logs/new`, `/daily-logs/:id`, `/opening-balances`, `/reports`, `/admin/users`, `/settings`.

## 6. Data model
Tables (all in `backend/models.py`; full column list in `docs/context/data-model.md`): `users`, `locations`, `categories`, `opening_balances`, `daily_logs`, `diseases`, `events`, `stock_levels`, `animals`, `health_intervals`, `farm_health_events`, `vaccine_types` (12), plus the reproduction/profile tables `bull_assignments`, `reproductive_cycles`, `bcs_records`, `animal_photos`, `animal_notes`, plus `animal_location_history` (18 in total; decisions 0008, 0009). A legacy table `registry_sync_outbox` still exists in the database without a model (inert; never drop).

Relationships (summary): a DailyLog belongs to a Location and has many Events; Events and OpeningBalances and StockLevels reference Location + Category + species; Animals reference Location + Category and carry a nullable inert legacy `registry_tag_id` string; FarmHealthEvents reference Location (and categories as JSON).

Enums (native PostgreSQL enums; Python/API values are lowercase but the database stores the uppercase member NAMES): UserRole {admin,data_entry,viewer}; EventType {birth, death, sold, missing, gift_in, gift_out, bought, transfer, category_change, abortion, weaning}; SpeciesType {cattle,sheep,goat}; AnimalStatus {active,sold,dead,transferred,missing}; AnimalSex {male,female}; HealthEventType {dipping,vaccination,deworming,log}; new: ServiceType {natural,ai}, PDResult {pregnant,open,repeat}, ReproductiveCycleStatus {open,served,pregnant,calved,aborted}, CalvingOutcome {live_calf,stillbirth,abortion,assisted_live,assisted_dead}, NoteType {observation,weight,measurement,incident,health,other}.

Rules that must always hold
- Stock is per Location + Species + Category; `stock_levels` must equal opening balance + applied events (recompute is the repair path).
- Event create/edit/delete must adjust stock symmetrically (apply/reverse), in the same transaction as the event write.
- Transfer subtracts from source and adds to destination atomically; category change stays in one location and moves count between categories atomically.
- Negative stock is blocked for non-admins (admin override exists per PRD; Unverified exact enforcement).
- A locked daily log should not accept changes (Unverified exact enforcement paths).
- Tag identity is local free text (event tag fields, `animals.tag_number`). `animals.registry_tag_id` is inert legacy data: never write it, never drop it. Local Animal birth date/status are Shamba's own data.
- `animal_tags` / `offspring_tags` on events are comma-separated text, not normalised tables.
- Schema policy: only nullable `ADD COLUMN IF NOT EXISTS` additions. Never drop, rename, retype or tighten existing columns in routine work. `create_all` does NOT migrate existing tables, enum members, indexes or constraints.

## 7. Business rules and glossary
Domain: counts-based livestock inventory for cattle, sheep and goats across multiple farm locations; categories are shown in Swahili. Event types: birth, death, sold, missing, gift in/out, bought, transfer, category change, abortion (early/mid/late), weaning. Farm health: dipping, deworming, vaccination, each with configurable intervals and overdue/upcoming views. Chemical rotation policy/inventory and outbound notifications (email/SMS) are NOT implemented.

| Term | Meaning in this code |
|---|---|
| Koo | Breeding females: cows (cattle), does/ewes (goats/sheep) |
| Mitamba | Heifers (the seed also reuses the label for small stock) |
| Achishwa | Weaners (local categories split Dume/Jike) |
| Ndama | Calves; Ndama Dume = bull calves, Ndama Jike = heifer calves |
| Vichinda | Kids/lambs, split Dume/Jike |
| Maksai | Steers / castrated small-stock males |
| Mbegu / Dume Mbegu | Breeding males (local seed says Dume Mbegu) |
| Dume Wadogo | Young males, separate from breeding males |
| Dume / Jike | Male / Female |
| Shamba | Farm |
| tag_number | Local per-animal tag, unique only within species/location |
| registry_tag_id | Inert legacy nullable column on animals (indexed, not unique); never written by code |
| Opening balance | Starting count per location/species/category/period |
| Daily log | One location+date container of events, lockable |

Conventions: lowercase local enums; sex-specific categories. Persisted category names come from `backend/seed_data.py`: do not rename casually. More terms: `docs/context/glossary.md`.

## 8. Commands
Never put real values for env vars into commands or docs. Names: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL`, `GCS_BUCKET_NAME` (optional; animal photos); frontend tooling `ENABLE_HEALTH_CHECK`, `ENABLE_VISUAL_EDITS`, `WDS_SOCKET_PORT`; container `PORT`. Obsolete and inert (owner may remove from Cloud Run): `REGISTRY_BASE_URL`, `REGISTRY_AUDIENCE`, `REGISTRY_DEATH_STATUS`, `REGISTRY_SOLD_STATUS`, `INTERNAL_SYNC_AUDIENCE`, `SYNC_ALLOWED_SERVICE_ACCOUNTS`.

| Purpose | Command (from) | Status |
|---|---|---|
| Backend install | `python -m pip install -r requirements.txt` (backend) | not verified (an existing `.venv` already had the packages) |
| Import smoke test | `python -c "import server"` (backend; dummy `DATABASE_URL`/`JWT_SECRET` set in the shell) | **verified** 2026-11-08 on `main` (`IMPORT_OK`; starts nothing, connects to nothing). See next row for the automated suite |
| Backend tests | `cd backend && python -m pytest tests/test_auth.py tests/test_stock.py tests/test_events.py tests/test_reproduction.py -q` (backend) | **verified** 2026-11-08 on `main`: 80 passed (40 functions) in 8-11s depending on machine load (the original three modules alone: 45 passed). SQLite in-memory (aiosqlite), `httpx.ASGITransport`, fixed `JWT_SECRET=test-secret-key`, function-scoped DB; needs `pytest-asyncio`. Not valid evidence for PG enums/JSONB/locking. Do not include the live-HTTP modules |
| Python syntax-level lint | `python -m flake8 --select=E9,F63,F7,F82 .` (backend) | **verified** 2026-11-08 on `main`: 0 findings. Full `flake8 .` reports ~1,270 style findings, so there is no baseline |
| Test database | `docker compose -f docker-compose.test.yml up -d --wait`, later `... down -v` (repo root) | not verified: Docker daemon was not running. Loopback port 5433, no password; set `DATABASE_URL` in the shell |
| Backend run | `python -m uvicorn server:app --reload --port 8000` (backend) | not verified (a startup attempt against a dead DB port failed as expected). Runs DDL + seeding; denied for Claude in settings, the user runs it, test DB only |
| Live-HTTP tests | `backend/tests/test_disease_events.py`, `test_csv_import.py`, `test_dashboard_analytics.py`, root `backend_test.py` | not verified, do not run blindly: they call HTTP at `REACT_APP_BACKEND_URL` and `test_disease_events.py` falls back to a hardcoded remote preview host if unset |
| Frontend install | `yarn install --frozen-lockfile` (frontend) | not verified (`node_modules` exists) |
| Frontend run | `npm start` (frontend) | not verified |
| Frontend build / lint | `npm run build` (frontend; CRACO includes ESLint, no separate lint script) | **verified** 2026-11-08 on `main`: compiled with 6 warnings, all pre-existing `react-hooks/exhaustive-deps` in `DailyLogs`, `Dashboard`, `LocationDetail`, `OpeningBalances`, `Reports` (none from the new pages); overwrites the ignored `frontend/build` |
| Frontend tests | `npm test -- --watchAll=false` (frontend) | not verified; no tracked frontend test files exist |
| DB migrations | none. Schema changes are startup `create_all` + nullable `ADD COLUMN IF NOT EXISTS` in `backend/server.py` | n/a |
| Backend build/deploy | `gcloud builds submit --tag <image> .` then `gcloud run deploy shamba-backend ...` (backend), see `README_DEPLOY_GCP.md` | not verified; region in the guide is `us-central1`, target is `africa-south1`; secrets must be bound via env/secret config, not typed into docs |
| Frontend build/deploy | `gcloud builds submit --config cloudbuild.yaml .` then `gcloud run deploy srcstock ...` (frontend) | not verified. The README's `--build-arg` form is out of date; the YAML is authoritative |

## 9. Claude Code workflow
Everything below is in the repo on `main`. Slash commands live in `.claude/skills/<name>/SKILL.md`.

| Command | Use it when | Side effects |
|---|---|---|
| `/plan-feature <idea>` | Starting any feature or change. Clarifies, explores, writes a plan, WAITS for approval | none until approved |
| `/fix-bug <bug or K-id>` | A defect: reproduce, failing test first, fix root cause, verify, update `docs/KNOWN_ISSUES.md` | edits code/tests/docs |
| `/db-change <desc>` | Any schema change (nullable column / new table). Plan, Docker test DB check, rollback, data checks | manual only (`disable-model-invocation`) |
| `/ship-check` | Before committing/merging: runs import smoke test, syntax lint, `npm run build`, reviews diff, checks docs. Reports PASS/FAIL | read-only + runs checks |
| `/release` | Preparing a Cloud Run release: prints the commands, user runs them | manual only; settings deny `gcloud` |
| `/update-docs` | After code changes: syncs `docs/` and `CLAUDE.md` with the diff | edits docs only |
| `/update-context` | Refreshes this file from the repo | manual only; edits this file only |
| `/next-improvement` | Takes the top open `docs/ROADMAP.md` item into `/plan-feature` | none until approved |

- Subagent: `reviewer` (`.claude/agents/reviewer.md`), read-only (Read/Grep/Glob + git diff/log/status/show); checks a diff against `CLAUDE.md`, `.claude/rules/`, `docs/DOMAIN.md`.
- Rules (`.claude/rules/`, loaded by `paths:`): `backend.md` (backend/**/*.py), `database.md` (models.py, database.py, seed_data.py), `frontend.md` (frontend/src/**).
- Hook (`.claude/settings.json` -> `.claude/hooks/protect-files.py`): PreToolUse on Edit/Write/NotebookEdit; blocks `.env*` (except `*.example`), `*.db`/`*.sqlite*`, `*.log`. Fails open on bad input. Tested with harmless cases 2026-11-08.
- Permissions: allow = syntax-level flake8, the import smoke test, `npm run build`, `npm test -- --watchAll=false`, the test-DB compose file, read-only git. Deny = reading `.env`/`.db`/`.log`/`node_modules`/`.venv`/`build`, `gcloud`, `git push`, `git reset --hard`, `git clean`, `rm -rf`, the live-HTTP tests, and starting the backend server. If a legitimate command is blocked, ask the user.
- Gitignored local overrides: `CLAUDE.local.md`, `.claude/settings.local.json`.
- Definition of done (from `CLAUDE.md`): syntax lint + import smoke test for backend, `npm run build` for frontend; schema via `/db-change` on the test DB only; update affected docs (`docs/*`, `docs/context/*`); update `docs/KNOWN_ISSUES.md` / `docs/ROADMAP.md` / `docs/decisions/`; run `/update-context` when stack, commands, structure or roadmap change; finish with `/ship-check`.
- Not set up: CI, a format-on-edit hook (no formatter config exists), a migration-protection hook (no migrations exist).

## 10. Current work
Recent commits on `main` (newest first): `2f11adf` animal profile page; `f46877d` reproduction dashboard, dialogs, species-aware UI; `474c076` reproduction schema, photos and analytics backend; `de065a0` SQLite backend test suite; `84978f2`/`a079e11` auth hardening (R1); `f541c55`/`3596c2e`/`06ea03e` Registry removal; `ef8c5a8`/`867cff4`/`5a40a64` Claude config, docs and test compose file. Before the setup the history ended at `9b72555` "Support registry tag edits and birth counts by sex". Most-changed files recently: `backend/server.py`, `backend/models.py`, `backend/schemas.py`, `frontend/src/lib/api.js`, `frontend/src/pages/Reproduction.jsx`, `AnimalDetail.jsx`.
In progress: nothing is mid-flight. Everything above is merged into local `main` and unpushed. Open follow-ups: browser verification of the new Reproduction and animal-profile UI against real data and a GCS bucket (K22, K24, K25); backend species filter and gestation defaults (R13, K23); deleting the merged local branches (owner's call). R1 auth hardening put JWT auth on 13 previously open GET routes; health, login and three CSV template downloads stay public (K21). Next candidates: ROADMAP R2 (fail-closed secrets, owner rotates credentials), R4 remainder (Postgres-backed tests), R13. No other open tasks identified (Unverified: no tracker).
Known issues: `docs/KNOWN_ISSUES.md` (open: K01, K07, K11, K14-K25; K02 closed by the auth hardening; K03-K06, K08-K10, K12-K13 resolved by the Registry removal). Headline themes only: credential hygiene, public CSV templates (K21), concurrency, thin test coverage (SQLite suite covers auth/stock/events/reproduction only), the new reproduction/photo features being unverified on PostgreSQL, GCS and in a browser (K22, K24, K25), a species-blind gestation default in the backend (K23), and inert legacy Registry data to clean up by the owner. Credentials that were once committed must be rotated by the owner.

## 11. Roadmap
Full table: `docs/ROADMAP.md` (sizes are estimates, Unverified). Dairy is out of scope (owner decision).
1. R2 Fail-closed secret/bootstrap handling; owner rotates credentials — medium.
2. R4 Backend test suite (SQLite suite for auth/stock/events/reproduction exists; remaining: verify the Docker test DB, Postgres-backed and concurrency tests, wider coverage) — medium.
3. R6 Atomic stock updates + positive-count validation — medium.
4. R8 Align deployment config; owner removes obsolete Registry env vars/scheduler — small.
5. R10 Frontend tests + CI (needs approval) — medium.
6. R11 Chemical rotation and notifications — large.
7. R12 done (animal profile page `/animals/:id`); remaining is browser verification (K25) — small.
8. R13 Backend species filter/gestation for reproduction (K23) — small.

## 12. Constraints
Never, or only with explicit owner approval:
- Deploy, run `gcloud`, or touch production data/credentials; run live-HTTP tests against anything unverified; send real messages.
- Print, log, commit or paste secret values or connection strings; edit tracked `.env` files.
- Start the backend purely to "look around" (it runs DDL/seeding).
- Drop/rename/retype/tighten columns, or edit enum Python classes without a PostgreSQL enum plan. Only nullable additive columns.
- Add or rely on Alembic without a separate, reviewed decision.
- Reintroduce Registry/outbox/sync code, write `animals.registry_tag_id`, or drop the legacy outbox table/column.
- Rename persisted category names in `backend/seed_data.py`.
- Change auth/session code (`backend/auth.py`, `frontend/src/lib/api.js`, `context/AuthContext.js`) without explicit approval and tests.
- Change Dockerfiles, `cloudbuild.yaml`, `nginx.conf`.
Must never break: stock arithmetic and the atomic event+stock commit; role enforcement on the backend.

## 13. How to write prompts for this repo
Structure every prompt: goal in one sentence; area (backend/frontend/both); files to read first; constraints from section 12; required checks; "plan first, wait for approval" for anything touching stock, events or schema.
- Start from a slash command: `/plan-feature` for features, `/fix-bug` for defects, `/db-change` for schema, `/next-improvement` to take the top roadmap item, `/ship-check` to finish, `/update-docs` then `/update-context` after docs-relevant changes. Tell Claude Code to run the command by name.
- Files to name: use `docs/context/codemap.md` rows. Common sets: stock/events -> `backend/server.py`, `backend/models.py`, `backend/schemas.py`, `frontend/src/pages/NewDailyLog.jsx`, `DailyLogDetail.jsx`; health -> `backend/server.py` (health section), `frontend/src/pages/FarmHealth.jsx`; auth -> `backend/auth.py`, `frontend/src/context/AuthContext.js`.
- Checks to require: `flake8 --select=E9,F63,F7,F82` and `python -c "import server"` (dummy env) in `backend/`, `npm run build` for frontend work, docs updated per the definition of done. Run the backend pytest command from section 8 for auth/stock/event work, and state which behaviours were verified only by reading code (Postgres-specific behaviour is outside the SQLite suite).
- Tell it what NOT to do: run live-HTTP tests, start the server against anything but the Docker test DB, run `gcloud`, push, or touch `.env` files.

Example prompt:
> Run /plan-feature: make the daily-log event editor reject non-positive counts. Area: backend + `frontend/src/pages/DailyLogDetail.jsx`. Read `backend/schemas.py` (EventCreate/EventUpdate), the event-update route in `backend/server.py`, `docs/context/api.md` and `docs/KNOWN_ISSUES.md` (K07). Do not change stock apply/reverse logic or the schema. Wait for my approval of the plan. After approval: implement, then run /ship-check and report each step as pass/fail/skipped.

## 14. Open questions / Unverified
1. Which region/environment is live (`us-central1` vs `africa-south1`), and is there staging? Owner has not answered; Unverified.
2. Real deployment process and secret configuration; the `docs/DEPLOYMENT.md` release/rollback steps are standard-practice guesses.
3. The Docker test DB (`docker-compose.test.yml`) and starting the backend against it: not verified because Docker was not running.
4. Whether `pip install -r backend/requirements.txt` and `yarn install --frozen-lockfile` work on a clean machine (the new `google-cloud-storage` and `pytest-asyncio` lines were not installed from the file); `npm start` and `npm test` not run.
5. Per-route roles beyond `docs/context/api.md` and all Postgres-specific behaviour (enums, JSONB, locking) are outside the SQLite suite; negative-stock override, locked-log edits and the admin-only add-event route are covered by SQLite tests only.
6. Reproduction/profile backend (decision 0008): PostgreSQL table/enum creation on a real DB (DDL was compiled offline only), GCS signed URLs on Cloud Run (needs a signing-capable service account and `GCS_BUCKET_NAME`), real photo upload/delete: Unverified (K22).
7. The `/reproduction` and `/animals/:id` pages were verified by `npm run build` only: layout, mobile behaviour, popover/dialog interaction, the Animals Edit/Transfer round trip and species-filtered KPIs have never been exercised in a browser (K24, K25).
8. Whether `ft-schedule`, `new-ft`, `origin/fx-changes` hold unmerged work; whether the merged local branches should be deleted.
9. Owner's must-never-break list beyond what the code and `memory/PRD.md` imply (guess used: stock never negative without admin override, atomic transfers/category changes, locked logs immutable).
10. Whether CI should be added; roadmap sizes and priorities are estimates.
11. Whether exposed credentials in git history have been rotated (assumed not); `main` is unpushed until they are.
