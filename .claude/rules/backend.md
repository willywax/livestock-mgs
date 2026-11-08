---
paths:
  - "backend/**/*.py"
---
# Backend rules
- Routes, stock logic and health logic all live in `backend/server.py`; read the surrounding code and `docs/context/codemap.md` before editing. Do not split or refactor it as a side effect.
- Every route must choose auth explicitly (`require_roles(...)` or `get_current_user`). Several business GETs are currently unauthenticated (see docs/KNOWN_ISSUES.md); never add a new unauthenticated route.
- Stock changes: apply/reverse helpers must stay symmetric, and event write + stock adjustment + outbox row commit in ONE transaction. There is no row lock on `stock_levels`; do not add new read-modify-write paths without noting it in KNOWN_ISSUES.
- Never start the server or import `database.py` against a real DB to "inspect"; startup runs DDL and seeding. Use the test DB (`docker-compose.test.yml`) only.
- Tests: mocked registry tests must pass (command in CLAUDE.md). Live-HTTP tests are off-limits. New tests should mock sessions/httpx like `backend/tests/test_registry_sync.py`.
- Errors via `HTTPException(detail=...)`; keep async; no blocking I/O in request paths.
