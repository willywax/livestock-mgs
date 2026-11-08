# 0005 Additive-only schema changes without Alembic
Status: accepted policy (CLAUDE.md). Startup runs create_all plus explicit nullable ADD COLUMN IF NOT EXISTS in backend/server.py. No migration chain despite alembic being installed. Only nullable additions and reviewed new tables; never drop/rename/retype. Revisit if a migration framework is approved.
