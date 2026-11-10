-- Additive daily-log reproductive sync. Run before deploying clients using PD_TEST/SERVICE.
-- SQLAlchemy PostgreSQL enums store member NAMES (uppercase).
-- Run without --single-transaction: new enum values must commit before use.
ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'PD_TEST';
ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'SERVICE';

BEGIN;
ALTER TABLE events ADD COLUMN IF NOT EXISTS pd_result VARCHAR(20);
ALTER TABLE events ADD COLUMN IF NOT EXISTS months_pregnant INTEGER;
CREATE TABLE IF NOT EXISTS event_animal_links (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    animal_id INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    tag_at_link VARCHAR(100),
    is_active BOOLEAN NOT NULL,
    source_key VARCHAR(100),
    reproductive_payload JSON,
    reproductive_baseline JSON,
    category_transition_id INTEGER REFERENCES category_transitions(id),
    CONSTRAINT uq_event_animal_role UNIQUE(event_id, animal_id, role),
    CONSTRAINT uq_animal_repro_source UNIQUE(animal_id, source_key)
);
CREATE INDEX IF NOT EXISTS ix_event_animal_links_event_id ON event_animal_links(event_id);
CREATE INDEX IF NOT EXISTS ix_event_animal_links_animal_id ON event_animal_links(animal_id);
COMMIT;
-- Leave additive schema in place on rollback. Older code cannot decode PD_TEST/SERVICE event rows;
-- after recording these types, roll back only to an image retaining the new enum members.
-- Do not remove enum values or journal rows: newer event rows / reproductive baselines depend on them.
