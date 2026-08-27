# SvelteKit runs with the Node adapter for the self-hosted web target.
#
# Edge deployments use adapter-auto and point BACKEND_URL/DATABASE_URL at the
# self-hosted services. This image is for `docker compose --profile web up`.
#
# Build context is the repo root:  docker build -f deploy/web.Dockerfile .
FROM oven/bun:1.4.0

WORKDIR /app

# Dependencies are installed before source changes invalidate the build cache.
COPY package.json bun.lock ./
COPY apps/web/package.json apps/web/package.json
COPY libs/api-client/package.json libs/api-client/package.json
RUN bun install --frozen-lockfile

COPY libs ./libs
COPY apps/web ./apps/web
ENV ADAPTER=node
RUN DATABASE_URL=file:/tmp/tsdhn-build.db \
    ORIGIN=http://localhost:3000 \
    BETTER_AUTH_SECRET=build-time-placeholder-not-for-runtime \
    BACKEND_URL=http://127.0.0.1:8000 \
    BACKEND_SERVICE_TOKEN=build-time-placeholder \
    bun --filter web build

WORKDIR /app/apps/web
ENV HOST=0.0.0.0 \
    PORT=3000
EXPOSE 3000

# adapter-node emits build/index.js. node_modules stays available for externalized deps.
CMD ["bun", "./build/index.js"]
