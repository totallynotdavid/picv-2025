import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import __version__
from api.core import db
from api.core.queue import build_queue
from api.core.settings import (
    COMPUTE_PRODUCER_PASSWORD,
    COMPUTE_PRODUCER_ROLE,
    LOG_LEVEL,
    api_pool_size,
)
from api.core.tasks import register_tasks
from api.routes import get_calculator, ops_router, router

# Send logs to stdout so container runtimes can collect them.
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_calculator()
    min_size, max_size = api_pool_size()
    # A zero floor keeps this from waiting on Postgres to start.
    pool = await db.open_pool(
        min_size=min_size,
        max_size=max_size,
        dsn=db.runtime_dsn(COMPUTE_PRODUCER_ROLE, COMPUTE_PRODUCER_PASSWORD),
    )
    register_tasks(build_queue(pool))
    logger.info("TSDHN API ready")
    try:
        yield
    finally:
        await db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="TSDHN API",
        version=__version__,
        docs_url="/api-docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    origins = [o for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(ops_router)
    app.include_router(router)
    return app


app = create_app()


def start_app() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "8000")),
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    start_app()
