# Compute API and worker image.
# The toolchain base provides GMT, Intel Fortran, and ttt_client.
#
# Build context is the repo root:  docker build -f deploy/api.Dockerfile .
ARG TOOLCHAIN_IMAGE=ghcr.io/totallynotdavid/tsdhn-toolchain:master
FROM ${TOOLCHAIN_IMAGE}

USER root
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python

COPY --from=ghcr.io/astral-sh/uv:0.11.27 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies before copying the remaining source.
COPY pyproject.toml uv.lock ./
COPY packages ./packages
RUN uv python install 3.14 \
 && uv sync --frozen --no-dev --package tsdhn-api

# TSDHN_MODEL_DIR points at this copied model tree at runtime.
# The pipeline uses Python plus GMT and ttt_client. The compiled Fortran
# binaries are used by parity tests, not by normal simulation runs.
COPY model ./model
RUN command -v gmt \
 && command -v gs \
 && command -v ttt_client

# Ghostscript is restricted to its allowed paths in the container. Keep its
# session files and simulation workspaces under /var/tmp.
RUN mkdir -p /var/tmp/jobs \
 && chown -R appuser:appuser /app /var/tmp/jobs

ENV APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    COMPUTE_DATABASE_URL=postgresql://tsdhn:tsdhn@postgres:5432/tsdhn \
    MINIO_ENDPOINT=minio:9000 \
    MINIO_ACCESS_KEY=minioadmin \
    MINIO_SECRET_KEY=minioadmin \
    MINIO_BUCKET=tsdhn-results \
    TSDHN_MODEL_DIR=/app/model \
    TSDHN_JOBS_DIR=/var/tmp/jobs \
    HOME=/var/tmp

USER appuser

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "tsdhn-api"]
