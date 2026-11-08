# ShambaManager glossary
Meanings below come from code labels/seed translations, not a veterinary taxonomy. Registry terms are cross-references to the sibling repo.
| Term | Meaning in this code | Where used |
|---|---|---|
| KOO / Koo | Cows for cattle; does/ewes for goats/sheep; breeding-female aggregate | `backend/seed_data.py:6`, `:19`; `backend/server.py:2032` |
| MITAMBA / Mitamba | Heifers; seed also uses this English label for small stock | `backend/seed_data.py:7`, `:20` |
| ACHISHWA | Weaners; local categories split Dume/Jike, Registry groups them | `backend/seed_data.py:10`, `:23`; `backend/registry_client.py:36` |
| NDAMA | Cattle calves; Ndama Dume bull calves, Ndama Jike heifer calves | `backend/seed_data.py:8`; `backend/registry_client.py:39` |
| VICHINDA | Kids/lambs, split Dume/Jike locally | `backend/seed_data.py:21`; `backend/registry_client.py:41` |
| MAKSAI / Maksai | Steers or castrated small-stock males | `backend/seed_data.py:12`, `:26` |
| MBEGU / Dume Mbegu | Breeding males; Registry spells category MBEGU, local seed Dume Mbegu | `backend/seed_data.py:13`, `:25`; sibling `tags-src/backend/app/scripts/seed_initial.py:22` |
| Dume Wadogo | Young males category; separate from breeding males | `backend/seed_data.py:14`, `:27` |
| JIKE / DUME | Female / male in Registry and category suffixes; local AnimalSex uses female/male | `backend/models.py:113`; `backend/seed_data.py:8` |
| PRE-COHORT | Registry UI label for NULL generated cohort; no Shamba cohort field | Sibling `tags-src/frontend/src/pages/HerdPage.tsx:268`; local `backend/models.py:212` |
| birth_cohort | Registry DOB year plus H1 (Jan-Jun) or H2 (Jul-Dec); not a status | Sibling `tags-src/backend/app/models/animal.py:54` |
| production_stage | Registry's separate production-planning dimension; absent in Shamba | Sibling `tags-src/backend/app/models/animal.py:53`; local `backend/models.py:212` |
| EPC | Electronic Product Code/RFID identifier; Registry import recognizes EPC column names | Sibling `tags-src/frontend/src/utils/excel.ts:23`; local picker `frontend/src/components/RegistryTagPicker.jsx:17` |
| Tag ID / tag_id | Canonical Registry string; outbox tag_id references it without cross-DB FK | `backend/models.py:343`; `backend/registry_client.py:236` |
| tag_number | Local individual-animal tag, unique only within species/location | `backend/models.py:217`, `:240` |
| registry_tag_id | Nullable local link to Registry; indexed but not unique | `backend/models.py:231`; `backend/server.py:3280` |
| animal_tags / offspring_tags | Comma-separated event references, not normalized membership tables | `backend/models.py:159`, `:172` |
| Status | Local AnimalStatus active/sold/dead/transferred/missing; Registry vocabulary differs | `backend/models.py:122`; `backend/registry_sync.py:26` |
| Opening balance | Stock starting count by location/species/category/period | `backend/models.py:68` |
| Daily log | One location/date container for events, optionally locked | `backend/models.py:87` |
| Stock event | Event whose count affects aggregate inventory; distinct from individual animal mutation | `backend/models.py:156`; `backend/server.py:2655` |
| Outbox / drain | Durable queued Registry intent / service-authenticated batch delivery | `backend/models.py:332`; `backend/registry_sync.py:111` |
| Reconciliation | Local status-intent versus Registry terminal-status feed; not identity delta sync | `backend/registry_report.py:56` |
| Dipping | Farm-health treatment type with configurable interval; chemical rotation not modeled | `backend/models.py:243`, `:254` |

High: CALVED is Shamba's wire action for birth; Registry's calving update recognizes BIRTH (`backend/registry_sync.py:212`; sibling `tags-src/backend/app/routers/integration.py:253`).
Medium: aliases collapse category sex but do not map DUME MBEGU to MBEGU; do not assume all domain words are interchangeable (`backend/registry_client.py:36`).

