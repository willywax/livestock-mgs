# Data model
Every column, constraint and an ER diagram: [context/data-model.md](context/data-model.md). Source: `backend/models.py`.

## Entities (13 tables)
`users`, `locations`, `categories`, `opening_balances`, `daily_logs`, `diseases`, `events`, `stock_levels`, `animals`, `health_intervals`, `farm_health_events`, `vaccine_types`, `registry_sync_outbox`.

## Invariants
- Stock is per Location + Species + Category. `stock_levels` = opening balance + applied events; the recompute endpoint is the repair path.
- Event create/edit/delete adjust stock symmetrically in the same transaction as the event write and the outbox insert.
- Transfer: subtract source, add destination, atomically. Category change: same location, atomic.
- Aggregate counts and the individual `animals` register are separate; a birth event does not create an Animal row.
- Registry owns tag identity, DOB, cohort, production stage, status. Animal `registry_tag_id` is a nullable, non-unique reference (no cross-DB FK). Do not add writers of local DOB/status.
- `events.animal_tags` / `offspring_tags` are comma-separated text. Outbox `source_event_id` is unique; keys are never reused for corrected payloads.
- Enums are native PostgreSQL enums with lowercase values (UserRole, EventType, SpeciesType, AnimalStatus, AnimalSex, HealthEventType, RegistrySyncAction/State...).

## Migration rules (current policy)
- Only nullable `ADD COLUMN IF NOT EXISTS`, and new tables after review. Never drop/rename/retype/tighten.
- `create_all` does not alter existing tables, enum members, indexes or constraints. Alembic is installed but there is no migration directory.
- Existing startup DDL is in `backend/server.py` near line 98; it is not a general migration framework.
- Test every schema change on the Docker test DB (`docker-compose.test.yml`), use `/db-change`, keep old readers working, and record rollback.
- Index candidates (unmeasured, Unverified): `events(daily_log_id)`, `daily_logs(log_date)`, outbox `state, created_at`.
