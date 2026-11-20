-- Add the derived cycle count before deploying the reproduction reports.
-- Only initialize NULL values; re-running preserves counters maintained by the API.
-- Daily-log births and reproductive_events do not create cycles and are not counted.
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '120s';
ALTER TABLE animals ADD COLUMN IF NOT EXISTS lifetime_calvings INTEGER;
UPDATE animals AS a
SET lifetime_calvings = (
    SELECT COUNT(*) FROM reproductive_cycles AS c
    WHERE c.animal_id = a.id
      AND c.calving_outcome IN ('LIVE_CALF', 'STILLBIRTH', 'ASSISTED_LIVE', 'ASSISTED_DEAD')
)
WHERE a.lifetime_calvings IS NULL;
COMMIT;
-- Rollback: leave the nullable column in place when reverting application traffic.
