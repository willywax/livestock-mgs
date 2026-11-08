# Architecture
Short map. Full detail (inventory, request flow, UI routes, risks): [context/architecture.md](context/architecture.md). Task-to-file lookup: [context/codemap.md](context/codemap.md).

## Modules
- `backend/server.py` entry point (`app`), all `/api` routes, startup DDL/seed, stock apply/reverse/recompute, farm-health due-date logic.
- `backend/models.py`, `schemas.py`, `database.py`, `auth.py`: ORM + enums, Pydantic contracts, async engine/session, JWT + `require_roles`.
- `frontend/src/App.js` (routes), `pages/`, `components/`, `context/AuthContext.js`, `lib/api.js`.

## Flows
1. UI -> `lib/api.js` (adds JWT) -> `/api/*` in server.py -> `AsyncSession` -> PostgreSQL.
2. Daily log create: validate stock, insert events, adjust `stock_levels`, ONE commit.
3. Event edit: reverse old stock effect then apply new. Delete: reverse stock, remove event.
4. Farm health: intervals + events produce next-due dates; vaccine types may override.

## Integrations
None. The Herd Tag Registry integration was removed 2026-11-08 ([decision 0007](decisions/0007-remove-registry-integration.md), [context/integration.md](context/integration.md)).

## Auth and roles
JWT HS256 24h from `/api/auth/login` (phone + password). Roles `admin`, `data_entry`, `viewer`. Backend `require_roles` is authoritative; frontend guards are UI. Per-route auth: [context/api.md](context/api.md). Unauthenticated reads: KNOWN_ISSUES K02.

## Deployment shape
Two Cloud Run services (API container, Nginx static frontend), PostgreSQL on Neon. See [DEPLOYMENT.md](DEPLOYMENT.md).
