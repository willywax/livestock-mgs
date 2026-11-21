"""Startup work: additive DDL on top of create_all, then seed data.

Runs on every process start (see server.py). Rules from CLAUDE.md apply: only nullable
`ADD COLUMN IF NOT EXISTS` / `ADD VALUE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` statements here;
create_all() never migrates existing tables. Never run this against a real DB just to "inspect".
"""
import logging

from sqlalchemy import func, select, text

from database import Base, engine, get_db
from models import Category, User, VaccineType
from seed_data import get_default_admin, get_seed_categories
from services.seed import _seed_death_causes
from services.transitions import _seed_category_transition_rules

logger = logging.getLogger(__name__)


async def apply_additive_ddl() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # PostgreSQL stores enum member names, not their lowercase API values.
        await conn.execute(text("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'PD_TEST'"))
        await conn.execute(text("ALTER TYPE eventtype ADD VALUE IF NOT EXISTS 'SERVICE'"))
        await conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS pd_result VARCHAR(20)"))
        await conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS months_pregnant INTEGER"))
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS "
            "cause_of_death_id INTEGER REFERENCES death_causes(id)"
        ))
        await _seed_death_causes(conn)
        # Add vaccine_type_id to farm_health_events if not already present.
        # IF NOT EXISTS makes this idempotent on every restart.
        await conn.execute(text(
            "ALTER TABLE farm_health_events "
            "ADD COLUMN IF NOT EXISTS vaccine_type_id INTEGER "
            "REFERENCES vaccine_types(id)"
        ))
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS gift_party_name VARCHAR(255)"
        ))
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS gift_party_phone VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS gift_reason TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE animals ADD COLUMN IF NOT EXISTS registry_tag_id VARCHAR(100)"
        ))
        # Temporary tags for untagged newborns (nullable column with default: additive only).
        await conn.execute(text(
            "ALTER TABLE animals ADD COLUMN IF NOT EXISTS is_temp_tag BOOLEAN DEFAULT FALSE"
        ))
        # create_all() does not add columns to existing tables.
        for definition in (
            "reproductive_status VARCHAR(20) DEFAULT 'unknown'",
            "last_calving_date DATE",
            "last_pd_date DATE",
            "months_pregnant INTEGER",
            "services_without_conception INTEGER DEFAULT 0",
            "lifetime_calvings INTEGER",
        ):
            await conn.execute(text(f"ALTER TABLE animals ADD COLUMN IF NOT EXISTS {definition}"))
        # create_all() does not add indexes to existing tables.
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_animals_registry_tag_id ON animals (registry_tag_id)"
        ))


async def seed_initial_data() -> None:
    # Seed initial data
    async for db in get_db():
        # Check if categories exist
        result = await db.execute(select(func.count(Category.id)))
        count = result.scalar()
        if count == 0:
            categories = get_seed_categories()
            db.add_all(categories)
            await db.commit()
            logger.info("Seeded categories")

        # Check if admin exists
        result = await db.execute(select(func.count(User.id)))
        count = result.scalar()
        if count == 0:
            admin = get_default_admin()
            db.add(admin)
            await db.commit()
            logger.info("Created default admin user")

        # Seed vaccine types if table is empty
        vt_count_result = await db.execute(select(func.count(VaccineType.id)))
        if vt_count_result.scalar() == 0:
            seed_vaccines = [
                VaccineType(name="FMD",               species_applicability=["CATTLE", "GOAT"],            default_interval_days=180),
                VaccineType(name="Blackleg",           species_applicability=["CATTLE"],                    default_interval_days=365),
                VaccineType(name="Anthrax",            species_applicability=["CATTLE", "SHEEP", "GOAT"],   default_interval_days=365),
                VaccineType(name="Brucellosis",        species_applicability=["CATTLE", "SHEEP", "GOAT"],   default_interval_days=None),
                VaccineType(name="CBPP",               species_applicability=["CATTLE"],                    default_interval_days=365),
                VaccineType(name="PPR",                species_applicability=["SHEEP", "GOAT"],             default_interval_days=1095),
                VaccineType(name="Lumpy Skin Disease", species_applicability=["CATTLE"],                    default_interval_days=365),
                VaccineType(name="ECF",                species_applicability=["CATTLE"],                    default_interval_days=None),
            ]
            db.add_all(seed_vaccines)
            await db.commit()
            logger.info("Seeded vaccine types")

        try:
            added = await _seed_category_transition_rules(db)
            if added:
                logger.info("Seeded %d category transition rules", added)
        except Exception:
            await db.rollback()
            logger.exception("Category transition rule seeding failed")

        break


async def run_startup() -> None:
    await apply_additive_ddl()
    await seed_initial_data()
