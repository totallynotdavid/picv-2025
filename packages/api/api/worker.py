import asyncio
import logging
import os
import signal
import socket

import numba
from rqueue import Worker

from api.core import db
from api.core.queue import build_queue
from api.core.settings import (
    COMPUTE_QUEUE,
    LOG_LEVEL,
    NUMBA_THREADS,
    WORKER_CONCURRENCY,
    WORKER_ID,
    WORKER_LEASE_SECONDS,
    worker_pool_size,
)
from api.core.tasks import (
    register_tasks,
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


async def run() -> None:
    min_size, max_size = worker_pool_size()
    pool = await db.open_pool(min_size=min_size, max_size=max_size)
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

        # The worker process owns maintenance because it is the process that
        # owns recovery: reconciliation exists to repair the compute.jobs rows
        # rqueue's own lease recovery leaves behind.
        stop_maintenance = asyncio.Event()
        maintenance = [
            asyncio.create_task(run_periodic_sweep(stop_maintenance)),
            asyncio.create_task(run_periodic_reconcile(stop_maintenance)),
        ]
        logger.info("simulation worker serving queue %s", COMPUTE_QUEUE)
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
