"""After add_daily_reproductive_sync.sql: preview exact historical links, or persist with --apply.

Run from repository root with DATABASE_URL and JWT_SECRET supplied in the environment:
    python backend/migrations/backfill_daily_event_links.py [--apply]
Does not start the server, replay historical reproductive changes, or change stock.
Ambiguous/missing historical tags remain unresolved rather than being guessed.
"""
import argparse
import asyncio
import os
from pathlib import Path
import sys


async def main(apply):
    if not os.environ.get('DATABASE_URL') or not os.environ.get('JWT_SECRET'):
        raise SystemExit('Set DATABASE_URL and JWT_SECRET explicitly before running this migration.')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy.ext.asyncio import AsyncSession
    from database import engine
    from server import _backfill_daily_event_links
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            print('APPLY' if apply else 'DRY RUN', await _backfill_daily_event_links(db, apply=apply))
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(main(parser.parse_args().apply))
