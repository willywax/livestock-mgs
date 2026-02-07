from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

def normalize_database_url(raw_url: str) -> str:
    if not raw_url:
        return raw_url

    if raw_url.startswith("postgres://"):
        raw_url = "postgresql://" + raw_url[len("postgres://"):]

    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(raw_url)
    if parsed.scheme.startswith("postgresql+asyncpg"):
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        # asyncpg does not understand libpq-specific options
        query.pop("channel_binding", None)
        if "sslmode" in query and "ssl" not in query:
            query["ssl"] = "require" if query["sslmode"] == "require" else query["sslmode"]
        query.pop("sslmode", None)
        parsed = parsed._replace(query=urlencode(query))
        return urlunparse(parsed)

    return raw_url


# Use PostgreSQL with asyncpg for async support
DATABASE_URL = normalize_database_url(
    os.environ.get(
        'DATABASE_URL',
        'postgresql+asyncpg://postgres:postgres@localhost:5432/shamba_manager'
    )
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
