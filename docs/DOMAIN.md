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
