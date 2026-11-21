# Architecture
Short map. Full detail (inventory, request flow, UI routes, risks): [context/architecture.md](context/architecture.md). Task-to-file lookup: [context/codemap.md](context/codemap.md).

## Modules
- `backend/server.py` entry point (`app`): wiring only. `backend/routers/` (endpoints per domain, order in `routers/__init__.py`), `backend/services/` (stock apply/reverse/recompute, animal-register sync, transitions), `backend/bootstrap.py` (startup DDL/seed). Full map: [context/backend-map.md](context/backend-map.md); decision 0012.
- `backend/reports_router.py`: `reports_router` (prefix `/api/reports`), included in `server.py` after `api_router`. Read-only reproduction reports `/calving`, `/reproductive-status`, `/abortions` (SQLAlchemy Core, portable to SQLite). It must never reuse a path already in `api_router` (`/reports/daily|range|analytics|detailed|sales|mortality`). Pydantic response models live in that file, not `schemas.py`.
- `backend/models/` (package, by domain), `schemas/`, `database.py`, `auth.py`: ORM + enums, Pydantic contracts, async engine/session, JWT + `require_roles`.
- `frontend/src/App.js` (routes), `pages/`, `components/`, `context/AuthContext.js`, `lib/api.js`.

## Flows
1. UI -> `lib/api.js` (adds JWT) -> `/api/*` in `backend/routers/*` -> `AsyncSession` -> PostgreSQL.
2. Daily log create: validate stock, insert events, adjust `stock_levels`, ONE commit.
3. Event edit: reverse old stock effect then apply new. Delete: reverse stock, remove event.
4. Farm health: intervals + events produce next-due dates; vaccine types may override.

## Integrations
None. The Herd Tag Registry integration was removed 2026-11-08 ([decision 0007](decisions/0007-remove-registry-integration.md), [context/integration.md](context/integration.md)).

## Auth and roles
JWT HS256 24h from `/api/auth/login` (phone + password). Roles `admin`, `data_entry`, `viewer`. Backend `require_roles` is authoritative; frontend guards are UI. Per-route auth: [context/api.md](context/api.md). Unauthenticated reads: KNOWN_ISSUES K02.

## Deployment shape
Two Cloud Run services (API container, Nginx static frontend), PostgreSQL on Neon. See [DEPLOYMENT.md](DEPLOYMENT.md).

## Status board and navigation (2026-11-10)
`/reproduction/status` loads the read-only status-board API with farm/species filters. `SidebarNavigation.jsx` owns the collapsible groups, role filtering, longest-path active matching, and localStorage key `shamba.sidebar.groups.v1`. Layout keeps the navigation scrollable above the user footer. Legacy URLs remain valid; `/repeat-breeders`, `/mortality`, `/users` redirect to their existing pages. Locations and Farm Health remain standalone links.

`ReproductiveEventDialog.jsx` is the existing standalone event form extracted from AnimalDetail. Both pages reuse it; the board presets service/calving and refreshes after successful saves. These actions create standalone reproductive events, not reproductive cycles. Pending board responses are ignored after filters change or the component unmounts. No server starts or live-HTTP test runs are needed for these checks.
