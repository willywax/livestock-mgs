---
name: db-change
description: Safe process for any ShambaManager schema change (new nullable column or table): plan, test on the Docker test DB, rollback and data checks. Manual only.
disable-model-invocation: true
---
# /db-change <description>
Policy: only nullable `ADD COLUMN IF NOT EXISTS` and reviewed new tables. No drop, rename, retype, NOT NULL, unique or enum-member changes. There is no Alembic chain and `create_all` does not alter existing tables.
1. Read `docs/DATA_MODEL.md`, the table in `docs/context/data-model.md`, `.claude/rules/database.md`, and the startup DDL in `backend/server.py` (search `ADD COLUMN IF NOT EXISTS`).
2. Write a plan and WAIT for approval: exact DDL, model + schema + route changes, old-reader compatibility, backfill (a separate step), rollback (dropping a new nullable column is the only safe rollback; say if data would be lost), and data checks (row counts, NULL ratios).
3. After approval, implement in `backend/models.py`, `backend/schemas.py` and the startup DDL list.
4. Verify ONLY on the throwaway DB: `docker compose -f docker-compose.test.yml up -d --wait`, set `DATABASE_URL` in the shell to the test DB (loopback port 5433, never in a file), start and seed against it, confirm the column exists and old rows still read, then `down -v`. If Docker is not running, report "not verified" and stop. Never run against production or any database you cannot identify.
5. Run the import smoke test and syntax lint. Update `docs/DATA_MODEL.md` and `docs/context/data-model.md`; add a `docs/decisions/` record if the change is lasting.
6. Give the user the deploy order: backend boot applies the DDL, so deploy the backend before the frontend.
