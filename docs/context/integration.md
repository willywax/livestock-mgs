# Cross-service integration (mirrored)
This file is intentionally identical in livestock-mgs and tags-src. Update both copies together.
Snapshot: 2026-10-08; source tags pre-analysis-20261008 (Shamba 9b72555; Registry a520131).
Paths below start with the repository name. No database, migration, token minting, scheduler or deployed endpoint was exercised.

## Ownership and direction
Registry owns authoritative animal identity: DOB, birth cohort, production stage, tag status and canonical tag ID.
Shamba owns aggregate stock, farm operations and event history; it may reference identity but should not become a competing authority.
Implemented calls run Shamba -> Registry. No Registry -> Shamba HTTP client is implemented.
Shamba's drain comment mentions a Registry/scheduler caller, but neither a scheduler definition nor a reverse caller exists in these sources (`livestock-mgs/backend/server.py:4095`, `tags-src/backend/app/main.py:36`).
There is no shared package or generated contract. Shamba uses async httpx; Registry uses synchronous FastAPI routers and Session.

## Every cross-service operation
| Caller | Method and Registry path | Request / response | Trigger |
|---|---|---|---|
| RegistryClient.search_tags | GET /api/integration/tags | query filters -> IntegrationTagsPage | Browser RegistryTagPicker through Shamba proxy |
| RegistryClient.reconcile | GET /api/integration/reconcile | since, cursor -> IntegrationReconcilePage | Admin sync report |
| RegistryClient.post_status | POST /api/integration/tags/{tag_id}/status | IntegrationStatusChangeRequest -> IntegrationStatusChangeResponse | death / sold outbox |
| RegistryClient.post_event | POST /api/integration/tags/{tag_id}/events | IntegrationEventLogRequest -> IntegrationEventLogResponse | birth dam / tag-assignment outbox |
| RegistryClient.revert | POST /api/integration/events/{source_event_id}/revert | IntegrationRevertRequest -> IntegrationRevertResponse | Delivery branch exists, no domain producer wired |
Sources: `livestock-mgs/backend/registry_client.py:184`, `:227`, `:236`, `:264`, `:286`; `tags-src/backend/app/routers/integration.py:53`, `:97`, `:165`, `:236`, `:308`; schemas `tags-src/backend/app/schemas/integration.py:7`.
Browser never receives Google's service token. Its own JWT authorizes `GET /api/integration/registry/tags` (`livestock-mgs/backend/server.py:4106`).

## Authentication and audience agreement
- Shamba target/base variable: REGISTRY_BASE_URL. REGISTRY_AUDIENCE falls back to that base. Registry must configure INTEGRATION_AUDIENCE to the exact minted audience, which can differ from the custom-domain request host.
- Every outgoing request adds Authorization bearer and X-Actor-Name. Interactive search uses the logged-in user name; writes/report use the fixed ShambaManager Sync actor (`livestock-mgs/backend/registry_client.py:150`, `livestock-mgs/backend/registry_sync.py:23`).
- Registry validates Google token audience and the email allowlist INTEGRATION_ALLOWED_SERVICE_ACCOUNTS, plus nonblank actor header (`tags-src/backend/app/core/service_auth.py:23`). It does not explicitly require email_verified or fail closed on blank audience; configuration is an open deployment question.
- Shamba drain uses INTERNAL_SYNC_AUDIENCE and SYNC_ALLOWED_SERVICE_ACCOUNTS, rejects empty configuration, and requires email_verified (`livestock-mgs/backend/registry_auth.py:34`).
- Admin report/retry use ordinary Shamba JWT ADMIN, not service OIDC (`livestock-mgs/backend/server.py:4137`).
- Token cache refreshes five minutes before expiry. HTTP timeout is ten seconds (`livestock-mgs/backend/registry_client.py:30`, `:105`). Synchronous Google token fetch/verification occurs inside Shamba async functions; Medium event-loop blocking risk (`:110`, `:151`; `livestock-mgs/backend/registry_auth.py:55`).

