# ShambaManager API

> **Updated 2026-11-08:** the Herd Tag Registry integration was removed from the application (docs/decisions/0007). Content below was trimmed accordingly; line numbers are from the 2026-10-08 snapshot and have shifted. Treat anything still mentioning the Registry as historical.


Source-only snapshot: 2026-10-08; deployment and database state were not inspected.
62 explicitly declared HTTP routes (68 before the Registry removal). Framework-generated /docs, /redoc and /openapi.json are public by default; they are not business endpoints. Registry static /assets is conditional on built assets.

Auth describes backend enforcement, not frontend visibility. Shamba uses phone/password JWT; Registry uses name/PIN JWT. OIDC is a separate service identity. Request names omit injected DB/auth arguments; untyped responses are labeled explicitly.

> **Auth hardening 2026-11-08 (branch `ft/r1-auth-hardening`):** every business endpoint now requires a valid JWT. 13 previously open GET routes now use `require_roles(UserRole.ADMIN, UserRole.DATA_ENTRY, UserRole.VIEWER)`: `/api/locations`, `/api/locations/{location_id}`, `/api/categories`, `/api/diseases`, `/api/opening-balances`, `/api/daily-logs`, `/api/daily-logs/{log_id}`, `/api/stock-levels`, `/api/dashboard`, `/api/reports/daily`, `/api/reports/range`, `/api/reports/analytics`, `/api/reports/detailed`. Still public by design: `GET /api/` (health), `POST /api/auth/login`, and the three CSV template downloads (`/api/templates/locations`, `/api/templates/opening-balances`, `/api/templates/animals`; the browser downloads them with a plain link that cannot send a JWT). Two of the templates read location and category names from the DB (KNOWN_ISSUES K21). A missing Authorization header returns 403 (HTTPBearer); an invalid or expired token returns 401. Line numbers in the Source column predate this change.

