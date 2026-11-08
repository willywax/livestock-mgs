# 0001 Track stock as counts, individuals optional
Status: accepted (evident from code and memory/PRD.md; date Unverified). Stock is per location+species+category driven by events and opening balances (backend/models.py, backend/server.py). The animals table is a separate register. Consequence: birth events do not create animals; stock_levels is a projection that can be recomputed.
