# Domain rules and glossary
Counts-based livestock inventory for a Tanzanian ranch: species cattle, sheep, goat; several farm locations; categories shown in Swahili. Sources: `memory/PRD.md` (historical, validate), `backend/seed_data.py`, `backend/models.py`. Fuller glossary: [context/glossary.md](context/glossary.md).

## Rules
- Animals are tracked as COUNTS per location + species + category; individual animals are an optional separate register.
- Events: birth, death, sold, missing, gift in/out, bought, transfer, category change, abortion (early/mid/late), weaning.
- Opening balances per period seed the counts; daily logs may be "no events" and can be locked.
- Negative stock is blocked for non-admins; admin may override (from PRD; exact enforcement Unverified).
- Roles: admin (everything), data_entry (create logs/events/animals), viewer (read).
- Farm health: dipping, deworming, vaccination with configurable intervals and overdue/upcoming views. Rotation of chemicals and outbound notifications are not implemented.
- Tag identity is local free text (animal tags on events, `animals.tag_number`). The external Registry integration was removed.

## Glossary
| Term | Meaning |
|---|---|
| Shamba | farm |
| Koo | breeding females (cows; does/ewes) |
| Mitamba | heifers (label reused for small stock) |
| Achishwa | weaners |
| Ndama (Dume/Jike) | calves (bull/heifer) |
| Vichinda | kids/lambs |
| Maksai | steers / castrated males |
| Mbegu / Dume Mbegu | breeding males |
| Dume Wadogo | young males |
| Dume / Jike | male / female |
| EPC | RFID electronic product code |

## Reproductive status board
The board covers active registered females, with overlapping categories rather than a partition. The revised requirements define both close-to-calving and due-this-month as the next 30 days; recently aborted also uses 30 days. Estimated dates use recorded pregnancy months at the last PD test, not the animal's current age. Unknown age remains in unknown status unless another attention rule applies. Breeding-age unknown females, stale pregnancy PD (>180 days), and repeat breeders (>=3 services) need attention. Failed-service rows are amber at 3–4 and red at 5+. See context/api.md for exact boundaries.

## Category transitions
- Animals move up a category chain by age (7 and 18 months by default, editable per rule) or on first calving. The queue only lists animals; staff confirm each move.
- Confirming changes `animals.category_id` and moves one head between `stock_levels` rows in the same transaction. It writes no daily-log event, so do NOT also log a `category_change` event for the same move or stock moves twice.
- Needs a birth date for age rules. Source stock must be at least 1 at the animal's location, otherwise the confirm is refused (409) rather than driving stock negative.
- First calving only fires for a female whose current category is the rule's source (Mitamba) and who has no earlier `first_calving` transition.
- UI: Animals > Transition Queue (`/animals/transitions`, admin and data entry) lists due animals per rule with a farm/species filter; selecting rows and confirming calls the bulk-confirm route. Thresholds are edited by an admin in Settings > Category Transition Rules. An animal's profile shows its last category changes under "Category history".
