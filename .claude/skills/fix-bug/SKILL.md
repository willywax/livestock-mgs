---
name: fix-bug
description: Fix a bug in ShambaManager: reproduce, write a failing test, fix the root cause, verify, and update docs/KNOWN_ISSUES.md.
---
# /fix-bug <bug description or KNOWN_ISSUES id>
1. Reproduce read-only first: find the code path (`docs/context/codemap.md`, grep) and check `docs/KNOWN_ISSUES.md` for an existing entry. Never reproduce against production or with the live-HTTP tests; use mocked tests or the Docker test DB (`docker-compose.test.yml`).
2. Write a failing test if a mocked test is feasible (`backend/tests/` has no runnable suite now; mock the DB session and run it with the repo `.venv`, dummy `DATABASE_URL`/`JWT_SECRET` in the shell). If not feasible, write exact reproduction steps and say so. Frontend-only bug: write manual reproduction steps.
3. Fix the root cause with the smallest change. Respect `.claude/rules/` and the "Never" list. Do not fix adjacent issues; log them.
4. Verify: new test passes (if any), `python -m flake8 --select=E9,F63,F7,F82 .` and `python -c "import server"` in `backend/` (dummy env), and `npm run build` in `frontend/` if it changed.
5. Update `docs/KNOWN_ISSUES.md` (move to Resolved with the commit, or add new findings) and any affected doc or decision record.
6. Report what failed before, what passes now, and what you could not verify.
