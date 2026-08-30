import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import __version__
from api.core.db import close_pool, get_pool
from api.core.settings import LOG_LEVEL
from api.routes import get_calculator, ops_router, router

# Logs go to stdout, at INFO by default. They used to go to a file inside
# the container at DEBUG, which made them invisible to `docker logs`, grew
# without bound on the container filesystem, and wrote the raw tracebacks
# that compute.jobs.error is careful to redact into a file nobody rotates.
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_calculator()
    # Warm the pool without waiting: the API still boots and serves
    # /health (reporting degraded) when Postgres is not up yet.
    get_pool()
    logger.info("TSDHN API ready")
    try:
        yield
    finally:
        close_pool()


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
    # Containers set APP_HOST=0.0.0.0. Local runs stay on loopback by default.
    uvicorn.run(
        app,
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "8000")),
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    start_app()
