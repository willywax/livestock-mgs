# 0008 Reproduction schema and animal photos in Google Cloud Storage
Status: accepted 2026-11-08 (owner approved the plan in-session).

Decision: add five NEW tables (`bull_assignments`, `reproductive_cycles`, `bcs_records`, `animal_photos`, `animal_notes`) and five new PostgreSQL enums, created by `create_all` (consistent with 0005: additive only, no existing table/column/enum touched). Photos are stored as objects in a private GCS bucket named by env var `GCS_BUCKET_NAME`; the database stores only the object path. Reads return 1-hour v4 signed URLs. `google-cloud-storage` is imported lazily inside the photo helpers so the app (and the SQLite test suite) runs without it; without the env var or package, uploads return 503 and reads return `photo_url=null` with a warning.

Why: reproduction records and animal profiles are needed per animal; binary images do not belong in PostgreSQL; a private bucket plus signed URLs avoids public image links.

Consequences / open points:
- Cycle numbering is `MAX+1` per animal; the unique constraint turns a race into a 409.
- Calving rate denominator is the latest Koo opening balance on or before 1 January (all species), falling back to current stock.
- Signed-URL generation on Cloud Run needs a service account allowed to sign (IAM `signBlob`); the code falls back to IAM signing but this is UNVERIFIED until run against a real bucket.
- Upload accepts jpeg/png/webp up to 10 MB and checks the file signature; no virus scanning or thumbnails.
- Frontend for all of this is not built yet.

## Update 2026-11-20: KPIs read daily-log events too
The page showed calving rate 0%, conception 100% and 0 open cows on a ranch that records reproduction in daily logs (production had 2 cycles and 17 animals with a calving date but no cycle). `_repro_metrics` now combines daily-log BIRTH (offspring count) and PD_TEST (count by result) events with cycles, skipping a cycle calving/PD when a linked event already covers the same animal and date; pregnant/open counts come from `animals.reproductive_status`. `/analytics/reproduction` gained an optional `species` filter and the browser-side per-species KPI maths was removed. The Koo denominator rule above is unchanged.
