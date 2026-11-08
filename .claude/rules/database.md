---
paths:
  - "backend/models.py"
  - "backend/database.py"
  - "backend/seed_data.py"
---
# Database / schema rules
- Allowed: new tables (reviewed plan) and nullable `ADD COLUMN IF NOT EXISTS`. Forbidden in routine work: drop, rename, retype, add NOT NULL/unique/constraints to existing columns, change enum members.
- `Base.metadata.create_all` creates only missing tables. Existing columns, PostgreSQL enum types, indexes and constraints are NOT changed by editing models.py. There is no Alembic chain.
- Existing explicit DDL lives in the startup code of `backend/server.py` (look for `ADD COLUMN IF NOT EXISTS`); follow that pattern only after running `/db-change`.
- Native PostgreSQL enums and JSONB: SQLite cannot validate them. Verify on the Docker test DB, never on a shared or production DB.
- `animals.registry_tag_id` and table `registry_sync_outbox` are inert legacy data: never drop them, never write or read them in new code (the Registry integration was removed, docs/decisions/0007).
- `seed_data.py` seeds only an empty categories table and fixes persisted category names; do not rename categories.
- Keep old readers working: add nullable columns first, backfill separately, switch reads last.
- Update docs/DATA_MODEL.md and docs/context/data-model.md with any change.
