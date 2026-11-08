---
name: update-context
description: Refresh docs/PROJECT_CONTEXT.md, the standalone handoff file for other AI sessions, from the current repo state.
disable-model-invocation: true
---

# /update-context

Regenerate `docs/PROJECT_CONTEXT.md` so it matches the repo now. Edit only that file.

## Steps
1. Read the existing `docs/PROJECT_CONTEXT.md` to keep its 14-section structure, tone and "Unverified" markings.
2. Gather current facts (read-only):
   - `git rev-parse --short HEAD`, `git branch --show-current`, `git status --short`, `git log --oneline -15`, and the most-changed files since the last snapshot date.
   - `backend/requirements.txt`, `frontend/package.json`, `backend/Dockerfile`, `frontend/Dockerfile` for versions.
   - Directory listing of the repo (exclude `.venv`, `node_modules`, `build`, caches, `.git`).
   - `CLAUDE.md`, `.claude/` (settings, rules, agents, skills, hooks), `docs/` including `KNOWN_ISSUES.md` and `ROADMAP.md` if present.
   - `backend/models.py` enums and tables, route list in `backend/server.py`, and `frontend/src/App.js` routes.
3. Update each section from that evidence. Specifically:
   - Section 2: today's date, branch, commit hash, working-tree state.
   - Section 8: re-run only the SAFE verified commands (the import smoke test `python -c "import server"` with dummy `DATABASE_URL` and `JWT_SECRET`, and `flake8 --select=E9,F63,F7,F82`) and update their status. Leave anything else "not verified" unless you ran it. Never run deploy commands, the backend server, or the live-HTTP tests.
   - Section 9: list every slash command, subagent, hook, rule and the definition of done that actually exists under `.claude/` and `CLAUDE.md`; remove items that no longer exist, add new ones.
   - Sections 10-11: recent commits, in-progress work, known issues and roadmap; if `docs/KNOWN_ISSUES.md` and `docs/ROADMAP.md` exist, summarise and point to them.
   - Section 14: drop questions that are now answered, add new ones.
4. Rules:
   - Keep the file under 500 lines and self-contained (the reader has no repo access).
   - Use exact names and file paths; verify every path exists before writing it.
   - Never include secrets, keys, passwords, connection strings, real customer data or access-granting URLs. Environment variable NAMES only.
   - Do not list exact security weaknesses; point to `docs/KNOWN_ISSUES.md` (or say it does not exist yet).
   - Do not paste large code blocks; summarise and reference paths.
   - Mark anything inferred as "Unverified".
5. Report: the line count, what changed since the previous version, and every remaining "Unverified" item.
