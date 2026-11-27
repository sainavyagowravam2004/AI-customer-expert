"""Procrastinate application.

Start the worker with::

    procrastinate --app=app.worker.app worker

Running this module directly (``python -m app.worker``) applies the
Procrastinate schema when ``procrastinate_jobs`` is missing. The image
entrypoint does that before the worker command on a fresh database.
"""

from __future__ import annotations

import asyncio
import logging

import psycopg
from procrastinate import App, PsycopgConnector

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

app = App(
    connector=PsycopgConnector(
        conninfo=settings.procrastinate_dsn,
        kwargs={},
    ),
)


async def ensure_schema() -> None:
    """Create Procrastinate tables when this database does not have them yet."""
    async with await psycopg.AsyncConnection.connect(settings.procrastinate_dsn) as connection:
        cursor = await connection.execute("SELECT to_regclass('public.procrastinate_jobs')")
        row = await cursor.fetchone()

    if row is not None and row[0] is not None:
        logger.info("Procrastinate schema already present")
        return

    logger.info("Applying Procrastinate schema")
    async with app.open_async():
        await app.schema_manager.apply_schema_async()
    logger.info("Procrastinate schema applied")


def main() -> None:
    """Apply the background-job schema and exit."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(ensure_schema())


if __name__ == "__main__":
    main()
