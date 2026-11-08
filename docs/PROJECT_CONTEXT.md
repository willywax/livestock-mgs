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
- Branch/commit: working branch `chore/claude-setup`, created from `main` at `9b72555` ("Support registry tag edits and birth counts by sex"); `main` was 4 commits ahead of `origin/main`. Local branches `ft-edit-event` (same commit as main), `ft-schedule` and `new-ft` appear stale/merged (Unverified). The setup commits (untracked env/DB/log files, Claude config, docs) sit on `chore/claude-setup`; nothing is pushed or merged.
- No application code was changed by the setup work.
- Sibling repo: the Herd Tag Registry (folder `tags-src`, next to this repo) owns authoritative animal tag identity. Not visible from this repo.

## 3. Tech stack
| Layer | Technology (versions from `backend/requirements.txt`, `frontend/package.json`) |
|---|---|
| Backend language | Python (Dockerfile uses 3.11-slim; local `.venv` ran 3.13 and tests passed) |
| Backend framework | FastAPI 0.110.1, uvicorn 0.25.0, Pydantic 2.12.5 |
| ORM / DB driver | SQLAlchemy 2.0.46 async, asyncpg 0.31.0 |
| Database | PostgreSQL (Neon, per `README_DEPLOY_GCP.md`). Historical PRD said SQLite; the code now targets Postgres |
| Auth libs | python-jose 3.5.0 (JWT HS256, 24h), passlib + bcrypt 3.2.2; google-auth for service-to-service OIDC |
| HTTP client | httpx 0.28.1 (Registry client) |
| Frontend | React 19, react-router-dom 7, CRA 5 (react-scripts 5.0.1) with CRACO 7, Tailwind 3.4, Radix/shadcn-style components, Axios, Recharts 3, Sonner toasts; JSX (no TypeScript) |
| Package managers | pip (backend); yarn.lock committed for frontend, but `npm start` / `npm run build` are the documented scripts |
| Hosting | Google Cloud Run, two services (API container, Nginx-served React build), images via Cloud Build / Container Registry. Checked-in region is `us-central1`; the intended target is `africa-south1` (Unverified which is live) |
| CI/CD | None (no `.github/`, no pipeline files) |
| Alembic | Installed but unused: no migration directory or config |

