import logging

import numba

from api.core.db import close_pool
from api.core.procrastinate_app import app
from api.core.settings import LOG_LEVEL, NUMBA_THREADS, PROCRASTINATE_QUEUE

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:  # pragma: no cover
    if NUMBA_THREADS is not None:
        # Numba lacks type stubs; suppress type checking.
        numba.set_num_threads(NUMBA_THREADS)  # type: ignore[no-untyped-call]
        logger.info(
            "numba parallel-region thread count capped to %d (TSDHN_NUMBA_THREADS)",
            NUMBA_THREADS,
        )

    app.open()
    try:
        app.run_worker(queues=[PROCRASTINATE_QUEUE])
    finally:
        app.close()
        # The periodic tasks use the read pool; close it so its worker
        # threads are joined before interpreter shutdown.
        close_pool()


if __name__ == "__main__":  # pragma: no cover
    main()
