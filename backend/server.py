"""ShambaManager API entrypoint (`uvicorn server:app`).

Only app wiring lives here: env, CORS, startup/shutdown, router registration. Business logic is in
`routers/` (HTTP endpoints, one module per domain) and `services/` (shared helpers: stock accounting,
animal-register sync, transitions). See docs/context/codemap.md for the task -> file map.
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from bootstrap import run_startup
from database import engine
from reports_router import reports_router
from routers import ROUTERS

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_CORS_ORIGINS = [
    "https://stocks.serengeti-ranching.com",
    "https://serengeti-ranching.com",
]


def parse_cors_origins(raw_origins: Optional[str]) -> List[str]:
    if not raw_origins:
        return list(DEFAULT_CORS_ORIGINS)
    origins = [
        origin.strip().strip('"').strip("'")
        for origin in raw_origins.split(',')
        if origin.strip().strip('"').strip("'")
    ]
    return origins or list(DEFAULT_CORS_ORIGINS)


app = FastAPI(title="ShambaManager API", version="1.0.0")

allowed_origins = parse_cors_origins(os.environ.get('CORS_ORIGINS'))
logger.info("CORS allowed origins: %s", allowed_origins)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await run_startup()


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()


# All JSON routes live under /api. Order of ROUTERS matters (see routers/__init__.py).
api_router = APIRouter(prefix="/api")
for _router in ROUTERS:
    api_router.include_router(_router)
app.include_router(api_router)
# Read-only reproduction reports (calving, reproductive-status, abortions); paths must not
# collide with any /api/reports/* route in routers/reports.py, sales.py or mortality.py.
app.include_router(reports_router)
