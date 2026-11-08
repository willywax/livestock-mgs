# Roadmap
Sizes: S = under a day, M = a few days, L = a week or more (estimates, Unverified). Order is priority. `/next-improvement` takes the first open item. Dairy is explicitly out of scope (owner, 2026-11-08).

| # | Item | Size | Addresses | Notes |
|---|---|---|---|---|
| R1 | Close unauthenticated reads: add explicit role dependencies to the 13 public GETs (keep `/` health and `/auth/login` public) (+ tests asserting 401 for anonymous); check frontend still works for each role | M | K02 | Owner approved the intent. Separate branch from `chore/claude-setup`. Viewer must keep read access |
| R2 | Remove JWT fallback and default-admin seed (fail closed); owner rotates exposed credentials | M | K01 | Needs a safe bootstrap path for the first admin; coordinate deploy env first |
| R3 | Freeze the Shamba<->Registry vocabulary (CALVED/BIRTH, DECEASED/DEAD, categories) with shared contract fixtures | M | K03, K13 | Both repos |
| R4 | Test DB workflow: verify `docker-compose.test.yml` and add a Postgres-backed test target (stock concurrency, startup DDL) | M | K07, K15 | Compose file exists, unverified |
| R5 | Safe correction and deletion of synced events: immutable correction intents, cancel unsent, durable revert | L | K04, K05 | Out-of-order cases in Registry |
| R6 | Atomic stock updates and positive-count validation | M | K07 | |
| R7 | Delivery operations: drain scheduler, failure normalisation, reconcile all pages | M | K08, K09, K10 | |
| R8 | Align deployment: target region, secret bindings, correct README | S | K11 | Owner decides region |
| R9 | Registry ownership of identity: validated unique links, stop competing DOB/status writes | L | K06 | |
| R10 | Frontend tests and CI workflow (needs approval) | M | K15 | |
| R11 | Chemical rotation policy/inventory and notifications | L | PRD backlog | |

## Housekeeping (S)
Delete stale root files (K17), trim unused dependencies after import audit (K16), rewrite README.