## 4. Repo structure
```
livestock-mgs/
  CLAUDE.md                 project instructions for Claude Code (commands, never-list, definition of done)
  docker-compose.test.yml   throwaway PostgreSQL for tests (loopback port 5433; not verified, Docker was off)
  README.md                 placeholder only
  README_DEPLOY_GCP.md      Cloud Run deploy notes (region and one frontend command are out of date)
  backend/
    server.py               ~4,170 lines: FastAPI app, ALL routes, startup DDL+seed, stock logic, health logic
    models.py               SQLAlchemy models and enums
    schemas.py              Pydantic request/response models
    database.py             async engine/session, DATABASE_URL normalisation
    auth.py                 JWT, password hashing, require_roles
    registry_auth.py        OIDC verification for the internal drain endpoint
    registry_client.py      httpx client to the external Tag Registry, category/status aliases
    registry_sync.py        outbox builder, drain/retry logic
    registry_report.py      reconciliation report vs the Registry
    seed_data.py            default categories (Swahili names), bootstrap data
    requirements.txt, Dockerfile, .dockerignore
    tests/                  conftest.py + 7 test modules (4 mocked, 3 live-HTTP)
  frontend/
    src/App.js              all routes; src/index.js entry
    src/pages/              Dashboard, Locations, LocationDetail, Animals, FarmHealth, DailyLogs,
                            DailyLogDetail, NewDailyLog, OpeningBalances, Reports, Users, Settings,
                            RegistrySync, Login
    src/components/         Layout.jsx, RegistryTagPicker.jsx, ui/ (46 shadcn-style primitives)
    src/context/AuthContext.js   session/role state
    src/lib/api.js          Axios wrapper, token interceptor
    plugins/                CRACO dev plugins (health-check, visual-edits)
    craco.config.js, tailwind.config.js, nginx.conf, Dockerfile, cloudbuild.yaml
  memory/PRD.md             historical product requirements (partly stale; validate against code)
  docs/                     ARCHITECTURE, DATA_MODEL, DEPLOYMENT, DOMAIN, KNOWN_ISSUES, ROADMAP,
                            decisions/ (0001-0006), PROJECT_CONTEXT.md (this file)
  docs/context/             detailed references: architecture, data-model, api, integration, codemap, glossary
  .claude/settings.json     permissions (allow/deny) + one PreToolUse hook
  .claude/hooks/protect-files.py   blocks edits to .env/.db/.log files
  .claude/rules/            backend.md, database.md, registry-sync.md, frontend.md (path-scoped)
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
1. Daily log: a log is one location + date container with events. Creating a log validates stock, creates events, adjusts `stock_levels` and writes any Registry outbox rows in ONE local commit; Registry delivery happens after commit.
2. Event edit: reverse the old event's stock effect, apply the new one. Event delete: reverse stock and remove the event.
3. Stock: opening balances + events are the history; `stock_levels` is a mutable projection that a recompute endpoint can rebuild. The Animal register is separate from aggregate stock.
4. Farm health: `health_intervals` (per event type/species/location) and `farm_health_events` compute next-due dates; `vaccine_types` can override the interval; "upcoming/overdue" views feed the UI.
5. Startup: `server.py` runs `create_all`, a few nullable `ADD COLUMN IF NOT EXISTS` additions, and seeds categories/default data/vaccines. Starting the backend therefore writes to whatever DB `DATABASE_URL` points at.

**Integration with the Herd Tag Registry (Shamba -> Registry only)**
- Outbound calls via `backend/registry_client.py`: tag search (proxied for the browser picker), reconcile feed, status change (death/sold), event log (birth, tag assignment), revert.
- Outbox table `registry_sync_outbox` (states PENDING/SENT/FAILED/CONFLICT) with idempotency keys of the form `<action>:<event_id>`; a drain endpoint `/api/internal/sync/drain` is intended for a scheduler using OIDC service auth. No scheduler definition exists in the repo (Unverified how it runs in production).
- Admins use `/api/internal/sync/report` and a retry endpoint through the UI page `/admin/registry-sync`.
- The wire vocabulary between the two services is not fully aligned; read `docs/context/integration.md` before touching it.

**Auth and roles**
- JWT bearer (HS256, 24h) from `/api/auth/login` (phone + password). Backend helper `require_roles(...)` in `backend/auth.py`; roles are `admin`, `data_entry`, `viewer`.
- Typical split: admins manage users/locations/categories/opening balances/settings/health config and updates; admin + data_entry create logs/events/animals; viewers read. Not every route follows this; the per-route truth is in `docs/context/api.md`.
- Frontend route guards (in `App.js`/`Layout.jsx`) are UI-only; backend enforcement is what counts.
- Internal drain endpoint uses Google OIDC, configured through environment variables.
- Known access-control gaps exist: see `docs/KNOWN_ISSUES.md` and `docs/context/api.md` (per-route auth).

**Frontend routes** (`frontend/src/App.js`): `/login`, `/`, `/locations`, `/locations/:id`, `/animals`, `/farm-health`, `/daily-logs`, `/daily-logs/new`, `/daily-logs/:id`, `/opening-balances`, `/reports`, `/admin/users`, `/settings`, `/admin/registry-sync`.

## 6. Data model
Tables (all in `backend/models.py`; full column list in `docs/context/data-model.md`): `users`, `locations`, `categories`, `opening_balances`, `daily_logs`, `diseases`, `events`, `stock_levels`, `animals`, `health_intervals`, `farm_health_events`, `vaccine_types`, `registry_sync_outbox` (13).

Relationships (summary): a DailyLog belongs to a Location and has many Events; Events and OpeningBalances and StockLevels reference Location + Category + species; Animals reference Location + Category and optionally carry a `registry_tag_id` (a string pointing into the Registry, no cross-DB foreign key); FarmHealthEvents reference Location (and categories as JSON); outbox rows reference an Event or Animal and a Registry tag id.

Enums (native PostgreSQL enums, values lowercase): UserRole {admin,data_entry,viewer}; EventType {birth, death, sold, missing, gift_in, gift_out, bought, transfer, category_change, abortion, weaning}; SpeciesType {cattle,sheep,goat}; AnimalStatus {active,sold,dead,transferred,missing}; AnimalSex {male,female}; HealthEventType {dipping,vaccination,deworming,log}; RegistrySyncAction/State as above.

Rules that must always hold
- Stock is per Location + Species + Category; `stock_levels` must equal opening balance + applied events (recompute is the repair path).
- Event create/edit/delete must adjust stock symmetrically (apply/reverse), in the same transaction as the event write and the outbox insert.
- Transfer subtracts from source and adds to destination atomically; category change stays in one location and moves count between categories atomically.
- Negative stock is blocked for non-admins (admin override exists per PRD; Unverified exact enforcement).
- A locked daily log should not accept changes (Unverified exact enforcement paths).
- The Registry owns tag identity, date of birth, birth cohort, production stage and tag status. `production_stage` and `status` are independent concepts; do not merge them. Shamba's local Animal birth date/status are legacy competing writes: do not extend that pattern.
- Event + stock + outbox commit locally BEFORE any remote delivery. Never reuse an idempotency key for a corrected payload.
- `animal_tags` / `offspring_tags` on events are comma-separated text, not normalised tables.
- Schema policy: only nullable `ADD COLUMN IF NOT EXISTS` additions. Never drop, rename, retype or tighten existing columns in routine work. `create_all` does NOT migrate existing tables, enum members, indexes or constraints.

## 7. Business rules and glossary
Domain: counts-based livestock inventory for cattle, sheep and goats across multiple farm locations; categories are shown in Swahili. Event types: birth, death, sold, missing, gift in/out, bought, transfer, category change, abortion (early/mid/late), weaning. Farm health: dipping, deworming, vaccination, each with configurable intervals and overdue/upcoming views. Chemical rotation policy/inventory and outbound notifications (email/SMS) are NOT implemented.

| Term | Meaning in this code |
|---|---|
| Koo | Breeding females: cows (cattle), does/ewes (goats/sheep) |
| Mitamba | Heifers (the seed also reuses the label for small stock) |
| Achishwa | Weaners (local categories split Dume/Jike; the Registry groups them) |
| Ndama | Calves; Ndama Dume = bull calves, Ndama Jike = heifer calves |
| Vichinda | Kids/lambs, split Dume/Jike |
| Maksai | Steers / castrated small-stock males |
| Mbegu / Dume Mbegu | Breeding males (Registry spells category MBEGU; local seed says Dume Mbegu) |
| Dume Wadogo | Young males, separate from breeding males |
| Dume / Jike | Male / Female |
| Shamba | Farm |
| EPC | RFID electronic product code (recognised by the Registry import) |
| Tag ID / tag_id | Canonical Registry tag string |
| tag_number | Local per-animal tag, unique only within species/location |
| registry_tag_id | Nullable local link to a Registry tag (indexed, not unique) |
| birth_cohort | Registry concept: DOB year + H1 (Jan-Jun) / H2 (Jul-Dec) |
| production_stage | Registry concept; absent in Shamba; independent of status |
| Opening balance | Starting count per location/species/category/period |
| Daily log | One location+date container of events, lockable |
| Outbox / drain | Durable queued Registry intents / authenticated batch delivery |

Conventions: lowercase local enums vs UPPERCASE Registry codes; sex-specific local categories vs sex-less Registry categories (translation lives in `backend/registry_client.py`). Persisted category names come from `backend/seed_data.py`: do not rename casually. More terms: `docs/context/glossary.md`.

## 8. Commands
Never put real values for env vars into commands or docs. Names: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL`; Registry client `REGISTRY_BASE_URL`, `REGISTRY_AUDIENCE`, `REGISTRY_DEATH_STATUS`, `REGISTRY_SOLD_STATUS`; internal OIDC `INTERNAL_SYNC_AUDIENCE`, `SYNC_ALLOWED_SERVICE_ACCOUNTS`; frontend tooling `ENABLE_HEALTH_CHECK`, `ENABLE_VISUAL_EDITS`, `WDS_SOCKET_PORT`; container `PORT`.

