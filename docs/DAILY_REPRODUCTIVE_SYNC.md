# Daily-log reproductive synchronization

Implemented 2026-11-10. Daily logs use `birth` for calving, lambing and kidding.
Birth updates the linked mother, not her offspring: open status, calving date,
cleared pregnancy months and zero services. An applicable first-calving rule
also advances her category once. PD tests update status/date/months; pregnant
results reset services. Abortion clears pregnancy months and last-calving date.
Daily services increment only for open/unknown females. Existing death, sale,
transfer and stock-helper behavior is preserved.

Sync is best effort after event persistence. Failures produce warnings rather
than rejecting saved logs. The category hook has its own savepoint. Events can
link multiple animals through subject, mother and offspring roles; these links
survive tag replacement. The new Daily Log Timeline tab loads only on activation,
supports dates/type filters, and loads 20 entries at a time. The older animal
timeline remains available.

## Edits, deletion and historical data

The first reproductive update captures an animal baseline. Active journal
entries replay in date/link order, making repeated saves idempotent and allowing
edits/deletions to remove earlier effects. Later standalone reproductive events
and cycle calvings participate in this journal. Deleted daily events leave
inactive links with null event IDs to preserve the baseline.

Entries dated before the baseline's latest known reproductive date are skipped
for state replay; they remain visible in the feed. This protects existing state
when entering older observations, but cannot reconstruct unknown historical
state. First-calving category/stock transitions are retained when the originating
birth is changed or deleted; sync returns a warning so an operator can review
the category separately. Automatic reversal could conflict with later movements.

## Migration and release

Run `backend/migrations/add_daily_reproductive_sync.sql` against PostgreSQL
before deploying clients that record the new types. Do not wrap the file in a
single transaction: enum additions must commit before use. It adds nullable
event fields, enum members and the durable journal table/indexes. Startup also
supports additive schema creation. Leave the additive schema on rollback;
after new event types are recorded, the rollback image must retain their enum
support so it can read those rows.

For historical timeline links, explicitly supply `DATABASE_URL` and `JWT_SECRET`
and run from the repository root:

```powershell
python backend/migrations/backfill_daily_event_links.py
python backend/migrations/backfill_daily_event_links.py --apply
```

The first command previews counts. The second persists links. Backfill uses
unambiguous species/tag matches and available durable movement history; missing
or ambiguous tags remain unresolved. It does not replay reproduction or change
stock and is idempotent for already-linked events.

## Verification

228 backend tests passed using the in-memory test suite. The three live-HTTP
modules (`test_csv_import`, `test_dashboard_analytics`, `test_disease_events`)
were excluded as requested; no server was started. All 26 frontend tests passed.
The production build completed with existing hook/Browserslist warnings.
Stock helpers were checked unchanged and the API client change is append-only.
The SQL migration and backfill have not been run against production PostgreSQL;
this feature has not been deployed.
