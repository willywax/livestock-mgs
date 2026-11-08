---
name: ship-check
description: Run all ShambaManager checks, review the diff against project rules, confirm docs are current, and report PASS or FAIL.
---
# /ship-check
Read-only apart from running checks. Report each step PASS / FAIL / SKIPPED with reasons; any FAIL means overall FAIL.
1. `git status` and `git diff main...HEAD --stat`; list the changed files.
2. Mocked tests from the repo root, with dummy `DATABASE_URL` and `JWT_SECRET` set in the shell so `.env` is not used: the 4-file pytest command in CLAUDE.md.
3. `python -m flake8 --select=E9,F63,F7,F82 .` in `backend/`.
4. If `frontend/` changed: `npm run build` in `frontend/`.
5. Review the diff with the `reviewer` subagent (`.claude/agents/reviewer.md`) or apply its checklist: stock/outbox atomicity, Registry contract, additive schema, explicit auth on new routes, no secrets or `.env`/DB/log files in the diff.
6. Docs current? Changed behaviour must be reflected in `docs/` (DATA_MODEL, DOMAIN, ARCHITECTURE, context/*), KNOWN_ISSUES and ROADMAP updated, and `docs/PROJECT_CONTEXT.md` refreshed with `/update-context` if stack, commands, structure or roadmap changed.
7. Output: a table of steps with PASS/FAIL/SKIPPED, blocking issues, non-blocking issues, and what could not be verified.
