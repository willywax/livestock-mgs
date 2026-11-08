# 0007 Remove the Herd Tag Registry integration
Status: accepted (owner, 2026-11-08). Supersedes 0002 and 0003.
Decision: delete all application code that talked to the external Herd Tag Registry: client, OIDC auth, outbox/drain, reconciliation report, tag picker and sync UI, `/api/internal/sync/*`, `/api/integration/registry/tags`, `assign-registry-tag` and `untagged-calves` routes, and the mocked tests for them.
Kept (deliberately, to avoid risk on live data): table `registry_sync_outbox` (model and enums removed, table stays) and column `animals.registry_tag_id` (still in the model and `AnimalResponse`, never written). Nothing may drop them without a separate reviewed plan.
Consequences: death/sold/dam tags are plain free-text fields; no automated backend tests remain (ROADMAP R4); existing pending outbox rows are never delivered; fresh databases will not create the outbox table; Registry-related env vars and any drain scheduler job become obsolete (owner action, K20). `requirements.txt` was intentionally not changed (httpx, google-auth*, still required transitively).
Reintroducing any Registry call requires a full design review.
