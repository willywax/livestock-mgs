-- Performance indexes for ShambaManager (indexes only: no column/table changes).
--
-- HOW TO RUN (manually, after review, ideally against a copy first):
--   psql "$DATABASE_URL" -f backend/migrations/add_perf_indexes.sql
--
-- * CREATE INDEX CONCURRENTLY cannot run inside a transaction block, so do NOT
--   wrap this file in BEGIN/COMMIT and do not use psql --single-transaction.
-- * Each statement is independent; IF NOT EXISTS makes the file safe to re-run.
-- * If a CONCURRENTLY build fails it leaves an INVALID index behind. Find with:
--     SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
--   then DROP INDEX CONCURRENTLY <name>; and re-run this file.
-- * Index names match the Index() declarations in backend/models.py.
-- * Rollback: DROP INDEX CONCURRENTLY IF EXISTS <name>; (no data is lost).

-- animals
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animals_location_id ON animals (location_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animals_category_id ON animals (category_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animals_reproductive_status ON animals (reproductive_status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animals_birth_date ON animals (birth_date);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animals_species_category_status ON animals (species, category_id, status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animals_location_status ON animals (location_id, status);

-- daily_logs (location_id, log_date) is already covered by unique constraint uq_daily_log
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_daily_logs_log_date ON daily_logs (log_date);

-- events
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_daily_log_id ON events (daily_log_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_event_type ON events (event_type);

-- reproductive_events (animal_id alone is already indexed)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_repro_events_event_type ON reproductive_events (event_type);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_repro_events_event_date ON reproductive_events (event_date);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_repro_events_animal_date ON reproductive_events (animal_id, event_date);

-- animal_identifiers
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animal_identifiers_id_value ON animal_identifiers (id_value);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_animal_identifiers_type_value ON animal_identifiers (id_type, id_value);

-- category_transitions (animal_id alone is already indexed)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_category_transitions_date ON category_transitions (transition_date);

-- reconciliation_entries (session_id is already indexed)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_recon_entries_match_status ON reconciliation_entries (match_status);
