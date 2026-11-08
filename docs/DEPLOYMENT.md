# Deployment
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
