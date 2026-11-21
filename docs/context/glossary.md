# ShambaManager glossary

> **2026-11-21:** `backend/server.py` and `backend/models.py` were split (decision 0012). File and line anchors below that cite `backend/server.py:NNN` or `backend/models.py:NNN` describe the pre-split files (git `5ddbe1b`); find the current location in [backend-map.md](backend-map.md).

> **Updated 2026-11-08:** the Herd Tag Registry integration was removed from the application (docs/decisions/0007). Content below was trimmed accordingly; line numbers are from the 2026-10-08 snapshot and have shifted. Treat anything still mentioning the Registry as historical.

Meanings below come from code labels/seed translations, not a veterinary taxonomy. The Registry-specific terms were removed with the integration.
| Term | Meaning in this code | Where used |
|---|---|---|
| KOO / Koo | Cows for cattle; does/ewes for goats/sheep; breeding-female aggregate | `backend/seed_data.py:6`, `:19`; `backend/server.py:2032` |
| MITAMBA / Mitamba | Heifers; seed also uses this English label for small stock | `backend/seed_data.py:7`, `:20` |
| ACHISHWA | Weaners; local categories split Dume/Jike | `backend/seed_data.py:10`, `:23` |
| NDAMA | Cattle calves; Ndama Dume bull calves, Ndama Jike heifer calves | `backend/seed_data.py:8` |
| VICHINDA | Kids/lambs, split Dume/Jike locally | `backend/seed_data.py:21` |
| MAKSAI / Maksai | Steers or castrated small-stock males | `backend/seed_data.py:12`, `:26` |
| MBEGU / Dume Mbegu | Breeding males; local seed name is Dume Mbegu | `backend/seed_data.py:13`, `:25` |
| Dume Wadogo | Young males category; separate from breeding males | `backend/seed_data.py:14`, `:27` |
| JIKE / DUME | Female / male in category suffixes; local AnimalSex uses female/male | `backend/models.py:113`; `backend/seed_data.py:8` |
| tag_number | Local individual-animal tag, unique only within species/location | `backend/models.py:217`, `:240` |
| registry_tag_id | Inert legacy column on animals (nullable, indexed). Echoed in AnimalResponse; no code writes it | `backend/models.py` (Animal) |
| animal_tags / offspring_tags | Comma-separated event references, not normalized membership tables | `backend/models.py:159`, `:172` |
| Status | Local AnimalStatus active/sold/dead/transferred/missing | `backend/models.py` (AnimalStatus) |
| Opening balance | Stock starting count by location/species/category/period | `backend/models.py:68` |
| Daily log | One location/date container for events, optionally locked | `backend/models.py:87` |
| Stock event | Event whose count affects aggregate inventory; distinct from individual animal mutation | `backend/models.py:156`; `backend/server.py:2655` |
| Dipping | Farm-health treatment type with configurable interval; chemical rotation not modeled | `backend/models.py:243`, `:254` |


