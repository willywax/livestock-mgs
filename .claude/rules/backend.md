---
paths:
  - "backend/**/*.py"
---
# Backend rules
- Layout: `server.py` (wiring only), `routers/` (endpoints per domain), `services/` (shared helpers: stock, animal sync, transitions), `models/` (ORM per domain), `bootstrap.py` (startup DDL/seed). Read `docs/context/backend-map.md` and the owning module before editing. Direction is `routers -> services -> models`; never import one router from another (move the helper to `services/`). Register new routers in `routers/__init__.py` `ROUTERS` (static paths before dynamic siblings). Do not split or move code as a side effect of another task.
- Every route must choose auth explicitly (`require_roles(...)` or `get_current_user`). Only health, login and the three CSV template downloads are public (KNOWN_ISSUES K21); never add another unauthenticated route.
- Stock changes: apply/reverse helpers must stay symmetric, and event write + stock adjustment commit in ONE transaction. There is no row lock on `stock_levels`; do not add new read-modify-write paths without noting it in KNOWN_ISSUES.
- Never start the server or import `database.py` against a real DB to "inspect"; startup runs DDL and seeding. Use the test DB (`docker-compose.test.yml`) only.
- Checks: syntax-level flake8 and the import smoke test (`python -c "import server"` with dummy env) must pass. Run `cd backend && python -m pytest tests/test_auth.py tests/test_stock.py tests/test_events.py tests/test_reproduction.py -q` for auth/stock/event changes. Live-HTTP tests are off-limits. New tests use the SQLite in-memory fixtures in `tests/conftest.py` (set `DATABASE_URL`/`JWT_SECRET` there before importing `server`); never touch a real DB or service. SQLite cannot validate native PG enums/JSONB or row locking.
- Errors via `HTTPException(detail=...)`; keep async; no blocking I/O in request paths.