| Method | Path | Auth | Purpose / handler | Request -> response schema | Caller | Source |
|---|---|---|---|---|---|---|
| GET | `/api/` | Public | root | none -> dict (no model) | Health/manual clients; no in-repo service caller | `backend/routers/system.py` |
| POST | `/api/auth/login` | Public | login | UserLogin -> TokenResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/auth.py` |
| GET | `/api/auth/me` | JWT active user | get me | path/query only -> UserResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/auth.py` |
| GET | `/api/users` | JWT ADMIN | list users | path/query only -> List[UserResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/auth.py` |
| POST | `/api/users` | JWT ADMIN | create user | UserCreate -> UserResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/auth.py` |
| PUT | `/api/users/{user_id}` | JWT ADMIN | update user | UserUpdate -> UserResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/auth.py` |
| DELETE | `/api/users/{user_id}` | JWT ADMIN | delete user | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/auth.py` |
| GET | `/api/locations` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | list locations | path/query only -> List[LocationResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/locations.py` |
| GET | `/api/locations/{location_id}` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | get location | path/query only -> LocationResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/locations.py` |
| POST | `/api/locations` | JWT ADMIN | create location | LocationCreate -> LocationResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/locations.py` |
| PUT | `/api/locations/{location_id}` | JWT ADMIN | update location | LocationUpdate -> LocationResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/locations.py` |
| GET | `/api/templates/locations` | Public | download locations template | none -> CSV StreamingResponse (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/imports.py` |
| GET | `/api/templates/opening-balances` | Public | download opening balances template | path/query only -> CSV StreamingResponse (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/imports.py` |
| POST | `/api/import/locations` | JWT ADMIN | import locations | UploadFile -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/imports.py` |
| POST | `/api/import/opening-balances` | JWT ADMIN | import opening balances | UploadFile -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/imports.py` |
| GET | `/api/categories` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | list categories | path/query only -> List[CategoryResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reference_data.py` |
| GET | `/api/diseases` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | list diseases | path/query only -> List[DiseaseResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reference_data.py` |
| POST | `/api/diseases` | JWT ADMIN (inline) | create disease | DiseaseCreate -> DiseaseResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reference_data.py` |
| DELETE | `/api/diseases/{disease_id}` | JWT ADMIN (inline) | delete disease | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reference_data.py` |
| PUT | `/api/diseases/{disease_id}` | JWT ADMIN (inline) | update disease | DiseaseCreate -> DiseaseResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reference_data.py` |
| GET | `/api/opening-balances` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | list opening balances | path/query only -> List[OpeningBalanceResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/opening_balances.py` |
| POST | `/api/opening-balances` | JWT ADMIN | create opening balance | OpeningBalanceCreate -> OpeningBalanceResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/opening_balances.py` |
| PUT | `/api/opening-balances/{balance_id}` | JWT ADMIN | update opening balance | OpeningBalanceUpdate -> OpeningBalanceResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/opening_balances.py` |
| GET | `/api/daily-logs` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | list daily logs | `page`/`page_size` (opt-in; max 200). Bare list by default; `{items,total,page,page_size,pages}` when either is given. Each log has optional `event_count` | List[DailyLogResponse] or DailyLogPage | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |
| GET | `/api/daily-logs/{log_id}` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | get daily log | path/query only -> DailyLogResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |
| POST | `/api/daily-logs` | JWT ADMIN,DATA_ENTRY | create daily log | DailyLogCreate -> DailyLogResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |
| POST | `/api/daily-logs/{log_id}/events` | JWT ADMIN | add event to daily log | EventCreate -> EventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |
| POST | `/api/daily-logs/{log_id}/lock` | JWT ADMIN,VIEWER | lock daily log | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |
| PUT | `/api/daily-logs/{log_id}` | JWT ADMIN | update daily log | DailyLogUpdate -> DailyLogResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |
| PUT | `/api/events/{event_id}` | JWT ADMIN,DATA_ENTRY | update event | EventUpdate -> EventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |
| DELETE | `/api/events/{event_id}` | JWT ADMIN | delete event | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/daily_logs.py` |

Animal-register sync (decision 0009): `POST /api/daily-logs` (events embedded; synced per event in order, `sync_warnings` on each returned event), `POST /api/daily-logs/{log_id}/events`, `PUT /api/events/{event_id}` and `DELETE /api/events/{event_id}` update/undo the individual animal register AFTER the stock commit, in separate best-effort transactions that never roll back stock. POST/PUT return skipped-tag messages in `EventResponse.sync_warnings` (optional list); DELETE returns `{message, sync_warnings}`. Birth events create temp-tag animals (`TEMP-<LOC>-<YYYYMMDD>-NNN`, `is_temp_tag=true`) for blank/`NEW`/`TEMP` offspring entries, or `count` of them when `offspring_tags` is blank; re-saving the event does not duplicate them (marker in `animals.notes`).

| GET | `/api/stock-levels` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | list stock levels | path/query only -> List[StockLevelResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/stock_levels.py` |
| POST | `/api/stock-levels/recompute` | JWT ADMIN | recompute stock levels endpoint | path/query only -> dict (no model) | Admin/manual; no frontend wrapper found | `backend/routers/stock_levels.py` |
| GET | `/api/dashboard` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | get dashboard | query: `location_id`, `period_days` (default 30), optional `date_from`/`date_to` (override `period_days` for herd performance and net changes; 400 if `date_to` < `date_from`) -> DashboardResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/dashboard.py` |
| GET | `/api/reports/daily` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | get daily report | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reports.py` |
| GET | `/api/reports/range` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | get range report | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reports.py` |
| GET | `/api/reports/analytics` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | get analytics report | path/query only -> AnalyticsResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reports.py` |
| GET | `/api/reports/detailed` | JWT ADMIN,DATA_ENTRY,VIEWER (closed 2026-11-08) | get detailed report | path/query only -> DetailedReportResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/reports.py` |
| GET | `/api/reports/calving` | JWT ADMIN,DATA_ENTRY,VIEWER | calving report: cycles with a calving date and outcome LIVE_CALF/STILLBIRTH/ASSISTED_LIVE/ASSISTED_DEAD; `summary{total,live,stillbirths,assisted}` + rows with active identifier tags for dam and calf | `location_id`, `species`, `date_from`, `date_to` (all optional) | CalvingReport | none yet | `backend/reports_router.py` |
| GET | `/api/reports/reproductive-status` | JWT ADMIN,DATA_ENTRY,VIEWER | females with their latest cycle (row_number window, created_at DESC); `summary.by_status` OPEN/SERVED/PREGNANT/CALVED/ABORTED/unknown | `location_id`, `species`, `status` (comma-separated cycle statuses, case-insensitive; 400 if invalid) | ReproStatusReport | none yet | `backend/reports_router.py` |
| GET | `/api/reports/abortions` | JWT ADMIN,DATA_ENTRY,VIEWER | cycles with status ABORTED, newest first; `abortion_date` is the cycle's `created_at` (record time, not event date); `summary.by_stage` | `location_id`, `species`, `date_from`, `date_to` (all optional) | AbortionReport | none yet | `backend/reports_router.py` |
| GET | `/api/templates/animals` | Public | download animals template | path/query only -> CSV StreamingResponse (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/animals.py` |
| GET | `/api/animals` | JWT active user | list animals (optional `is_temp_tag=true|false` filter; omitted = no filter); `AnimalResponse` includes read-only `last_calving_date` | `page`/`page_size` (opt-in; max 200) and `export=true`. Bare list by default and with `export=true`; `{items,total,page,page_size,pages}` when page/page_size is given | List[AnimalResponse] or AnimalPage | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/animals.py` |
| POST | `/api/animals` | JWT ADMIN,DATA_ENTRY | create animal | AnimalCreate -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/animals.py` |
| POST | `/api/animals/bulk-import` | JWT ADMIN | bulk import animals | UploadFile -> BulkImportResult | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/animals.py` |
| GET | `/api/animals/register-reconciliation` | JWT ADMIN,DATA_ENTRY,VIEWER | per location+species: stock_levels total vs registered active animals (`registered_pct` null when stock is 0; `unregistered` may be negative) | none -> List[ReconciliationRow] | Animals.jsx (Register completeness panel), Dashboard.jsx (Animal register card) | `backend/server.py` (register_reconciliation) |
| GET | `/api/animals/{animal_id}/location-history` | JWT ADMIN,DATA_ENTRY,VIEWER | animal move log, newest first; 404 if animal missing | path -> List[AnimalLocationHistoryResponse] | AnimalDetail.jsx (Movement history tab) | `backend/server.py` (get_animal_location_history) |
| GET | `/api/animals/{animal_id}` | JWT active user | get animal | path/query only -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/animals.py` |
| POST | `/api/animals/{animal_id}/replace-tag` | JWT ADMIN,DATA_ENTRY | replace a temporary tag with the real one: 404 missing, 400 animal has no temp tag / blank / same tag, 409 tag already used by that species at that location | ReplaceTagRequest `{new_tag_number}` -> ReplaceTagResponse `{message, old_tag, new_tag, animal_id}` | AnimalDetail.jsx (Replace tag dialog) | `backend/server.py` (replace_animal_tag) |
| PUT | `/api/animals/{animal_id}` | JWT ADMIN,DATA_ENTRY | update animal (a changed `location_id` also writes an `animal_location_history` row with no event_id; an unchanged one writes nothing) | AnimalUpdate -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/animals.py` |
| POST | `/api/animals/{animal_id}/transfer` | JWT ADMIN | transfer animal (also writes an `animal_location_history` row linked to the TRANSFER event it creates, same transaction) | AnimalTransfer -> AnimalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/animals.py` |
| GET | `/api/health-intervals` | JWT active user | list health intervals | path/query only -> List[HealthIntervalResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| POST | `/api/health-intervals` | JWT ADMIN | create health interval | HealthIntervalCreate -> HealthIntervalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| PUT | `/api/health-intervals/{interval_id}` | JWT ADMIN | update health interval | HealthIntervalUpdate -> HealthIntervalResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| DELETE | `/api/health-intervals/{interval_id}` | JWT ADMIN | delete health interval | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| GET | `/api/farm-health/last-events` | JWT active user | get last events | path/query only -> List[LastEventSummary] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| GET | `/api/farm-health/upcoming` | JWT active user | get upcoming health events | path/query only -> List[FarmHealthEventResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| GET | `/api/farm-health/product-suggestions` | JWT active user | get product suggestions | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| GET | `/api/farm-health` | JWT active user | list farm health events | path/query only -> List[FarmHealthEventResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| POST | `/api/farm-health` | JWT ADMIN,DATA_ENTRY | create farm health event | FarmHealthEventCreate -> FarmHealthEventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| GET | `/api/farm-health/{event_id}` | JWT active user | get farm health event | path/query only -> FarmHealthEventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| PUT | `/api/farm-health/{event_id}` | JWT ADMIN | update farm health event | FarmHealthEventUpdate -> FarmHealthEventResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| DELETE | `/api/farm-health/{event_id}` | JWT ADMIN | delete farm health event | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/farm_health.py` |
| GET | `/api/vaccine-types` | JWT active user | list vaccine types | path/query only -> List[VaccineTypeResponse] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/vaccine_types.py` |
| POST | `/api/vaccine-types` | JWT ADMIN | create vaccine type | VaccineTypeCreate -> VaccineTypeResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/vaccine_types.py` |
| PUT | `/api/vaccine-types/{vt_id}` | JWT ADMIN | update vaccine type | VaccineTypeUpdate -> VaccineTypeResponse | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/vaccine_types.py` |
| DELETE | `/api/vaccine-types/{vt_id}` | JWT ADMIN | delete vaccine type | path/query only -> dict (no model) | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/vaccine_types.py` |
| GET | `/api/farm-health-events/last-vaccinations` | JWT active user | get last vaccinations | path/query only -> List[LastVaccinationSummary] | Shamba UI via frontend/src/lib/api.js:5 | `backend/routers/vaccine_types.py` |

## Reproduction and animal-profile routes (added 2026-11-08)
All in `backend/server.py` (block "REPRODUCTION & ANIMAL PROFILE", registered before `app.include_router`). Reads: JWT ADMIN/DATA_ENTRY/VIEWER. Writes: ADMIN/DATA_ENTRY. Deletes: ADMIN. Behaviour notes live in the handlers' docstrings and docs/decisions/0008.

| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/bull-assignments` | filters `location_id`, `active_only`; POST needs a MALE bull (400), existing location (404), unique (bull, location, date) else 409 |
| PUT/DELETE | `/api/bull-assignments/{id}` | DELETE returns 409 while reproductive cycles reference it |
| GET/POST | `/api/reproductive-cycles` | filters `animal_id`, `location_id`, `status`, `date_from`, `date_to` (first set date of the cycle); POST needs a FEMALE animal (400/404), assigns `cycle_number`, computes expected calving (+283 d) and intervals |
| GET/PUT/DELETE | `/api/reproductive-cycles/{id}` | PUT recomputes expected date/intervals (and following cycles); explicit null clears nullable fields |
| GET | `/api/animals/{id}/reproductive-history` | cycles + `total_calvings`, `avg_interval_days`, `last_calving_date`, `current_status` |
| GET/POST | `/api/bcs-records` | filters `animal_id`, `location_id`, `date_from`, `date_to`; bcs validated 1.0-5.0 (422) |
| PUT/DELETE | `/api/bcs-records/{id}` | |
| GET/POST | `/api/animals/{id}/photos` | GET: signed 1 h URLs, `photo_url=null` + `warning` when GCS is not configured; POST multipart (`file`, `caption`, `taken_date`): jpeg/png/webp, 10 MB, content sniffed; 503 without `GCS_BUCKET_NAME` |
| PUT/DELETE | `/api/animals/{id}/photos/{photo_id}` | PUT may set `is_primary` (unsets the others); DELETE removes the object first, 502 and keeps the row if storage fails |
| GET/POST | `/api/animals/{id}/notes` | newest first |
| PUT/DELETE | `/api/animals/{id}/notes/{note_id}` | |
| GET | `/api/animals/{id}/timeline` | merged reproduction milestones, matching farm-health events, BCS and notes, newest first |
| GET | `/api/analytics/reproduction` | filters `location_id`, optional `species` (cattle|sheep|goat; 422 otherwise), `year`, or `date_from`+`date_to` together (override `year`; Koo count is taken at `date_from`; 400 if only one is given or reversed); rates are 0-1 fractions; Koo = `categories.name_sw == 'Koo'`. Since 2026-11-20 `live_calvings` = daily-log BIRTH event offspring counts in range + cycle live calvings not already covered by a linked birth event (same animal and date); `conception_rate` combines PD_TEST event counts and cycle PD results the same way; `pregnant_cows`/`open_cows` use `animals.reproductive_status` (cycles only for animals still `unknown`) |

## Frontend pages using these routes (added 2026-11-08)
- `/reproduction` (`frontend/src/pages/Reproduction.jsx`, all roles; write actions need admin/data_entry, bull assignment admin only): KPI cards (`GET /api/analytics/reproduction`, with `species` when one is selected; the browser no longer computes KPIs), needs-attention list, upcoming and recent births, bull assignments. Uses `GET/POST/PUT /api/reproductive-cycles`, `GET/POST/PUT /api/bull-assignments`, `GET/POST /api/bcs-records`, `GET /api/animals`, `/api/opening-balances`, `/api/stock-levels`.
- Shared dialogs `frontend/src/components/ReproductionDialogs.jsx` (service, PD check, calving/lambing/kidding, BCS). The animal detail page is `/animals/:id` (below).
- Client wrappers appended to `frontend/src/lib/api.js`: `getReproductionAnalytics`, `getReproductiveCycles`, `getReproductiveCycle`, `createReproductiveCycle`, `updateReproductiveCycle`, `getBullAssignments`, `createBullAssignment`, `updateBullAssignment`, `getBCSRecords`, `createBCSRecord`, `searchAnimals`.
- `/animals/:id` (`frontend/src/pages/AnimalDetail.jsx`, all roles read; admin/data_entry write; admin deletes and Transfer): animal profile. Calls `GET /api/animals/{id}`, `GET/POST /api/animals/{id}/photos`, `PUT/DELETE /api/animals/{id}/photos/{photo_id}`, `GET /api/animals/{id}/timeline`, `GET /api/animals/{id}/reproductive-history`, `GET /api/bcs-records?animal_id=`, `GET/POST /api/animals/{id}/notes`, `PUT/DELETE /api/animals/{id}/notes/{note_id}`. Reuses the dialogs in `ReproductionDialogs.jsx` (service, PD, calving, BCS). Photos: client checks jpeg/png/webp and 10 MB; shows the backend `warning` when GCS is not configured; admin/data_entry can set the primary photo (PUT `is_primary`).
- `frontend/src/pages/Animals.jsx`: rows now navigate to `/animals/:id` (the old detail Sheet is no longer reachable). The page also honours `?edit=ID` and `?transfer=ID`, opening the existing Edit/Transfer dialogs, then returns to that profile when the dialog closes.
- Client wrappers appended to `frontend/src/lib/api.js`: `getAnimalDetail`, `getAnimalTimeline`, `getAnimalReproductiveHistory`, `getAnimalPhotos`, `uploadAnimalPhoto`, `updateAnimalPhoto`, `deleteAnimalPhoto`, `getAnimalNotes`, `createAnimalNote`, `updateAnimalNote`, `deleteAnimalNote`, `getAnimalBCSHistory`.
- `GET /api/animals` has no `sex` filter: the page filters female/male client-side.
- Species-aware UI constants (gestation days, terminology, interval thresholds) live in `ReproductionDialogs.jsx` and are keyed by the API species values `cattle`/`sheep`/`goat`. The backend still defaults expected calving to 283 days for every species (K23); the UI always sends the date explicitly.

## Schema and auth lookup

- Pydantic contracts: `backend/schemas/`; enum values: `backend/models.py:9`. Request models with optional fields do not necessarily support clearing fields; handlers commonly ignore None.
- Active-user verification and role factory: `backend/auth.py:37`, `backend/auth.py:67`.
- Resolved 2026-11-08: unauthenticated business reads were closed (see the note at the top). Remaining public routes: health, login, three CSV templates.
- Low: generated API/client comments can lag actual roles: add-event is ADMIN, update-event allows ADMIN/DATA_ENTRY, lock allows ADMIN/VIEWER (`backend/server.py:1071`, `backend/server.py:1266`, `backend/server.py:1179`).

## Reproductive status board (2026-11-10)
`GET /api/reproduction/status-board?farm_id=<location-id>&species=cattle|sheep|goat` is available to ADMIN, DATA_ENTRY and VIEWER. No database writes or schema changes. Only active female animals are included.

Response: `summary {total_breeding_females, status_known_pct}` plus nine `{label, count, animals}` buckets: `open`, `pregnant`, `close_to_calving`, `due_this_month`, `recently_calved`, `recently_aborted`, `repeat_breeders`, `unknown_status`, `needs_attention`. Animal rows expose `id`, `tag_number`, `species`, `category`, `farm`, `age_months`, `reproductive_status`, `last_event_date`, `last_event_type`, `last_pd_date`, `last_calving_date`, `months_pregnant`, `services_without_conception`, `expected_calving_date`.

Both due buckets use the inclusive interval today through today + 30 days. Estimate = last PD date + species gestation days - months pregnant * 30, only for pregnant animals with both inputs. Gestations: cattle 283, sheep 147, goats 150. Recent calving/abortion windows are inclusive today - 30 through today. Future events are excluded from recent history. Needs attention includes breeding-age unknown status, pregnant with PD strictly older than 180 days, or >= 3 services. Unknown status holds younger females or those without a birth date. Breeding ages: cattle 24 months, sheep/goats 18; completed calendar months. Summary percentage considers only breeding-age females, returns 0 for no denominator. Dates use UTC+03:00. Buckets overlap, and repeated abortions never duplicate an animal in a bucket.

### Category transitions (added 2026-11-10)
| Method | Path | Auth | Purpose | Source |
|---|---|---|---|---|
| GET | `/api/admin/transition-rules` | JWT ADMIN,DATA_ENTRY,VIEWER | list rules with category names | `backend/server.py` (list_transition_rules) |
| PUT | `/api/admin/transition-rules/{rule_id}` | JWT ADMIN | edit age / target categories / is_active (400 on wrong species, age on an event rule) | update_transition_rule |
| POST | `/api/admin/tasks/sync-category-transitions` | JWT ADMIN | same pending queue as below; no writes | sync_category_transitions |
| GET | `/api/animals/transition-queue` | JWT ADMIN,DATA_ENTRY,VIEWER | active animals past an age rule's threshold (`species`, `location_id` filters); no writes. Declared above `/animals/{animal_id}` on purpose | get_transition_queue |
| POST | `/api/animals/{animal_id}/confirm-transition` | JWT ADMIN,DATA_ENTRY | `{to_category_id, notes?}`: changes the category and moves 1 head of `stock_levels` in one transaction. 400 not active / same category / wrong species; 409 source stock is 0 | confirm_transition |
| POST | `/api/animals/bulk-confirm-transitions` | JWT ADMIN,DATA_ENTRY | per-animal result, partial success persists | bulk_confirm_transitions |
| GET | `/api/animals/{animal_id}/transition-history` | JWT ADMIN,DATA_ENTRY,VIEWER | audit rows, newest first | get_transition_history |
Also: recording a `calving` reproductive event (`POST /api/animals/{id}/reproductive-events`) auto-confirms the first-calving rule (Mitamba -> Koo). Best-effort: if it fails (e.g. stock 0) the calving still saves and a warning is logged.

### Daily-log reproduction and animal feed (2026-11-10)
Daily event create/update accepts `pd_test` and `service`. PD tests require
`pd_result` (`pregnant` or `open`), with optional integer `months_pregnant` (0–12).
PD tests, services and abortions are non-stock events. Open PD clears months.
`GET /api/animals/{animal_id}/daily-log-timeline` is available to all authenticated
roles: `from_date`, `to_date`, `event_type`, `page` (default 1), `page_size`
(default 20, maximum 100). Returns `{items,total,page,page_size}`; items contain
`event_id,event_type,event_date,event_type_label,daily_log_id,farm_name,notes,
quantity,result,recorded_by_name`. Newest date/id first; invalid date ranges are
400, missing animals 404. The existing `/timeline` route is unchanged.
See [daily reproduction operations](../DAILY_REPRODUCTIVE_SYNC.md).

### Animal tag search
`GET /api/animals?search=...` matches primary tags, legacy registry IDs, names, and active identifiers of every type. Matching is case-insensitive and supports partial values. Animal list responses include `search_tags` for the register and shared pickers. Exact reproductive tag resolution checks these same tags and rejects ambiguous matches. No database schema change is required.
