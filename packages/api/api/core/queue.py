"""The rqueue handle for the simulation queue.

Three modules import rqueue, and no others: this one for `Queue`, `tasks.py`
for the task and retry types, and `worker.py` for `Worker`. `repository.py` in
particular does not -- it reaches the queue through the `defer` callback
`create_or_get_job` takes, and takes the queue's schema and name as plain
arguments where reconciliation needs them, so the business code stays
independent of which queue is behind it.
"""

import asyncpg
from rqueue import Queue

from api.core.settings import COMPUTE_QUEUE, COMPUTE_QUEUE_SCHEMA

__all__ = ["build_queue", "get_queue", "set_queue"]

_queue: Queue | None = None


def build_queue(pool: asyncpg.Pool) -> Queue:
    """Bind the process-wide queue to `pool` and return it.

    Both processes call this: the worker to serve the queue, the API to
    enqueue on the connection that also writes `compute.jobs`.
    """
    queue = Queue(pool, name=COMPUTE_QUEUE, schema=COMPUTE_QUEUE_SCHEMA)
    set_queue(queue)
    return queue


def set_queue(queue: Queue | None) -> None:
    global _queue
    _queue = queue


def get_queue() -> Queue:
    if _queue is None:
        raise RuntimeError("simulation queue is not built; call build_queue() first")
    return _queue
