# Roadmap
Sizes: S = under a day, M = a few days, L = a week or more (estimates, Unverified). Order is priority. `/next-improvement` takes the first open item. Dairy is explicitly out of scope (owner, 2026-11-08).

| # | Item | Size | Addresses | Notes |
|---|---|---|---|---|
| R2 | Remove JWT fallback and default-admin seed (fail closed); owner rotates exposed credentials | M | K01 | Needs a safe bootstrap path for the first admin; coordinate deploy env first |
| R4 | Backend test suite: a SQLite in-memory suite exists (auth, stock helpers, events, reproduction; 40 functions). Remaining: verify `docker-compose.test.yml`, add Postgres-backed tests (stock concurrency, startup DDL, atomic event+stock) | M | K07, K15 | Compose file exists, unverified |
| R6 | Atomic stock updates and positive-count validation | M | K07 | |
| R8 | Align deployment: target region, secret bindings, correct README; owner removes obsolete REGISTRY_*/INTERNAL_SYNC_* env vars and any drain scheduler job | S | K11, K20 | Owner decides region |
| R10 | Frontend tests and CI workflow (needs approval) | M | K15 | |
| R12 | (done 2026-11-08, branch `ft/animal-detail`) Animal detail page for reproduction/profile; remaining: browser verification with real data and a GCS bucket | S | K22, K25 | Needs `GCS_BUCKET_NAME` configured for photos |
| R13 | Backend: `species` filter on `/analytics/reproduction` and species-aware gestation default (sheep 147, goat 150) instead of the 283-day constant; then drop the browser-side species KPI maths | S | K23, K24 | Additive backend change |
| R11 | Chemical rotation policy/inventory and notifications | L | PRD backlog | |

Done 2026-11-08: R1 (close unauthenticated reads) on `ft/r1-auth-hardening`; follow-up K21 needs a frontend change.
Done 2026-11-08: backend reproduction/animal-profile schema and routes (branch `ft/repro-schema`, decision 0008). Follow-ups: R13 backend species support; K22 verify on the PostgreSQL test DB and a real GCS bucket.
Done 2026-11-08: Reproduction dashboard page and shared dialogs (branch `ft/repro-frontend`).

Removed from the roadmap 2026-11-08 (obsolete after the Registry integration was removed): former R3 (wire vocabulary), R5 (correction/deletion of synced events), R7 (drain scheduler/reconciliation), R9 (Registry identity ownership).

## Housekeeping (S)
Delete stale root files (K17), trim unused dependencies after import audit (K16), rewrite README.
Done 2026-11-08: Animal detail page `/animals/:id` (branch `ft/animal-detail`).
