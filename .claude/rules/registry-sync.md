---
paths:
  - "backend/registry_*.py"
  - "backend/tests/test_registry_*.py"
  - "frontend/src/components/RegistryTagPicker.jsx"
  - "frontend/src/pages/RegistrySync.jsx"
---
# Registry sync rules
- Read `docs/context/integration.md` first. It is mirrored in the sibling repo `../tags-src`; contract changes must update both copies and both services.
- Outbox rows are created in the same local commit as the event; delivery happens after commit. Idempotency keys are `death:{event_id}`, `sold:{event_id}`, `birth:{event_id}`, `tag_assigned:{animal_id}`. Never reuse a key for a corrected payload.
- Known wire mismatches (CALVED vs BIRTH, DECEASED vs DEAD) are logged in docs/KNOWN_ISSUES.md. Do not "fix" one side silently, and do not write tests that cement the wrong vocabulary without a note.
- Failure states: SENT / CONFLICT (409) / FAILED (404 or after 10 attempts) / PENDING. Preserve them; do not swallow errors after the local commit.
- Never call a real Registry or mint real tokens from tests; keep httpx and Google auth mocked.
- Local enums are lowercase, Registry codes uppercase; category translation lives in `registry_client.py` and drops sex.
