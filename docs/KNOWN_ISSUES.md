# Known issues
Source: read-only analysis of main 9b72555 (2026-10-08) plus spot checks on 2026-11-08. "Unverified" = not reproduced by running code. Fix by plan (`/plan-feature`, `/fix-bug`); do not fix opportunistically. Close an item by moving it to "Resolved" with the commit.

| ID | Sev | Area | Issue | Files | Status |
|---|---|---|---|---|---|
| K01 | Critical | Secrets | JWT secret has a literal code fallback; a fixed default admin is seeded when no users exist. `.env` files, local DB and logs WERE tracked in git (untracked on branch `chore/claude-setup`, but history still holds them). Owner must rotate the DB credential and JWT secret and change the default admin. | backend/auth.py:14, backend/seed_data.py:62, backend/server.py:139 | Open (history not rewritten) |
| K02 | High | Auth | 14 of 68 routes have no auth dependency; 13 are GET reads (locations, daily logs + detail, dashboard, all reports, templates) plus login. Owner decision: close them (roadmap R1). Confirmed by script on 2026-11-08; role of each route: docs/context/api.md | backend/server.py:166-2992 (e.g. :773, :829, :1540, :1882, :1935, :1990, :2508) | Open |
| K03 | High | Contract | Shamba sends `CALVED`, Registry only acts on `BIRTH`; Shamba defaults death status `DECEASED`, Registry terminal is `DEAD`. Mocked test expects CALVED. | backend/registry_sync.py:26, :212; backend/tests/test_registry_sync.py:318; ../tags-src integration router | Open |
| K04 | High | Edits | Editing a synced event overwrites the outbox row and reuses the permanent idempotency key; Registry replays the old outcome. | backend/registry_sync.py:243 | Open |
| K05 | High | Deletion | Deleting an event reverses stock only; queued/sent Registry actions are not cancelled or reverted. | backend/server.py:1446-1481, backend/registry_sync.py:57 | Open |
| K06 | High | Identity | Local Animal DOB/status written independently of Registry; `registry_tag_id` is non-unique and assigned before Registry validation. | backend/models.py:212, :231; backend/server.py:3295, :3373 | Open |
| K07 | High | Concurrency | Stock read-modify-write without lock/atomic increment; event counts not validated positive. | backend/server.py:2789-2801; backend/schemas.py:109 | Open (Unverified under load) |
| K08 | Medium | Reconciliation | Report reads only the first Registry page and compares by tag, not event. | backend/registry_report.py:69, :85 | Open |
| K09 | Medium | Failure handling | Token/config errors and 400/422 can escape retry handling after local commit; blocking Google auth call inside async code. | backend/registry_client.py:147-181; backend/registry_auth.py:55 | Open |
| K10 | Medium | Ops | No scheduler for the outbox drain is defined anywhere in the repo. | backend/server.py (`/api/internal/sync/drain`) | Open (Unverified in prod) |
| K11 | Medium | Deploy | Checked-in region is us-central1, target is africa-south1; README frontend command out of date (use cloudbuild.yaml); secrets are passed via `--set-env-vars` in the README. | README_DEPLOY_GCP.md, frontend/cloudbuild.yaml | Open |
| K12 | Medium | Multi-tag | Death/sale outbox uses only the first tag of a comma-separated list. | backend/registry_sync.py:169, :185, :202 | Open |
| K13 | Medium | Categories | Registry alias drops sex; `Dume Mbegu` vs `MBEGU` not mapped. | backend/registry_client.py:36 | Open |
| K14 | Medium | Performance | Per-row queries in health-category resolution and bulk import. | backend/server.py:3735, :3785, :3200 | Open |
| K15 | Medium | Tests | No frontend tests; no Postgres/concurrency/contract tests; 3 test modules + backend_test.py are live-HTTP (one with a hardcoded remote fallback). | backend/tests/test_disease_events.py:12 | Open |
| K16 | Low | Deps | requirements.txt lists many packages with no observed import; full flake8 ~1,270 style findings. | backend/requirements.txt | Open |
| K17 | Low | Dead code / clutter | Unused helpers; stale root files (`commands.txt`, `test_result.md`, `backend_test_results.json`, `backend/sampe.txt`); placeholder README; stale `MONGO_URL` name in local env file (Unverified use). | backend/auth.py:62, backend/server.py:17, :56 | Open |
| K18 | Low | Docs | `memory/PRD.md` describes SQLite and says notifications not needed; code uses PostgreSQL. | memory/PRD.md | Open |
| K19 | Low | Roles docs | Route comments can lag actual roles (add-event ADMIN, update-event ADMIN/DATA_ENTRY, lock ADMIN/VIEWER). | backend/server.py | Open |

## Not run / not reproduced
Concurrency (K07), Registry mismatches against a live Registry (K03-K05), and deployment state were assessed from source only.

## Resolved
- 2026-11-08: `.env`, `shamba.db`, `*.log` untracked and ignored (commit on `chore/claude-setup`); credential rotation still required (K01).
