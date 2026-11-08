# Known issues
Source: read-only analysis of main 9b72555 (2026-10-08) plus spot checks on 2026-11-08. "Unverified" = not reproduced by running code. Fix by plan (`/plan-feature`, `/fix-bug`); do not fix opportunistically. Close an item by moving it to "Resolved" with the commit.

| ID | Sev | Area | Issue | Files | Status |
|---|---|---|---|---|---|
| K01 | Critical | Secrets | JWT secret has a literal code fallback; a fixed default admin is seeded when no users exist. `.env` files, local DB and logs WERE tracked in git (untracked on branch `chore/claude-setup`, but history still holds them). Owner must rotate the DB credential and JWT secret and change the default admin. | backend/auth.py:14, backend/seed_data.py:62, backend/server.py:139 | Open (history not rewritten) |
| K02 | High | Auth | 14 of 68 routes have no auth dependency; 13 are GET reads (locations, daily logs + detail, dashboard, all reports, templates) plus login. Owner decision: close them (roadmap R1). Confirmed by script on 2026-11-08; role of each route: docs/context/api.md | backend/server.py:166-2992 (e.g. :773, :829, :1540, :1882, :1935, :1990, :2508) | Open |
| K07 | High | Concurrency | Stock read-modify-write without lock/atomic increment; event counts not validated positive. | backend/server.py:2789-2801; backend/schemas.py:109 | Open (Unverified under load) |
| K11 | Medium | Deploy | Checked-in region is us-central1, target is africa-south1; README frontend command out of date (use cloudbuild.yaml); secrets are passed via `--set-env-vars` in the README. | README_DEPLOY_GCP.md, frontend/cloudbuild.yaml | Open |
| K14 | Medium | Performance | Per-row queries in health-category resolution and bulk import. | backend/server.py:3735, :3785, :3200 | Open |
| K15 | Medium | Tests | No automated backend tests remain (the 57 mocked registry tests were deleted with the integration); the other modules and root harness are live-HTTP (one with a hardcoded remote fallback). No frontend tests. No Postgres/concurrency tests. | backend/tests/test_disease_events.py:12 | Open (ROADMAP R4) |
| K16 | Low | Deps | requirements.txt lists many packages with no observed import; full flake8 ~1,270 style findings. | backend/requirements.txt | Open |
| K17 | Low | Dead code / clutter | Unused helpers; stale root files (`commands.txt`, `test_result.md`, `backend_test_results.json`, `backend/sampe.txt`); placeholder README; stale `MONGO_URL` name in local env file (Unverified use). | backend/auth.py:62, backend/server.py:17, :56 | Open |
| K18 | Low | Docs | `memory/PRD.md` describes SQLite and says notifications not needed; code uses PostgreSQL. | memory/PRD.md | Open |
| K20 | Low | Legacy data | Table `registry_sync_outbox`, its PostgreSQL enum types and `animals.registry_tag_id` remain as inert legacy data (deliberately not dropped). Pending outbox rows will never be delivered; the Registry is not told about deaths/sales/births after 2026-11-08. Env vars `REGISTRY_*`, `INTERNAL_SYNC_*` and any Cloud Scheduler drain job should be removed by the owner. | backend/models.py (Animal.registry_tag_id) | Open (owner action) |
| K19 | Low | Roles docs | Route comments can lag actual roles (add-event ADMIN, update-event ADMIN/DATA_ENTRY, lock ADMIN/VIEWER). | backend/server.py | Open |

## Not run / not reproduced
Concurrency (K07) and deployment state were assessed from source only.

## Resolved
- K03 (Shamba sends `CALVED`, Registry only acts on `BIRTH`; Shamba defaults death status `DECEASED`, Registry terminal is `DEAD`): removed with the Registry integration, commit on `chore/remove-registry`.
- K04 (Editing a synced event overwrites the outbox row and reuses the permanent idempotency key; Registry replays the old outcome): removed with the Registry integration, commit on `chore/remove-registry`.
- K05 (Deleting an event reverses stock only; queued/sent Registry actions are not cancelled or reverted): removed with the Registry integration, commit on `chore/remove-registry`.
- K06 (Local Animal DOB/status written independently of Registry; `registry_tag_id` is non-unique and assigned before Registry validation): removed with the Registry integration, commit on `chore/remove-registry`.
- K08 (Report reads only the first Registry page and compares by tag, not event): removed with the Registry integration, commit on `chore/remove-registry`.
- K09 (Token/config errors and 400/422 can escape retry handling after local commit; blocking Google auth call inside async code): removed with the Registry integration, commit on `chore/remove-registry`.
- K10 (No scheduler for the outbox drain is defined anywhere in the repo): removed with the Registry integration, commit on `chore/remove-registry`.
- K12 (Death/sale outbox uses only the first tag of a comma-separated list): removed with the Registry integration, commit on `chore/remove-registry`.
- K13 (Registry alias drops sex; `Dume Mbegu` vs `MBEGU` not mapped): removed with the Registry integration, commit on `chore/remove-registry`.
- 2026-11-08: `.env`, `shamba.db`, `*.log` untracked and ignored (commit on `chore/claude-setup`); credential rotation still required (K01).
