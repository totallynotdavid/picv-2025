#!/usr/bin/env bash
set -euo pipefail

: "${SIMULATION_ID:=4cfe522f-7e7d-46e0-96ca-7b98743fb9f5}"
: "${COMPUTE_API_TOKEN:=compose-e2e-token}"
: "${MINIO_ACCESS_KEY:=minioadmin}"
: "${MINIO_SECRET_KEY:=minioadmin}"
: "${MINIO_BUCKET:=tsdhn-results}"
: "${COMPUTE_API_URL:=http://localhost:8000}"

wait_for_api() {
    for _ in {1..60}; do
        if curl -fsS "$COMPUTE_API_URL/api/v1/version"; then
            return 0
        fi
        docker compose ps
        sleep 5
    done

    echo "::error::API did not become reachable"
    return 1
}

create_results_bucket() {
    docker compose exec -T minio \
        mc alias set local http://127.0.0.1:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
    docker compose exec -T minio mc mb --ignore-existing "local/$MINIO_BUCKET"
}

submit_idempotent_simulation() {
    local payload first second conflicting status

    payload="$(
        jq -cn --arg simulation_id "$SIMULATION_ID" '{
          simulation_id: $simulation_id,
          input: {
            Mw: 8.0,
            h: 10.0,
            lat0: -20.5,
            lon0: -70.5,
            hhmm: "0000",
            dia: "23"
          }
        }'
    )"

    first="$(
        curl -fsS -X POST "$COMPUTE_API_URL/api/v1/jobs" \
            -H "Authorization: Bearer $COMPUTE_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$payload"
    )"
    echo "$first" | jq .
    echo "$first" > first-job.json

    second="$(
        curl -fsS -X POST "$COMPUTE_API_URL/api/v1/jobs" \
            -H "Authorization: Bearer $COMPUTE_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$payload"
    )"
    echo "$second" | jq .
    echo "$second" > second-job.json

    jq -e --arg simulation_id "$SIMULATION_ID" \
        '.simulation_id == $simulation_id' first-job.json
    jq -e --arg simulation_id "$SIMULATION_ID" \
        '.simulation_id == $simulation_id' second-job.json

    conflicting="$(
        jq -cn --arg simulation_id "$SIMULATION_ID" '{
          simulation_id: $simulation_id,
          input: {
            Mw: 8.1,
            h: 10.0,
            lat0: -20.5,
            lon0: -70.5,
            hhmm: "0000",
            dia: "23"
          }
        }'
    )"
    status="$(
        curl -sS -o conflict-response.json -w "%{http_code}" \
            -X POST "$COMPUTE_API_URL/api/v1/jobs" \
            -H "Authorization: Bearer $COMPUTE_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$conflicting"
    )"
    jq . conflict-response.json
    test "$status" = "400"
}

assert_queued_job() {
    local compute_count queue_count

    compute_count="$(
        docker compose exec -T postgres psql -U tsdhn -d tsdhn -tAc \
            "SELECT count(*) FROM compute.jobs WHERE simulation_id = '$SIMULATION_ID'::uuid"
    )"
    test "$compute_count" = "1"

    docker compose exec -T postgres psql -U tsdhn -d tsdhn -c \
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'procrastinate_%' ORDER BY tablename"

    # Idempotent submissions must not create a second queue row.
    queue_count="$(
        docker compose exec -T postgres psql -U tsdhn -d tsdhn -tAc \
            "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'api.run_simulation' AND queue_name = 'simulations'"
    )"
    test "$queue_count" = "1"
}

poll_job_to_completion() {
    local deadline body status

    rm -f status-history.jsonl
    deadline=$((SECONDS + 1800))

    while [ "$SECONDS" -lt "$deadline" ]; do
        body="$(
            curl -fsS "$COMPUTE_API_URL/api/v1/jobs/$SIMULATION_ID" \
                -H "Authorization: Bearer $COMPUTE_API_TOKEN"
        )"
        echo "$body" | jq -c . | tee -a status-history.jsonl

        status="$(echo "$body" | jq -r .status)"
        case "$status" in
            completed)
                echo "$body" > final-status.json
                return 0
                ;;
            failed)
                echo "$body" > final-status.json
                echo "::error::Simulation failed"
                return 1
                ;;
        esac

        sleep 10
    done

    echo "::error::Simulation did not complete before timeout"
    return 1
}

assert_completed_outputs() {
    local persisted

    jq . final-status.json
    jq -e '
      .status == "completed"
      and (.outputs | length) > 0
      and (.outputs | index("max_height_map")) != null
      and (.step_index | type == "number")
      and (.total_steps | type == "number")
      and (.calculation | type == "object")
      and (.travel_times | type == "object")
    ' final-status.json

    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$SIMULATION_ID/metadata.json"
    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$SIMULATION_ID/outputs/calculation.json"
    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$SIMULATION_ID/outputs/travel_times.csv"

    persisted="$(
        docker compose exec -T postgres psql -U tsdhn -d tsdhn -tAc \
            "SELECT status || '|' || result_key FROM compute.jobs WHERE simulation_id = '$SIMULATION_ID'::uuid"
    )"
    test "$persisted" = "completed|simulations/$SIMULATION_ID/metadata.json"
}

assert_output_is_downloadable() {
    local listed location bytes

    listed="$(
        curl -fsS "$COMPUTE_API_URL/api/v1/jobs/$SIMULATION_ID/outputs" \
            -H "Authorization: Bearer $COMPUTE_API_TOKEN"
    )"
    echo "$listed" | jq .
    jq -e '.outputs | map(.name) | index("max_height_map") != null' <<< "$listed"

    location="$(
        curl -fsS -o /dev/null -w '%{redirect_url}' \
            "$COMPUTE_API_URL/api/v1/jobs/$SIMULATION_ID/outputs/max_height_map" \
            -H "Authorization: Bearer $COMPUTE_API_TOKEN"
    )"
    test -n "$location"

    # The URL must be usable from the browser-facing endpoint.
    bytes="$(curl -fsS "$location" | head -c 4)"
    test "$bytes" = "%PDF"
}

assert_unauthenticated_output_is_refused() {
    local status
    status="$(
        curl -sS -o /dev/null -w '%{http_code}' \
            "$COMPUTE_API_URL/api/v1/jobs/$SIMULATION_ID/outputs/max_height_map"
    )"
    test "$status" = "401"
}

wait_for_api
create_results_bucket
submit_idempotent_simulation
assert_queued_job
poll_job_to_completion
assert_completed_outputs
assert_output_is_downloadable
assert_unauthenticated_output_is_refused
