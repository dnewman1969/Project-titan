#!/usr/bin/env python3
"""Seed games, personas, and default teams into the configured Postgres database (M2.T4)."""

from __future__ import annotations

import argparse
import asyncio

from titan_core.config import load_config
from titan_db import migrate
from titan_db.seed import seed_all
from titan_db.session import create_engine, create_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="store_true", help="run alembic upgrade head before seeding")
    args = parser.parse_args()
    cfg = load_config(user_config=False)
    url = migrate.database_url(cfg.postgres)
    if args.migrate:
        migrate.upgrade(url, "head")
    engine = create_engine(cfg.postgres)
    factory = create_session_factory(engine)

    async def _run() -> dict[str, int]:
        try:
            return await seed_all(factory)
        finally:
            await engine.dispose()

    counts = asyncio.run(_run())
    print(f"Seeded: {counts['personas']} personas, {counts['games']} games, {counts['teams']} teams")


if __name__ == "__main__":
    main()
