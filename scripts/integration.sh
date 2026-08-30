#!/usr/bin/env bash
set -euo pipefail

# These tests own this project-local cluster and never accept a production URL.
base_url="postgresql://tsdhn:tsdhn@127.0.0.1:5432/tsdhn"
database_name="tsdhn_integration_$(date +%s)_$$"
app_role="${database_name}_role"
app_password="tsdhn-web-test-password"

case "${1:-}" in
    "") coverage=0 ;;
    --coverage) coverage=1 ;;
    *) echo "usage: $0 [--coverage]" >&2; exit 2 ;;
esac

# Skip database startup if COMPUTE_DATABASE_URL is set (e.g., by CI with service container)
if [ -z "${COMPUTE_DATABASE_URL:-}" ]; then
    mise run db:start
fi

admin_url="$(
    uv run python -m scripts.database create \
        --base-url "$base_url" \
        --name "$database_name"
)"
app_url="$(
    uv run python -m scripts.database url \
        --base-url "$admin_url" \
        --name "$database_name" \
        --user "$app_role" \
        --password "$app_password"
)"

cleanup() {
    uv run python -m scripts.database drop \
        --base-url "$base_url" \
        --name "$database_name" \
        --role "$app_role" >/dev/null
}
trap cleanup EXIT

COMPUTE_DATABASE_URL="$admin_url" \
APP_DB_ROLE="$app_role" \
APP_DB_PASSWORD="$app_password" \
uv run tsdhn-compute-migrate

COMPUTE_DATABASE_URL="$admin_url" \
uv run tsdhn-procrastinate-migrate

# Schema changes run with the database-owner connection. The app role below
# is intentionally limited to runtime DML and compute-state reads.
DATABASE_URL="$admin_url" bun --filter web db:migrate

COMPUTE_DATABASE_URL="$admin_url" \
APP_DB_ROLE="$app_role" \
uv run tsdhn-web-grants

if [[ "$coverage" == "1" ]]; then
    uv run coverage run -m pytest -m integration packages/api/tests
else
    uv run pytest -m integration packages/api/tests
fi

DATABASE_URL="$app_url" \
    bun --filter web test:integration
