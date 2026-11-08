---
paths:
  - "backend/**/*.py"
---
# Backend rules
- Routes, stock logic and health logic all live in `backend/server.py`; read the surrounding code and `docs/context/codemap.md` before editing. Do not split or refactor it as a side effect.
- Every route must choose auth explicitly (`require_roles(...)` or `get_current_user`). Only health, login and the three CSV template downloads are public (KNOWN_ISSUES K21); never add another unauthenticated route.
- Stock changes: apply/reverse helpers must stay symmetric, and event write + stock adjustment commit in ONE transaction. There is no row lock on `stock_levels`; do not add new read-modify-write paths without noting it in KNOWN_ISSUES.
- Never start the server or import `database.py` against a real DB to "inspect"; startup runs DDL and seeding. Use the test DB (`docker-compose.test.yml`) only.
- Checks: syntax-level flake8 and the import smoke test (`python -c "import server"` with dummy env) must pass. There are no automated backend tests; live-HTTP tests are off-limits. Any new test must mock the DB session; never call a real service.
- Errors via `HTTPException(detail=...)`; keep async; no blocking I/O in request paths.
