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
