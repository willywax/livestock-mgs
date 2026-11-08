---
name: release
description: Walk through the ShambaManager manual release (build and deploy to Cloud Run). Manual only; never auto-run.
disable-model-invocation: true
---
# /release
Release is manual and affects a live system. The project settings deny `gcloud`, so prepare the exact commands and let the user run them unless they explicitly change that.
1. Run `/ship-check`; stop if the result is not PASS.
2. Ask the user to confirm the target region (checked-in docs say us-central1, the owner's target is africa-south1), image tags, which service(s), and that the env vars and secret bindings (names in `docs/DEPLOYMENT.md`) exist in the target.
3. If the diff includes schema changes, confirm `/db-change` was done (backend boot applies DDL).
4. Print the commands from `docs/DEPLOYMENT.md` with the confirmed values (never secret values). Backend first, then frontend.
5. Give the smoke-test checklist and the rollback command from `docs/DEPLOYMENT.md` (rollback is Unverified).
6. After the user reports the result, update `docs/DEPLOYMENT.md` if the process changed.
