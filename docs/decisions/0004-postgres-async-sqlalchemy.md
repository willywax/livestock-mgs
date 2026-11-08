# 0004 PostgreSQL (Neon) with async SQLAlchemy
Status: accepted; the original PRD said SQLite/aiosqlite (memory/PRD.md) but backend/database.py now uses asyncpg and README_DEPLOY_GCP.md names Neon. aiosqlite remains in requirements.txt. Native PG enums/JSONB mean SQLite cannot validate the schema. Switch date Unverified.
