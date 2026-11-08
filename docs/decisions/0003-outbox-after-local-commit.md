# 0003 Registry delivery through an outbox after local commit
Status: accepted (backend/registry_sync.py, git history 'Support registry tag edits'). Event + stock + outbox row commit together; delivery happens afterwards and is retried by a drain endpoint with OIDC auth. Idempotency keys are per source event. Open problems: key reuse on edits, no revert on delete (K04, K05).
