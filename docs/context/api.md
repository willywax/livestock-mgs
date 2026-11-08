# ShambaManager API

Source-only snapshot: 2026-10-08; deployment and database state were not inspected.
68 explicitly declared HTTP routes. Framework-generated /docs, /redoc and /openapi.json are public by default; they are not business endpoints. Registry static /assets is conditional on built assets.

Auth describes backend enforcement, not frontend visibility. Shamba uses phone/password JWT; Registry uses name/PIN JWT. OIDC is a separate service identity. Request names omit injected DB/auth arguments; untyped responses are labeled explicitly.

| Method | Path | Auth | Purpose / handler | Request -> response schema | Caller | Source |
|---|---|---|---|---|---|---|
| GET | `/api/` | Public | root | none -> dict (no model) | Health/manual clients; no in-repo service caller | `backend/server.py:166` |
| POST | `/api/auth/login` | Public | login | UserLogin -> TokenResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:171` |
| GET | `/api/auth/me` | JWT active user | get me | path/query only -> UserResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:188` |
| GET | `/api/users` | JWT ADMIN | list users | path/query only -> List[UserResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:193` |
| POST | `/api/users` | JWT ADMIN | create user | UserCreate -> UserResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:202` |
| PUT | `/api/users/{user_id}` | JWT ADMIN | update user | UserUpdate -> UserResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:224` |
| DELETE | `/api/users/{user_id}` | JWT ADMIN | delete user | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:247` |
| GET | `/api/locations` | Public | list locations | path/query only -> List[LocationResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:266` |
| GET | `/api/locations/{location_id}` | Public | get location | path/query only -> LocationResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:272` |
| POST | `/api/locations` | JWT ADMIN | create location | LocationCreate -> LocationResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:280` |
| PUT | `/api/locations/{location_id}` | JWT ADMIN | update location | LocationUpdate -> LocationResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:296` |
| GET | `/api/templates/locations` | Public | download locations template | none -> CSV StreamingResponse (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:321` |
| GET | `/api/templates/opening-balances` | Public | download opening balances template | path/query only -> CSV StreamingResponse (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:338` |
| POST | `/api/import/locations` | JWT ADMIN | import locations | UploadFile -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:384` |
| POST | `/api/import/opening-balances` | JWT ADMIN | import opening balances | UploadFile -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:439` |
| GET | `/api/categories` | Public | list categories | path/query only -> List[CategoryResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:563` |
| GET | `/api/diseases` | Public | list diseases | path/query only -> List[DiseaseResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:578` |
| POST | `/api/diseases` | JWT ADMIN (inline) | create disease | DiseaseCreate -> DiseaseResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:593` |
| DELETE | `/api/diseases/{disease_id}` | JWT ADMIN (inline) | delete disease | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:618` |
| PUT | `/api/diseases/{disease_id}` | JWT ADMIN (inline) | update disease | DiseaseCreate -> DiseaseResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:637` |
| GET | `/api/opening-balances` | Public | list opening balances | path/query only -> List[OpeningBalanceResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:662` |
| POST | `/api/opening-balances` | JWT ADMIN | create opening balance | OpeningBalanceCreate -> OpeningBalanceResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:695` |
| PUT | `/api/opening-balances/{balance_id}` | JWT ADMIN | update opening balance | OpeningBalanceUpdate -> OpeningBalanceResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:742` |
| GET | `/api/daily-logs` | Public | list daily logs | path/query only -> List[DailyLogResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:773` |
| GET | `/api/daily-logs/{log_id}` | Public | get daily log | path/query only -> DailyLogResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:829` |
| POST | `/api/daily-logs` | JWT ADMIN,DATA_ENTRY | create daily log | DailyLogCreate -> DailyLogResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:927` |
| POST | `/api/daily-logs/{log_id}/events` | JWT ADMIN | add event to daily log | EventCreate -> EventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1071` |
| POST | `/api/daily-logs/{log_id}/lock` | JWT ADMIN,VIEWER | lock daily log | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1179` |
| PUT | `/api/daily-logs/{log_id}` | JWT ADMIN | update daily log | DailyLogUpdate -> DailyLogResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1197` |
| PUT | `/api/events/{event_id}` | JWT ADMIN,DATA_ENTRY | update event | EventUpdate -> EventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1266` |
| DELETE | `/api/events/{event_id}` | JWT ADMIN | delete event | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1446` |
| GET | `/api/stock-levels` | Public | list stock levels | path/query only -> List[StockLevelResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1495` |
| POST | `/api/stock-levels/recompute` | JWT ADMIN | recompute stock levels endpoint | path/query only -> dict (no model) | Admin/manual; no frontend wrapper found | `backend/server.py:1528` |
| GET | `/api/dashboard` | Public | get dashboard | path/query only -> DashboardResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1540` |
| GET | `/api/reports/daily` | Public | get daily report | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1882` |
| GET | `/api/reports/range` | Public | get range report | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1935` |
| GET | `/api/reports/analytics` | Public | get analytics report | path/query only -> AnalyticsResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:1990` |
| GET | `/api/reports/detailed` | Public | get detailed report | path/query only -> DetailedReportResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:2508` |
| GET | `/api/templates/animals` | Public | download animals template | path/query only -> CSV StreamingResponse (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:2992` |
| GET | `/api/animals` | JWT active user | list animals | path/query only -> List[AnimalResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3039` |
| POST | `/api/animals` | JWT ADMIN,DATA_ENTRY | create animal | AnimalCreate -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3071` |
| POST | `/api/animals/bulk-import` | JWT ADMIN | bulk import animals | UploadFile -> BulkImportResult | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3118` |
| GET | `/api/animals/untagged-calves` | JWT ADMIN | list untagged calves | path/query only -> List[UntaggedCalfResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3241` |
| POST | `/api/animals/{animal_id}/assign-registry-tag` | JWT ADMIN | assign registry tag | AnimalAssignRegistryTag -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3280` |
| GET | `/api/animals/{animal_id}` | JWT active user | get animal | path/query only -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3318` |
| PUT | `/api/animals/{animal_id}` | JWT ADMIN,DATA_ENTRY | update animal | AnimalUpdate -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3336` |
| POST | `/api/animals/{animal_id}/transfer` | JWT ADMIN | transfer animal | AnimalTransfer -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3396` |
| GET | `/api/health-intervals` | JWT active user | list health intervals | path/query only -> List[HealthIntervalResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3530` |
| POST | `/api/health-intervals` | JWT ADMIN | create health interval | HealthIntervalCreate -> HealthIntervalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3557` |
| PUT | `/api/health-intervals/{interval_id}` | JWT ADMIN | update health interval | HealthIntervalUpdate -> HealthIntervalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3596` |
| DELETE | `/api/health-intervals/{interval_id}` | JWT ADMIN | delete health interval | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3621` |
| GET | `/api/farm-health/last-events` | JWT active user | get last events | path/query only -> List[LastEventSummary] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3635` |
| GET | `/api/farm-health/upcoming` | JWT active user | get upcoming health events | path/query only -> List[FarmHealthEventResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3715` |
| GET | `/api/farm-health/product-suggestions` | JWT active user | get product suggestions | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3740` |
| GET | `/api/farm-health` | JWT active user | list farm health events | path/query only -> List[FarmHealthEventResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3752` |
| POST | `/api/farm-health` | JWT ADMIN,DATA_ENTRY | create farm health event | FarmHealthEventCreate -> FarmHealthEventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3790` |
| GET | `/api/farm-health/{event_id}` | JWT active user | get farm health event | path/query only -> FarmHealthEventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3858` |
| PUT | `/api/farm-health/{event_id}` | JWT ADMIN | update farm health event | FarmHealthEventUpdate -> FarmHealthEventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3875` |
| DELETE | `/api/farm-health/{event_id}` | JWT ADMIN | delete farm health event | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3936` |
| GET | `/api/vaccine-types` | JWT active user | list vaccine types | path/query only -> List[VaccineTypeResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3952` |
| POST | `/api/vaccine-types` | JWT ADMIN | create vaccine type | VaccineTypeCreate -> VaccineTypeResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3967` |
| PUT | `/api/vaccine-types/{vt_id}` | JWT ADMIN | update vaccine type | VaccineTypeUpdate -> VaccineTypeResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:3988` |
| DELETE | `/api/vaccine-types/{vt_id}` | JWT ADMIN | delete vaccine type | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:4014` |
| GET | `/api/farm-health-events/last-vaccinations` | JWT active user | get last vaccinations | path/query only -> List[LastVaccinationSummary] | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:4035` |
| POST | `/api/internal/sync/drain` | OIDC service | drain registry sync | path/query only -> SyncDrainResult | Intended scheduler/service; no caller config found | `backend/server.py:4095` |
| GET | `/api/integration/registry/tags` | JWT active user | search registry tags | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:4106` |
| GET | `/api/internal/sync/report` | JWT ADMIN | get registry sync report | path/query only -> SyncReportResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:4137` |
| POST | `/api/internal/sync/{outbox_id}/retry` | JWT ADMIN | retry registry sync row | path/query only -> OutboxIssueResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/server.py:4155` |

## Schema and auth lookup

- Pydantic contracts: `backend/schemas.py:1`; enum values: `backend/models.py:9`. Request models with optional fields do not necessarily support clearing fields; handlers commonly ignore None.
- Active-user verification and role factory: `backend/auth.py:37`, `backend/auth.py:67`; internal OIDC: `backend/registry_auth.py:34`.
- High: unauthenticated business reads include daily logs, opening balances, stock and reports (`backend/server.py:773`, `backend/server.py:1990`). Browser ProtectedRoute (`frontend/src/App.js:24`) does not secure these routes.
- Low: generated API/client comments can lag actual roles: add-event is ADMIN, update-event allows ADMIN/DATA_ENTRY, lock allows ADMIN/VIEWER (`backend/server.py:1071`, `backend/server.py:1266`, `backend/server.py:1179`).
- High: Registry tag assignment commits a raw tag link before delivery/validation; a missing Registry tag leaves a persisted local link (`backend/server.py:3295`).
