# Data model
Every column, constraint and an ER diagram: [context/data-model.md](context/data-model.md). Source: `backend/models.py`.

## Entities (18 tables in models.py)
`users`, `locations`, `categories`, `opening_balances`, `daily_logs`, `diseases`, `events`, `stock_levels`, `animals`, `health_intervals`, `farm_health_events`, `vaccine_types`, and (reproduction/profile, added 2026-11-08) `bull_assignments`, `reproductive_cycles`, `bcs_records`, `animal_photos`, `animal_notes`. Also `animal_location_history` (added 2026-11-08: animal move log written by the event-to-register sync; decision 0009).
Legacy: table `registry_sync_outbox` still exists in existing databases but has no model; never drop it in routine work.

## Invariants
- Stock is per Location + Species + Category. `stock_levels` = opening balance + applied events; the recompute endpoint is the repair path.
- Event create/edit/delete adjust stock symmetrically in the same transaction as the event write.
- Transfer: subtract source, add destination, atomically. Category change: same location, atomic.
- Aggregate counts and the individual `animals` register are separate; a birth event does not create an Animal row.
- `animals.registry_tag_id` is an inert legacy nullable column: echoed in responses, never written by code. Local Animal `birth_date`/`status` are Shamba's own data again.
- `events.animal_tags` / `offspring_tags` / `mother_tag` are plain comma-separated text.
- Enums are native PostgreSQL enums. The database stores the uppercase member NAMES (e.g. `ADMIN`, `LIVE_CALF`); Python/API values are lowercase.
- Reproduction: one `reproductive_cycles` row per service/pregnancy/calving of a FEMALE animal (`cycle_number` per animal); `calving_interval_days`/`days_to_service` are derived from the previous calved cycle; bull assignments reference a MALE animal. Photos store only a GCS object path.

## Migration rules (current policy)
- Only nullable `ADD COLUMN IF NOT EXISTS`, and new tables after review. Never drop/rename/retype/tighten.
- `create_all` does not alter existing tables, enum members, indexes or constraints. Alembic is installed but there is no migration directory.
- Existing startup DDL is in `backend/server.py` near line 98; it is not a general migration framework.
- Test every schema change on the Docker test DB (`docker-compose.test.yml`), use `/db-change`, keep old readers working, and record rollback.
- Index candidates (unmeasured, Unverified): `events(daily_log_id)`, `daily_logs(log_date)`.
