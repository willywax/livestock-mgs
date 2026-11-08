# ShambaManager
Livestock stock + farm-operations app for a Tanzanian ranch (cattle/sheep/goats): daily-log events, aggregate stock counts, individual animal register, farm-health scheduling, reports. Repo folder is `livestock-mgs`. FastAPI/async SQLAlchemy/PostgreSQL backend, React 19 (CRA/CRACO, JSX) frontend, Cloud Run.
The sibling Herd Tag Registry (`../tags-src`) owns tag identity, DOB, birth_cohort, production_stage and tag status. Shamba references them and owns operational history. `production_stage` and `status` are independent. Local Animal DOB/status are legacy competing writes: do not extend that pattern.
Snapshot facts come from source; deployment state is Unverified. Standalone summary for other AI sessions: [PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md).

## Commands
Configure `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL` via the shell/environment. Never paste values into files, docs or chat.
| Purpose | Command (from) | Status |
|---|---|---|
| Mocked tests | `python -m pytest backend/tests/test_registry_auth.py backend/tests/test_registry_client.py backend/tests/test_registry_report.py backend/tests/test_registry_sync.py -q` (repo root) | works (57 passed). Use the repo `.venv`; set a dummy `DATABASE_URL` first so `.env` is never used |
| Syntax lint | `python -m flake8 --select=E9,F63,F7,F82 .` (backend) | works (0 findings). Full flake8 has ~1,270 style findings: no baseline, do not "fix" them |
| Test DB | `docker compose -f docker-compose.test.yml up -d --wait` then `down -v` | not verified (Docker daemon was off). Port 5433, loopback only, no password |
| Backend run | `python -m uvicorn server:app --reload --port 8000` (backend) | denied for Claude in settings; the user runs it. Needs a reachable DB and runs DDL + seeding: use the test DB only |
| Backend install | `python -m pip install -r requirements.txt` (backend) | not verified |
| Frontend install/run | `yarn install --frozen-lockfile`; `npm start` (frontend) | not verified |
| Frontend build (+ESLint) | `npm run build` (frontend) | works (2026-11-08, compiled; warnings not reviewed). Overwrites ignored `frontend/build/` |
| Frontend tests | `npm test -- --watchAll=false` (frontend) | no test files exist |
| Migrations | none. See Schema safety | n/a |
| Deploy | `gcloud ...` in README_DEPLOY_GCP.md, frontend/cloudbuild.yaml | not verified; only via `/release`, only when asked |
Live-HTTP tests (`backend/tests/test_disease_events.py`, `test_csv_import.py`, `test_dashboard_analytics.py`, root `backend_test.py`) call a URL from `REACT_APP_BACKEND_URL` (one falls back to a remote host). Never run them unless that URL is the local test backend.

## Slash commands (`.claude/skills/`)
`/plan-feature` (clarify, explore, plan, wait) · `/fix-bug` (reproduce, failing test, fix, verify) · `/db-change` (schema changes) · `/ship-check` (all checks + diff review, pass/fail) · `/update-docs` · `/update-context` (refresh docs/PROJECT_CONTEXT.md) · `/next-improvement` (top ROADMAP item -> plan) · `/release` (manual only). Reviewer subagent: `.claude/agents/reviewer.md`. Path-scoped rules: `.claude/rules/`.

## Conventions that differ from defaults
- All routes and most business logic live in `backend/server.py` (~4,170 lines, no service layer). Add to it carefully; do not refactor opportunistically.
- Python snake_case, PascalCase Pydantic/ORM; str enums; `async def` routes, `AsyncSession`, `await` execute/flush/commit, `selectinload` what responses need; `expire_on_commit=False`.
- Errors via `HTTPException(detail=...)`; writes guarded by `require_roles` (backend/auth.py). Backend auth is the real gate, frontend route guards are UI only.
- Event + stock + outbox commit locally BEFORE remote delivery. Never reuse an idempotency key for a corrected payload.
- Lowercase local enums vs UPPERCASE Registry codes; sex-specific local categories vs sex-less Registry categories (backend/registry_client.py).
- Frontend: JSX function components, PascalCase pages, local state, AuthContext, `lib/api.js` wrappers, Sonner toasts.

## Never
- Print, log, commit or write secrets, tokens or connection strings; read `.env` files (denied in settings). Credentials in git history must be rotated by the owner.
- Start the backend or run tests against production or any unverified database. Run `gcloud`, deploy, or push without being asked.
- Change schema other than nullable `ADD COLUMN IF NOT EXISTS`. Never drop, rename, retype or tighten columns, or edit enum members without a PostgreSQL plan (`/db-change`). `create_all` does not migrate existing tables.
- Change the Registry contract on one side only; consult docs/context/integration.md.
- Rename persisted category names (backend/seed_data.py).
- Touch auth/session code, Dockerfiles, cloudbuild.yaml or nginx.conf without explicit approval.
- Fix a bug you were not asked to fix: log it in docs/KNOWN_ISSUES.md instead.

## Do not touch casually
backend/server.py (startup DDL/seed, event reversal, stock projection, commit ordering) · backend/models.py, database.py · backend/registry_sync.py, registry_client.py, registry_auth.py · backend/seed_data.py · frontend/src/lib/api.js, context/AuthContext.js.

## Definition of done
1. Mocked test command passes; add/adjust a test for the changed behaviour (bug fixes: failing test first).
2. `flake8 --select=E9,F63,F7,F82` clean on backend changes; `npm run build` passes for frontend changes.
3. Schema changes follow the additive policy via `/db-change`; anything needing a live DB uses the test DB only.
4. Update the docs that your change touches: docs/DATA_MODEL.md, docs/DOMAIN.md, docs/ARCHITECTURE.md, docs/context/*, mirrored integration.md in BOTH repos if the Registry contract changes.
5. Add/close entries in docs/KNOWN_ISSUES.md and docs/ROADMAP.md; add a docs/decisions/ record for a lasting decision.
6. Run `/update-context` when the stack, commands, structure or roadmap changed. Keeping this setup current is part of the task.
7. Run `/ship-check` and report pass/fail honestly, including anything skipped.

## Docs (read on demand)
- [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATA_MODEL](docs/DATA_MODEL.md) · [DEPLOYMENT](docs/DEPLOYMENT.md) · [DOMAIN](docs/DOMAIN.md) · [KNOWN_ISSUES](docs/KNOWN_ISSUES.md) · [ROADMAP](docs/ROADMAP.md) · [decisions/](docs/decisions/)
- Detailed references: [architecture](docs/context/architecture.md), [data-model](docs/context/data-model.md) (every column), [api](docs/context/api.md) (every route + actual auth), [integration](docs/context/integration.md), [codemap](docs/context/codemap.md) (task -> files), [glossary](docs/context/glossary.md).
- `memory/PRD.md` is historical (it says SQLite/phone login in places); trust code over it. `../ANALYSIS_REPORT.md` (outside the repo) holds the original findings table.
