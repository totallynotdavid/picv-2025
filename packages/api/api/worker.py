import asyncio
import logging
import os
import signal
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import numba
from rqueue import Admin, Worker

from api.core import db
from api.core.queue import build_queue
from api.core.settings import (
    COMPUTE_PURGER_PASSWORD,
    COMPUTE_PURGER_ROLE,
    COMPUTE_QUEUE,
    COMPUTE_QUEUE_SCHEMA,
    COMPUTE_WORKER_PASSWORD,
    COMPUTE_WORKER_ROLE,
    LOG_LEVEL,
    NUMBA_THREADS,
    WORKER_CONCURRENCY,
    WORKER_ID,
    WORKER_LEASE_SECONDS,
    worker_pool_size,
)
from api.core.tasks import (
    register_tasks,
    run_periodic_purge,
    run_periodic_reconcile,
    run_periodic_sweep,
)

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def worker_id() -> str:
    """Name this worker so its heartbeats and leases are attributable."""
    if WORKER_ID:
        return WORKER_ID
    # rqueue restricts a worker id to letters, digits, '_', '.', ':' and '-'.
    host = "".join(
        c if c.isalnum() or c in "_.-" else "-" for c in socket.gethostname()
    )
    return f"tsdhn-worker-{host or 'unknown'}-{os.getpid()}"[:128]


@asynccontextmanager
async def purge_pool() -> AsyncIterator[asyncpg.Pool]:
    """Yield the pool used by retention, separately credentialed from consume.

    When the purger role is not configured, retain the same development
    fallback as ``db.open_pool``: a separate owner-DSN pool. Reusing the worker
    pool here would use the CONSUME role, which intentionally cannot delete
    queue jobs.
    """
    dsn = db.runtime_dsn(COMPUTE_PURGER_ROLE, COMPUTE_PURGER_PASSWORD)
    fallback_dsn = dsn or db.COMPUTE_DATABASE_URL
    # Retention is hourly, so one lazy connection is enough. It is always a
    # separate pool, including the owner fallback above.
    pool = await asyncpg.create_pool(
        fallback_dsn, min_size=0, max_size=1, timeout=db.CONNECT_TIMEOUT
    )
    try:
        yield pool
    finally:
        await pool.close()


async def run() -> None:
    min_size, max_size = worker_pool_size()
    pool = await db.open_pool(
        min_size=min_size,
        max_size=max_size,
        dsn=db.runtime_dsn(COMPUTE_WORKER_ROLE, COMPUTE_WORKER_PASSWORD),
    )
    try:
        worker = Worker(
            register_tasks(build_queue(pool)),
            worker_id=worker_id(),
            concurrency=WORKER_CONCURRENCY,
            lease_duration=WORKER_LEASE_SECONDS,
        )

        loop = asyncio.get_running_loop()
        for received in (signal.SIGTERM, signal.SIGINT):
            # stop() stops claiming and gives in-flight work a bounded grace
            # period (rqueue's shutdown_timeout, 30s by default). A simulation
            # runs for tens of minutes, so in practice it does not finish:
            # rqueue cancels it and hands the lease straight back as `pending`
            # rather than leaving it to expire, and the next worker picks it up
            # and resumes from the checkpoints in its work directory.
            #
            # The lease is handed back on time. The *process* is not: rqueue's
            # bounded default executor shuts down with wait=True, so run() does
            # not return until the cancelled kernel thread finishes on its own.
            # That is an rqueue defect, filed there rather than worked around
            # here; in practice the orchestrator's own SIGKILL bounds it.
            loop.add_signal_handler(received, worker.stop)

        stop_maintenance = asyncio.Event()
        logger.info("simulation worker serving queue %s", COMPUTE_QUEUE)
        async with purge_pool() as retention_pool:
            maintenance = [
                asyncio.create_task(run_periodic_sweep(stop_maintenance)),
                asyncio.create_task(run_periodic_reconcile(stop_maintenance)),
                asyncio.create_task(
                    run_periodic_purge(
                        Admin(retention_pool, schema=COMPUTE_QUEUE_SCHEMA),
                        stop_maintenance,
                        compute_pool=pool,
                    )
                ),
            ]
            try:
                await worker.run()
            finally:
                stop_maintenance.set()
                for task in maintenance:
                    task.cancel()
                await asyncio.gather(*maintenance, return_exceptions=True)
    finally:
        await db.close_pool()


def main() -> None:  # pragma: no cover
    if NUMBA_THREADS is not None:
        # Numba lacks type stubs; suppress type checking.
        numba.set_num_threads(NUMBA_THREADS)  # type: ignore[no-untyped-call]
        logger.info(
            "numba parallel-region thread count capped to %d (TSDHN_NUMBA_THREADS)",
            NUMBA_THREADS,
        )

    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()
