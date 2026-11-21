"""Startup seed helpers that run raw SQL."""
from sqlalchemy import text

async def _seed_death_causes(connection):
    for order, name in enumerate(("Disease", "Predation", "Accident", "Starvation/Drought",
                                  "Dystocia", "Unknown", "Other")):
        await connection.execute(text(
            "INSERT INTO death_causes (name, is_active, sort_order) VALUES (:name, true, :sort_order) "
            "ON CONFLICT (name) DO NOTHING"
        ), {"name": name, "sort_order": order})