## Outbox, idempotency and transaction boundary
1. Create log/add event persists event, stock adjustment and outbox in one local commit; HTTP delivery happens afterward (`livestock-mgs/backend/server.py:998`, `:1019`, `:1071`).
2. An outbox row is built only if registry_previous_status is truthy. That browser-supplied status is both the opt-in marker and death/sale concurrency expectation. A tag with blank status can be selected without producing a row (`livestock-mgs/backend/registry_sync.py:162`).
3. Keys: death:{event_id}, sold:{event_id}, birth:{event_id}, tag_assigned:{animal_id}. source_system is ShambaManager. Death/sale use only the first comma-separated tag; event count is not validated against the tag count (`livestock-mgs/backend/registry_sync.py:168`, `:185`, `:202`, `:255`).
4. Local source_event_id is unique. Registry deduplicates globally by (source_system, source_event_id), not by tag or action; previously used/reverted keys permanently replay the original outcome (`livestock-mgs/backend/models.py:342`; `tags-src/backend/app/models/integration_event.py:12`; `tags-src/backend/app/routers/integration.py:172`).
5. Outbox success becomes SENT; 409 becomes CONFLICT; 404 becomes FAILED; unavailable/auth failures remain PENDING until attempt 10, then FAILED. A drain selects up to 50 oldest pending rows with FOR UPDATE SKIP LOCKED (`livestock-mgs/backend/registry_sync.py:30`, `:111`).
6. Manual retry resets state/attempts but defers sending until a drain; there is no backoff schedule or next_attempt_at column (`livestock-mgs/backend/registry_sync.py:269`, `livestock-mgs/backend/models.py:332`).
7. High: editing an already-sent event overwrites its row and reuses its key; Registry acknowledges the old outcome, and Shamba ignores returned tag/status. The old animal can remain terminal while the replacement is unchanged (`livestock-mgs/backend/registry_sync.py:243`, `:38`; `tags-src/backend/app/routers/integration.py:173`).
8. High: Registry read/check/write is not locked or a conditional SQL update; parallel different keys can both pass expected_current_status. Concurrent identical keys can race into the unique constraint without recovery (`tags-src/backend/app/routers/integration.py:172`, `:185`, `:219`).
9. Medium: token/config failures and HTTP 400/422 escape the mapped error handling; a local commit can succeed before the request returns 500, and a drain can abort on one malformed row (`livestock-mgs/backend/registry_client.py:147`, `:151`, `:181`; `livestock-mgs/backend/server.py:1019`).

## Implemented sequence
```mermaid
sequenceDiagram
    actor U as Farm operator
    participant UI as Shamba React
    participant S as Shamba API
    participant DB as Shamba DB
    participant R as Registry API
    participant RD as Registry DB
    participant J as External scheduler (not configured in repo)
    U->>UI: Pick tag and record event
    UI->>S: JWT GET integration/registry/tags
    S->>R: OIDC GET /api/integration/tags + actor
    R-->>S: items + next_cursor
    S-->>UI: tag_id + current status
    UI->>S: JWT POST daily log / PUT event
    S->>DB: Event + stock + outbox, COMMIT
    S->>R: OIDC POST status or events, stable key
    R->>RD: Find key, check status, mutate + audit, COMMIT
    R-->>S: outcome or 409/404
    S->>DB: Persist SENT / CONFLICT / FAILED / PENDING
    S-->>UI: Saved; conflict warning when applicable
    J->>S: OIDC POST /api/internal/sync/drain
    S->>DB: Lock pending batch, SKIP LOCKED
    loop Pending rows
        S->>R: Retry with same key
        R-->>S: Original outcome or new result
    end
    S->>DB: Commit batch outcomes
    U->>S: ADMIN GET /api/internal/sync/report
    S->>R: GET /api/integration/reconcile?since=...
    R-->>S: First terminal-status page + next_cursor
    Note over S,R: Shamba currently ignores next_cursor
    Note over S,R: Revert endpoint exists, deletion does not call it
```