| Purpose | Command (from) | Status |
|---|---|---|
| Backend install | `python -m pip install -r requirements.txt` (backend) | not verified (an existing `.venv` already had the packages) |
| Mocked tests | `python -m pytest backend/tests/test_registry_auth.py backend/tests/test_registry_client.py backend/tests/test_registry_report.py backend/tests/test_registry_sync.py -q` (repo root) | **verified**: 57 passed (run with dummy `DATABASE_URL`/`JWT_SECRET` so no real DB could be reached) |
| Python syntax-level lint | `python -m flake8 --select=E9,F63,F7,F82 .` (backend) | **verified**: 0 findings. Full `flake8 .` reports ~1,270 style findings, so there is no baseline |
| Test database | `docker compose -f docker-compose.test.yml up -d --wait`, later `... down -v` (repo root) | not verified: Docker daemon was not running. Loopback port 5433, no password; set `DATABASE_URL` in the shell |
| Backend run | `python -m uvicorn server:app --reload --port 8000` (backend) | not verified (a startup attempt against a dead DB port failed as expected). Runs DDL + seeding; denied for Claude in settings, the user runs it, test DB only |
| Live-HTTP tests | `backend/tests/test_disease_events.py`, `test_csv_import.py`, `test_dashboard_analytics.py`, root `backend_test.py` | not verified, do not run blindly: they call HTTP at `REACT_APP_BACKEND_URL` and `test_disease_events.py` falls back to a hardcoded remote preview host if unset |
| Frontend install | `yarn install --frozen-lockfile` (frontend) | not verified (`node_modules` exists) |
| Frontend run | `npm start` (frontend) | not verified |
| Frontend build / lint | `npm run build` (frontend; CRACO includes ESLint, no separate lint script) | **verified** 2026-11-08: compiled successfully (warnings not reviewed); overwrites the ignored `frontend/build` |
| Frontend tests | `npm test -- --watchAll=false` (frontend) | not verified; no tracked frontend test files exist |
| DB migrations | none. Schema changes are startup `create_all` + nullable `ADD COLUMN IF NOT EXISTS` in `backend/server.py` | n/a |
| Backend build/deploy | `gcloud builds submit --tag <image> .` then `gcloud run deploy shamba-backend ...` (backend), see `README_DEPLOY_GCP.md` | not verified; region in the guide is `us-central1`, target is `africa-south1`; secrets must be bound via env/secret config, not typed into docs |
| Frontend build/deploy | `gcloud builds submit --config cloudbuild.yaml .` then `gcloud run deploy srcstock ...` (frontend) | not verified. The README's `--build-arg` form is out of date; the YAML is authoritative |

