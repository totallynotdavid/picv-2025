# SvelteKit image for the self-hosted web target.
# Edge deployments use adapter-auto and these runtime variables.
#
# Build context is the repo root:  docker build -f deploy/web.Dockerfile .
FROM oven/bun:1.3.14

WORKDIR /app

# Install dependencies before copying the remaining source.
COPY package.json bun.lock ./
COPY apps/web/package.json apps/web/package.json
COPY libs/api-client/package.json libs/api-client/package.json
RUN bun install --frozen-lockfile

COPY libs ./libs
COPY apps/web ./apps/web
ENV ADAPTER=node
# The build only needs syntactically valid runtime variables.
RUN DATABASE_URL=postgresql://build:build@127.0.0.1:5432/build \
    ORIGIN=http://localhost:3000 \
    BETTER_AUTH_SECRET=build-time-placeholder-not-for-runtime \
    COMPUTE_API_URL=http://127.0.0.1:8000 \
    COMPUTE_API_TOKEN=build-time-placeholder \
    bun --filter web build

WORKDIR /app/apps/web
ENV HOST=0.0.0.0 \
    PORT=3000
EXPOSE 3000

# The Node adapter builds this entry point.
CMD ["bun", "./build/index.js"]
