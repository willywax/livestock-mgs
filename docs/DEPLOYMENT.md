# Deployment
## Verified release: 2026-11-10
- Application commit `4506bf7` deployed from a clean Git archive to `elitagroup`, `us-central1`: reproductive status board, grouped sidebar, category transitions, and animal/form improvements.
- Backend `shamba-backend-4506bf7` and frontend `srcstock-4506bf7` each serve 100% of traffic. Existing runtime environment and identity retained. Images use tag `4506bf7`.
- Successful Cloud Builds: backend `551b1e3c-032a-4662-b8fb-64ce965c664b`, frontend `57989e29-1dc4-4b73-ad74-42a51c28966e`.
- Production migration ran before service deployment via job execution `shamba-migrate-4506bf7-2bptq`, using the backend runtime identity and environment. Startup creates the two category-transition tables and enum, then seeds rules. Repeated startup passed: all 28 ORM tables readable, 15 transition rules, and unchanged row counts in animals, events, stock_levels, reproductive_events and categories. No historical transition backfill was run.
- Local checks: 202 self-contained backend tests, 21 frontend tests, syntax lint, import/startup checks and production build passed (existing hook warnings only). PostgreSQL 16 upgrade from `816dac4` and repeated startup verified on an isolated local container, now stopped.
- Live checks: `/reproduction/status` and its JavaScript asset returned HTTP 200. Bundle includes the board and transition queue. OpenAPI exposes status-board, transition queue and transition-rule endpoints; unauthenticated board access returns HTTP 403. Interactive login and authenticated browser workflows were not tested.
- Rollback traffic targets: `shamba-backend-816dac4` and `srcstock-816dac4`. Use `gcloud run services update-traffic <service> --project elitagroup --region us-central1 --to-revisions <previous-revision>=100`. Leave the additive schema in place. Traffic rollback does not reverse category/stock transitions recorded after release.

## Verified release: 2026-11-09
- Deployed application commit `816dac4` from a clean Git archive to existing project `elitagroup`, region `us-central1`.
- Backend revision: `shamba-backend-816dac4`; frontend revision: `srcstock-816dac4`. Explicitly routed 100% of traffic to each new revision because the services retained traffic pins to `ff6314c` after deploy.
- Images: `gcr.io/elitagroup/shamba-backend:816dac4` and `gcr.io/elitagroup/srcstock:816dac4`. Existing runtime environment and secret configuration retained.
- Successful Cloud Builds: backend `a6d7688a-22e2-4c3d-a98e-39e1172cdad7`; frontend `5e0b1777-7927-4189-9382-16867f4c656d`.
- Validation: 180 self-contained backend tests, 5 frontend regression tests, import smoke test, syntax lint and production builds passed. Local PostgreSQL 16 upgrade from `ff6314c` succeeded; repeated startup succeeded and all 26 ORM tables were readable. The separate temporary PostgreSQL container was stopped afterward.
- Live checks: frontend and main JavaScript asset returned HTTP 200; API root returned its expected response. OpenAPI includes mortality, death-cause and reconciliation routes; unauthenticated mortality access returns HTTP 403. Interactive login and authenticated user workflows were not tested. External-server test suites were not part of release validation.
- Rollback traffic targets: `shamba-backend-ff6314c` and `srcstock-ff6314c`. Use `gcloud run services update-traffic <service> --project elitagroup --region us-central1 --to-revisions <previous-revision>=100`. Leave additive schema changes in place; no production data rollback was attempted.

