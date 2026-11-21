# Data model
Every column, constraint and an ER diagram: [context/data-model.md](context/data-model.md). Source: `backend/models/` package (enums.py, core.py, animals.py, health.py, reproduction.py, reconciliation.py, sales.py, mortality.py).

## Entities (18 tables in the models package)
`users`, `locations`, `categories`, `opening_balances`, `daily_logs`, `diseases`, `events`, `stock_levels`, `animals`, `health_intervals`, `farm_health_events`, `vaccine_types`, and (reproduction/profile, added 2026-11-08) `bull_assignments`, `reproductive_cycles`, `bcs_records`, `animal_photos`, `animal_notes`. Also `animal_location_history` (added 2026-11-08: animal move log written by the event-to-register sync; decision 0009). `animals.is_temp_tag` (boolean, added 2026-11-08: temporary tag for untagged newborns; see `POST /api/animals/{id}/replace-tag`).
Legacy: table `registry_sync_outbox` still exists in existing databases but has no model; never drop it in routine work.

## Invariants
- Stock is per Location + Species + Category. `stock_levels` = opening balance + applied events; the recompute endpoint is the repair path.
- Event create/edit/delete adjust stock symmetrically in the same transaction as the event write.
- Transfer: subtract source, add destination, atomically. Category change: same location, atomic.
- Aggregate counts and the individual `animals` register are separate; a birth event does not create an Animal row.
- `animals.registry_tag_id` is an inert legacy nullable column: echoed in responses, never written by code. Local Animal `birth_date`/`status` are Shamba's own data again.
- `animals.lifetime_calvings` (nullable INTEGER, added 2026-11-20) is a derived count of calving cycles (abortions excluded), backfilled once from `reproductive_cycles` and then recounted by `_sync_lifetime_calvings` after every cycle create, calving_outcome update or delete (best-effort: failures are logged as warnings and never raised, so the value can drift until the next save); exposed by `/api/reports/reproductive-status`. Run `backend/migrations/add_lifetime_calvings.sql` before release to add the column and initialize NULL counters; repeated runs preserve existing counters.
- `events.animal_tags` / `offspring_tags` / `mother_tag` are plain comma-separated text.
- Enums are native PostgreSQL enums. The database stores the uppercase member NAMES (e.g. `ADMIN`, `LIVE_CALF`); Python/API values are lowercase.
- Reproduction: one `reproductive_cycles` row per service/pregnancy/calving of a FEMALE animal (`cycle_number` per animal); `calving_interval_days`/`days_to_service` are derived from the previous calved cycle; bull assignments reference a MALE animal. Photos store only a GCS object path.
- Category transitions: `category_transition_rules` (per species and source category: target category for females/males, trigger `age` + `trigger_age_months` or `event` + `trigger_event`; unique on species, source, trigger type) and `category_transitions` (audit log of each confirmed change). Both are new tables created by `create_all`; the trigger enum is a new native PG enum (stored as `AGE`/`EVENT`). No existing table changed.

## Migration rules (current policy)
- Only nullable `ADD COLUMN IF NOT EXISTS`, and new tables after review. Never drop/rename/retype/tighten.
- `create_all` does not alter existing tables, enum members, indexes or constraints. Alembic is installed but there is no migration directory.
- Existing startup DDL is in `backend/bootstrap.py` (`apply_additive_ddl`); it is not a general migration framework.
- Test every schema change on the Docker test DB (`docker-compose.test.yml`), use `/db-change`, keep old readers working, and record rollback.
- Performance indexes (2026-11-10): 16 btree indexes declared in `__table_args__` in `backend/models/` and created on existing databases by `backend/migrations/add_perf_indexes.sql` (manual, `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, not in a transaction, run by the owner with `psql -f`). Index-only; no column/table changes. Names match between models and SQL. Gain unmeasured (Unverified). Rollback: `DROP INDEX CONCURRENTLY IF EXISTS <name>`. Skipped as redundant: `daily_logs(location_id[, log_date])` (uq_daily_log) and the `stock_levels` composite (uq_stock_level).

## Daily-log reproductive journal (2026-11-10)
`events` adds `pd_result` and `months_pregnant`; `eventtype` adds `PD_TEST` and
`SERVICE`. `event_animal_links` stores durable animal/event/role associations,
original tags, active flags, reproductive payloads/baselines, external source
keys and optional category-transition IDs. Event deletion retains inactive
journal rows with a null event ID so reproductive baselines remain available.
See [migration and replay details](DAILY_REPRODUCTIVE_SYNC.md).