## Contract gaps and boundary findings
| Severity | Topic | Observed behavior and evidence |
|---|---|---|
| High | Birth event vocabulary | Shamba sends CALVED; Registry special-cases BIRTH. HTTP succeeds but last_birth_date/category do not update. `livestock-mgs/backend/registry_sync.py:212`; `tags-src/backend/app/routers/integration.py:253`. |
| High | Death status vocabulary | Shamba defaults to DECEASED, while migration flags DEAD/SOLD as terminal. Registry accepts arbitrary new_status, so DECEASED need not be excluded from picker/reconcile. Runtime overrides unknown. `livestock-mgs/backend/registry_sync.py:26`; `tags-src/backend/alembic/versions/0005_status_terminal.py:22`; `tags-src/backend/app/schemas/integration.py:28`. |
| High | Delete/revert | Shamba deletion reverses aggregate stock and hard-deletes Event, leaving sent/pending outbox untouched. REVERT branch/client exist but no producer. `livestock-mgs/backend/server.py:1446`; `livestock-mgs/backend/registry_sync.py:57`. |
| High | Identity duplication | Shamba stores/writes local DOB and status without Registry updates. They are not refreshed projections. `livestock-mgs/backend/models.py:223`; `livestock-mgs/backend/server.py:3096`, `:3220`, `:3373`, `:3381`. |
| High | Tag assignment | Local link commits before Registry existence is known; no unique registry_tag_id or species/location check. 404 leaves an assigned link plus FAILED row. TAG_ASSIGNED only logs an event, not animal creation/DOB. `livestock-mgs/backend/server.py:3295`; `livestock-mgs/backend/models.py:231`; `tags-src/backend/app/routers/integration.py:246`. |
| High | Soft deletion | Registry DELETE hard-deletes Animal and cascades integration history, losing dedupe memory; no tombstone feed. Shamba Event also hard-deletes. `tags-src/backend/app/routers/animals.py:297`; `tags-src/backend/app/models/integration_event.py:19`; `livestock-mgs/backend/server.py:1481`. |
| High | Delta sync absent | Neither updated_since nor a persisted watermark/identity-cache importer is present; tags search is not delta sync. IntegrationTagOut omits DOB/cohort/stage. `tags-src/backend/app/routers/integration.py:53`; `tags-src/backend/app/schemas/integration.py:7`; `livestock-mgs/backend/registry_client.py:184`. |
| Medium | Reconciliation | Registry pages terminal tags (default 25), filtered by last_updated; Shamba requests one page, includes unsent local attempts, collapses by tag without ordering, ignores Registry integration_event IDs. This is not full identity drift detection. `tags-src/backend/app/routers/integration.py:97`; `livestock-mgs/backend/registry_report.py:69`, `:85`. |
| Medium | Production-stage boundary | No implemented assignment from stage to status was found. Stage exists only in Registry model/migration and is absent from API/UI; permissive status inputs could admit stage labels. `tags-src/backend/app/models/animal.py:53`; `tags-src/backend/app/schemas/animal.py:48`; `tags-src/backend/app/routers/verification_sessions.py:275`. |
| Medium | Category/sex mapping | Shamba strips sex suffixes but does not send a sex filter. DUME MBEGU is not mapped to MBEGU; seeded Registry categories are cattle-only and omit VICHINDA. `livestock-mgs/backend/registry_client.py:36`; `tags-src/backend/app/scripts/seed_initial.py:17`, `:34`. |

## Revert semantics and unresolved correctness
Registry replays an already-reverted key; a status revert requires the animal still has that event's new_status, then restores previous_status and audits (`tags-src/backend/app/routers/integration.py:319`).
For BIRTH it recomputes from remaining integration births plus the event's saved prior date, and may restore MITAMBA (`:347`).
Medium: saved prior dates can refer to subsequently reverted births; out-of-order reverts can resurrect a stale date. This branch also has no lock against manual corrections. Add ordered/out-of-order and manual-edit tests before wiring automated reverts.
The supplied test suites disagree on CALVED versus BIRTH (`livestock-mgs/backend/tests/test_registry_sync.py:333`; `tags-src/backend/tests/test_integration_writes.py:199`). Their isolated mocks do not prove cross-service compatibility.