## Verified release: 2026-11-08
- Deployed commit `57199a2` from a clean Git archive to project `elitagroup`, updating the existing services in `us-central1`.
- Backend: `shamba-backend-00022-lrx`; frontend: `srcstock-00013-srg`; both serve 100% of traffic. Previous revisions: `shamba-backend-00021-gtc` and `srcstock-00012-c58`.
- Cloud Build IDs: backend `9f01b53b-399f-45f5-bcff-98285980b415`, frontend `e34cdef0-f525-4a0b-8b09-85a579523639`; both succeeded.
- Applied the existing startup schema changes to the production database using Cloud Run job execution `shamba-release-57199a2-q87ds` before deploying. All ORM tables and columns were inspected and queried successfully. No separate Alembic migration chain exists.
- Configured private bucket `gs://elitagroup-shamba-photos` with uniform bucket access and public access prevention. Backend `GCS_BUCKET_NAME` points to it.
- Runtime service account `883901859223-compute@developer.gserviceaccount.com` has `roles/storage.objectUser` on this bucket and `roles/iam.serviceAccountTokenCreator` on itself for IAM signing. Enabled IAM Credentials and Cloud Resource Manager APIs.
- The job verified actual upload, signed-URL download and deletion using the runtime identity; its temporary object was removed.
- Validation: 101 SQLite backend tests passed, syntax lint passed, both production image builds passed, and the API and frontend custom domains returned HTTP 200. Interactive login/browser workflows and concurrent reproduction writes were not tested.
- The frontend JavaScript asset downloaded successfully (HTTP 200, 1,426,742 bytes). The local connection was slow; a separate curl request with a 30-second limit timed out partway through.

The older source-only notes below predate this verified release.

Source: README_DEPLOY_GCP.md, backend/Dockerfile, frontend/Dockerfile, frontend/cloudbuild.yaml, frontend/nginx.conf. Live state is Unverified: nothing was inspected or run. There is no CI/CD; every release is manual.

## Environments
- One production environment is documented (Unverified: no staging). Two Cloud Run services: `shamba-backend` (FastAPI, container port from `PORT`, default 8080) and `srcstock` (Nginx serving the React build). Database: PostgreSQL on Neon.
- Checked-in region is `us-central1`; the owner's target is `africa-south1`. Confirm before any deploy (KNOWN_ISSUES K11).
- Local/test: backend on port 8000, throwaway DB via `docker-compose.test.yml` (port 5433, loopback, not verified).

## Environment variable NAMES (never values)
- Backend: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, `PORT`.
- Obsolete (inert, safe to remove from Cloud Run): `REGISTRY_BASE_URL`, `REGISTRY_AUDIENCE`, `REGISTRY_DEATH_STATUS`, `REGISTRY_SOLD_STATUS`, `INTERNAL_SYNC_AUDIENCE`, `SYNC_ALLOWED_SERVICE_ACCOUNTS`. Delete any Cloud Scheduler job that called `/api/internal/sync/drain` (route no longer exists).
- Frontend (build-time): `REACT_APP_BACKEND_URL`; dev tooling `ENABLE_HEALTH_CHECK`, `ENABLE_VISUAL_EDITS`, `WDS_SOCKET_PORT`.
- Backend loads `backend/.env` locally (not committed). Prefer Cloud Run secret bindings in deployed environments (Unverified how prod is configured).

## Release steps (manual; run only via `/release`, when asked)
1. On a clean branch: import smoke test, syntax lint and `npm run build` all pass (`/ship-check`). No automated backend tests exist.
2. Backend (from `backend/`): `gcloud builds submit --tag <image> .` then `gcloud run deploy shamba-backend --image <image> --platform managed --region <confirmed region>`; bind env/secrets by name.
3. Frontend (from `frontend/`): `gcloud builds submit --config cloudbuild.yaml .` then `gcloud run deploy srcstock --image <image> ...`. `REACT_APP_BACKEND_URL` is a build arg in cloudbuild.yaml.
4. Schema changes: backend startup applies DDL on boot, so deploy only after `/db-change` review.
5. Smoke test login and one read after deploy.

## Rollback (Unverified, standard Cloud Run behaviour)
Shift traffic to the previous revision (`gcloud run services update-traffic <service> --to-revisions <prev>=100`). Nullable-column additions need no rollback; stock/event data changes need a recompute plan.

## Known doc drift
README_DEPLOY_GCP.md frontend `--build-arg` command is wrong for `gcloud builds submit`; use cloudbuild.yaml. README places secrets in `--set-env-vars`; do not copy that into shell history or docs.

## Last local verification (2026-11-08)
Import smoke test: passes. flake8 syntax-level: 0 findings. (The 57 mocked registry tests were deleted with the integration.) `npm run build`: compiled successfully after the removal (only pre-existing react-hooks warnings in untouched files). `docker-compose.test.yml`: NOT verified, Docker daemon was not running. Backend start against the test DB: not verified.
