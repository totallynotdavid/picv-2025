#!/usr/bin/env bash
set -euo pipefail

: "${APP_JOB_ID:=4cfe522f-7e7d-46e0-96ca-7b98743fb9f5}"
: "${BACKEND_SERVICE_TOKEN:=compose-e2e-token}"
: "${MINIO_ACCESS_KEY:=minioadmin}"
: "${MINIO_SECRET_KEY:=minioadmin}"
: "${MINIO_BUCKET:=tsdhn-results}"
: "${API_BASE_URL:=http://localhost:8000}"

wait_for_api() {
    for _ in {1..60}; do
        if curl -fsS "$API_BASE_URL/api/v1/version"; then
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

submit_idempotent_job() {
    local payload first second first_compute_job_id second_compute_job_id conflicting status

    payload="$(
        jq -cn --arg app_job_id "$APP_JOB_ID" '{
          app_job_id: $app_job_id,
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
        curl -fsS -X POST "$API_BASE_URL/api/v1/jobs" \
            -H "Authorization: Bearer $BACKEND_SERVICE_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$payload"
    )"
    echo "$first" | jq .
    echo "$first" > first-job.json

    second="$(
        curl -fsS -X POST "$API_BASE_URL/api/v1/jobs" \
            -H "Authorization: Bearer $BACKEND_SERVICE_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$payload"
    )"
    echo "$second" | jq .
    echo "$second" > second-job.json

    first_compute_job_id="$(jq -r .compute_job_id first-job.json)"
    second_compute_job_id="$(jq -r .compute_job_id second-job.json)"
    test "$first_compute_job_id" = "$second_compute_job_id"

    conflicting="$(
        jq -cn --arg app_job_id "$APP_JOB_ID" '{
          app_job_id: $app_job_id,
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
            -X POST "$API_BASE_URL/api/v1/jobs" \
            -H "Authorization: Bearer $BACKEND_SERVICE_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$conflicting"
    )"
    jq . conflict-response.json
    test "$status" = "400"
}

assert_queued_job() {
    local compute_count queue_count

    compute_count="$(
        docker compose exec -T postgres psql -U tsdhn -d tsdhn_compute -tAc \
            "SELECT count(*) FROM compute_jobs WHERE external_id = '$APP_JOB_ID'::uuid"
    )"
    test "$compute_count" = "1"

    docker compose exec -T postgres psql -U tsdhn -d tsdhn_compute -c \
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'procrastinate_%' ORDER BY tablename"

    # api.prepare_simulation is the first hop of the chained pipeline
    # (prepare -> run_pipeline_step x N -> finalize); api.run_simulation was
    # the old monolithic task name, retired when the chain was introduced.
    queue_count="$(
        docker compose exec -T postgres psql -U tsdhn -d tsdhn_compute -tAc \
            "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'api.prepare_simulation' AND queue_name = 'simulations'"
    )"
    test "$queue_count" = "1"
}

poll_job_to_completion() {
    local deadline body status

    rm -f status-history.jsonl
    deadline=$((SECONDS + 1800))

    while [ "$SECONDS" -lt "$deadline" ]; do
        body="$(
            curl -fsS "$API_BASE_URL/api/v1/jobs/$APP_JOB_ID" \
                -H "Authorization: Bearer $BACKEND_SERVICE_TOKEN"
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
    jq -e --arg key "simulations/$APP_JOB_ID/metadata.json" '
      .status == "completed"
      and .artifacts_available == true
      and .result_bucket == env.MINIO_BUCKET
      and .result_key == $key
      and (.step_index | type == "number")
      and (.total_steps | type == "number")
      and (.calculation | type == "object")
      and (.travel_times | type == "object")
    ' final-status.json

    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$APP_JOB_ID/metadata.json"
    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$APP_JOB_ID/artifacts/calculation.json"
    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$APP_JOB_ID/artifacts/travel_times.csv"

    persisted="$(
        docker compose exec -T postgres psql -U tsdhn -d tsdhn_compute -tAc \
            "SELECT status || '|' || result_key FROM compute_jobs WHERE external_id = '$APP_JOB_ID'::uuid"
    )"
    test "$persisted" = "completed|simulations/$APP_JOB_ID/metadata.json"
}

wait_for_api
create_results_bucket
submit_idempotent_job
assert_queued_job
poll_job_to_completion
assert_completed_outputs