## 9. Claude Code workflow
Everything below is in the repo on branch `chore/claude-setup` (not yet merged). Slash commands live in `.claude/skills/<name>/SKILL.md`.

| Command | Use it when | Side effects |
|---|---|---|
| `/plan-feature <idea>` | Starting any feature or change. Clarifies, explores, writes a plan, WAITS for approval | none until approved |
| `/fix-bug <bug or K-id>` | A defect: reproduce, failing test first, fix root cause, verify, update `docs/KNOWN_ISSUES.md` | edits code/tests/docs |
| `/db-change <desc>` | Any schema change (nullable column / new table). Plan, Docker test DB check, rollback, data checks | manual only (`disable-model-invocation`) |
| `/ship-check` | Before committing/merging: runs mocked tests, syntax lint, `npm run build`, reviews diff, checks docs. Reports PASS/FAIL | read-only + runs checks |
| `/release` | Preparing a Cloud Run release: prints the commands, user runs them | manual only; settings deny `gcloud` |
| `/update-docs` | After code changes: syncs `docs/` and `CLAUDE.md` with the diff | edits docs only |
| `/update-context` | Refreshes this file from the repo | manual only; edits this file only |
| `/next-improvement` | Takes the top open `docs/ROADMAP.md` item into `/plan-feature` | none until approved |

