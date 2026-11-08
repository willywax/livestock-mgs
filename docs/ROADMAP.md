# Roadmap
Sizes: S = under a day, M = a few days, L = a week or more (estimates, Unverified). Order is priority. `/next-improvement` takes the first open item. Dairy is explicitly out of scope (owner, 2026-11-08).

| # | Item | Size | Addresses | Notes |
|---|---|---|---|---|
| R2 | Remove JWT fallback and default-admin seed (fail closed); owner rotates exposed credentials | M | K01 | Needs a safe bootstrap path for the first admin; coordinate deploy env first |
| R4 | Backend test suite: no automated backend tests exist. Verify `docker-compose.test.yml`, add mocked route tests and Postgres-backed tests (stock concurrency, startup DDL, atomic event+stock) | M | K07, K15 | Compose file exists, unverified |
| R6 | Atomic stock updates and positive-count validation | M | K07 | |
| R8 | Align deployment: target region, secret bindings, correct README; owner removes obsolete REGISTRY_*/INTERNAL_SYNC_* env vars and any drain scheduler job | S | K11, K20 | Owner decides region |
| R10 | Frontend tests and CI workflow (needs approval) | M | K15 | |
| R11 | Chemical rotation policy/inventory and notifications | L | PRD backlog | |

Done 2026-11-08: R1 (close unauthenticated reads) on `ft/r1-auth-hardening`; follow-up K21 needs a frontend change.

Removed from the roadmap 2026-11-08 (obsolete after the Registry integration was removed): former R3 (wire vocabulary), R5 (correction/deletion of synced events), R7 (drain scheduler/reconciliation), R9 (Registry identity ownership).

## Housekeeping (S)
Delete stale root files (K17), trim unused dependencies after import audit (K16), rewrite README.
