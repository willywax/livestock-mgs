"""HTTP routers, one module per domain. Each module exposes `router = APIRouter()`.

Registration order matters: FastAPI matches the first route that fits, so routers that own static
paths (e.g. `/animals/transition-queue` in `transitions`) must come before routers that own a
dynamic sibling (`/animals/{animal_id}` in `animals`). Add new routers to ROUTERS below.
`reports_router` (reports_router.py at the backend root) is included separately by server.py.
"""
from routers import (
    animal_identifiers, animal_notes, animal_photos, animal_timeline, animals, auth, bcs_records,
    bull_assignments, daily_logs, dashboard, farm_health, imports, locations, mortality,
    opening_balances, pd_import, reconciliation, reference_data, reports, reproduction_analytics,
    reproductive_cycles, reproductive_events, sales, status_board, stock_levels, system,
    transitions, vaccine_types,
)

ROUTERS = [
    system.router,
    auth.router,
    locations.router,
    imports.router,
    reference_data.router,
    opening_balances.router,
    daily_logs.router,
    stock_levels.router,
    dashboard.router,
    reports.router,
    transitions.router,  # before animals: static /animals/transition-queue vs /animals/{animal_id}
    animals.router,
    farm_health.router,
    vaccine_types.router,
    bull_assignments.router,
    reproductive_cycles.router,
    bcs_records.router,
    animal_photos.router,
    animal_notes.router,
    animal_identifiers.router,
    animal_timeline.router,
    reproduction_analytics.router,
    reproductive_events.router,
    reconciliation.router,
    pd_import.router,
    sales.router,
    mortality.router,
    status_board.router,
]