- Subagent: `reviewer` (`.claude/agents/reviewer.md`), read-only (Read/Grep/Glob + git diff/log/status/show); checks a diff against `CLAUDE.md`, `.claude/rules/`, `docs/DOMAIN.md`.
- Rules (`.claude/rules/`, loaded by `paths:`): `backend.md` (backend/**/*.py), `database.md` (models.py, database.py, seed_data.py), `registry-sync.md` (backend/registry_*.py, registry tests, picker + sync page), `frontend.md` (frontend/src/**).
- Hook (`.claude/settings.json` -> `.claude/hooks/protect-files.py`): PreToolUse on Edit/Write/NotebookEdit; blocks `.env*` (except `*.example`), `*.db`/`*.sqlite*`, `*.log`. Fails open on bad input. Tested with harmless cases 2026-11-08.
- Permissions: allow = the 4 mocked registry test files, syntax-level flake8, `npm run build`, `npm test -- --watchAll=false`, the test-DB compose file, read-only git. Deny = reading `.env`/`.db`/`.log`/`node_modules`/`.venv`/`build`, `gcloud`, `git push`, `git reset --hard`, `git clean`, `rm -rf`, the live-HTTP tests, and starting the backend server. If a legitimate command is blocked, ask the user.
- Gitignored local overrides: `CLAUDE.local.md`, `.claude/settings.local.json`.
- Definition of done (from `CLAUDE.md`): mocked tests pass + a test for the change; syntax lint clean; `npm run build` for frontend work; schema via `/db-change` on the test DB only; update affected docs (`docs/*`, `docs/context/*`, mirrored `integration.md` in BOTH repos); update `docs/KNOWN_ISSUES.md` / `docs/ROADMAP.md` / `docs/decisions/`; run `/update-context` when stack, commands, structure or roadmap change; finish with `/ship-check`.
- Not set up: CI, a format-on-edit hook (no formatter config exists), a migration-protection hook (no migrations exist).

## 10. Current work
Recent commits on `main` (newest first): `9b72555` Support registry tag edits and birth counts by sex; `114b280`, `4baae11` changes to tags; `9c52010` view extra details in edit logs; `56f3558` logs and vaccines; `f1f227e` animals. Direction: Registry sync (tag picker on logs, tag edits, birth counts by sex), event-edit detail, animals register, farm health/vaccines. Most-changed files: `backend/server.py`, `backend/schemas.py`, `backend/registry_sync.py`, `backend/registry_client.py`, `frontend/src/pages/NewDailyLog.jsx`, `DailyLogDetail.jsx`, `frontend/src/lib/api.js`, and the registry test modules.
In progress: the Claude Code setup on branch `chore/claude-setup` (env/DB/log files untracked and ignored, Claude config, docs). Next intended work, approved by the owner in principle: close unauthenticated read routes (ROADMAP R1) on a separate branch. No other open tasks identified (Unverified: no tracker).
Known issues: `docs/KNOWN_ISSUES.md` (K01-K19 with severity and file paths). Headline themes only: credential hygiene, access control on some reads, Shamba/Registry vocabulary and edit/delete propagation, identity ownership, concurrency, and thin tests. Credentials that were once committed must be rotated by the owner.

## 11. Roadmap
Full table: `docs/ROADMAP.md` (sizes are estimates, Unverified). Dairy is out of scope (owner decision).
1. R1 Close unauthenticated reads with explicit roles + tests — medium (owner approved).
2. R2 Fail-closed secret/bootstrap handling; owner rotates credentials — medium.
3. R3 Freeze Shamba<->Registry vocabulary with shared contract fixtures — medium.
4. R4 Verify the Docker test DB and add Postgres-backed tests — medium.
5. R5 Safe correction/deletion of synced events — large.
6. R6 Atomic stock updates + positive-count validation — medium.
7. R7 Drain scheduler, failure handling, full reconciliation — medium.
8. R8 Align deployment config (region, secrets, README) — small.
9. R9 Registry ownership of identity — large.
10. R10 Frontend tests + CI (needs approval) — medium.
11. R11 Chemical rotation and notifications — large.

## 12. Constraints
Never, or only with explicit owner approval:
- Deploy, run `gcloud`, or touch production data/credentials; run live-HTTP tests against anything unverified; send real messages.
- Print, log, commit or paste secret values or connection strings; edit tracked `.env` files.
- Start the backend purely to "look around" (it runs DDL/seeding).
- Drop/rename/retype/tighten columns, or edit enum Python classes without a PostgreSQL enum plan. Only nullable additive columns.
- Add or rely on Alembic without a separate, reviewed decision.
- Change the Registry wire contract on one side only.
- Add new writers of animal birth date/status/cohort in Shamba.
- Rename persisted category names in `backend/seed_data.py`.
- Change auth/session code (`backend/auth.py`, `frontend/src/lib/api.js`, `context/AuthContext.js`) without explicit approval and tests.
- Change Dockerfiles, `cloudbuild.yaml`, `nginx.conf`.
- Log or reuse an idempotency key for a changed payload.
Must never break: stock arithmetic and the atomic event+stock+outbox commit; role enforcement on the backend; the 57 mocked tests.

## 13. How to write prompts for this repo
Structure every prompt: goal in one sentence; area (backend/frontend/both); files to read first; constraints from section 12; required checks; "plan first, wait for approval" for anything touching stock, events, the outbox or schema.
- Start from a slash command: `/plan-feature` for features, `/fix-bug` for defects, `/db-change` for schema, `/next-improvement` to take the top roadmap item, `/ship-check` to finish, `/update-docs` then `/update-context` after docs-relevant changes. Tell Claude Code to run the command by name.
- Files to name: use `docs/context/codemap.md` rows. Common sets: stock/events -> `backend/server.py`, `backend/models.py`, `backend/schemas.py`, `frontend/src/pages/NewDailyLog.jsx`, `DailyLogDetail.jsx`; Registry sync -> `backend/registry_sync.py`, `registry_client.py`, `docs/context/integration.md`, `backend/tests/test_registry_sync.py`; health -> `backend/server.py` (health section), `frontend/src/pages/FarmHealth.jsx`; auth -> `backend/auth.py`, `frontend/src/context/AuthContext.js`.
- Checks to require: the 4-file mocked pytest command (section 8), `flake8 --select=E9,F63,F7,F82` in `backend/`, `npm run build` for frontend work, a named new/updated test, docs updated per the definition of done.
- Tell it what NOT to do: run live-HTTP tests, start the server against anything but the Docker test DB, run `gcloud`, push, or touch `.env` files.

Example prompt:
> Run /plan-feature: make the daily-log event editor reject non-positive counts. Area: backend + `frontend/src/pages/DailyLogDetail.jsx`. Read `backend/schemas.py` (EventCreate/EventUpdate), the event-update route in `backend/server.py`, `docs/context/api.md` and `docs/KNOWN_ISSUES.md` (K07). Do not change stock apply/reverse logic or the schema. Wait for my approval of the plan. After approval: implement, add a mocked pytest in `backend/tests/`, then run /ship-check and report each step as pass/fail/skipped.

## 14. Open questions / Unverified
1. Which region/environment is live (`us-central1` vs `africa-south1`), and is there staging? Owner has not answered; Unverified.
2. What triggers the outbox drain in production and how often? Unanswered (no scheduler in the repo).
3. Real deployment process and secret configuration; the `docs/DEPLOYMENT.md` release/rollback steps are standard-practice guesses.
4. Production Registry audience/allow-list and status-name overrides.
5. The Docker test DB (`docker-compose.test.yml`) and starting the backend against it: not verified because Docker was not running.
6. Whether `pip install -r backend/requirements.txt` and `yarn install --frozen-lockfile` work on a clean machine; `npm start` and `npm test` not run; build warnings not reviewed.
7. Exact enforcement of the negative-stock override, locked logs and per-route roles beyond what `docs/context/api.md` says.
8. Whether `ft-schedule`, `new-ft`, `origin/fx-changes` hold unmerged work.
9. Owner's must-never-break list beyond what the code and `memory/PRD.md` imply (guess used: stock never negative without admin override, atomic transfers/category changes, locked logs immutable, Registry owns identity).
10. Whether CI should be added; roadmap sizes and priorities are estimates.
11. Whether exposed credentials in git history have been rotated (assumed not).
