#!/usr/bin/env bash
# Exercise worker recovery against a running Compose stack.
set -euo pipefail

: "${CRASH_SIMULATION_ID:=b6e1f5a0-2c1b-4a7c-9c7a-3f7b6a5d9e11}"
: "${TRANSIENT_SIMULATION_ID:=c1a2b3c4-5d6e-4f70-8a9b-0c1d2e3f4a5b}"
: "${COMPUTE_API_TOKEN:=compose-e2e-token}"
: "${MINIO_ACCESS_KEY:=minioadmin}"
: "${MINIO_SECRET_KEY:=minioadmin}"
: "${MINIO_BUCKET:=tsdhn-results}"
: "${COMPUTE_API_URL:=http://localhost:8000}"
: "${COMPUTE_QUEUE_SCHEMA:=task_queue}"
# The crash must happen after the resumable step writes a checkpoint.
: "${TSUNAMI_CHECKPOINT_WAIT_SECONDS:=120}"

psql_c() {
    docker compose exec -T postgres psql -U tsdhn -d tsdhn -tAc "$1"
}

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

submit_simulation() {
    local simulation_id="$1" payload response
    payload="$(
        jq -cn --arg simulation_id "$simulation_id" '{
          simulation_id: $simulation_id,
          input: { Mw: 8.0, h: 10.0, lat0: -20.5, lon0: -70.5, hhmm: "0000", dia: "23" }
        }'
    )"
    response="$(
        curl -fsS -X POST "$COMPUTE_API_URL/api/v1/jobs" \
            -H "Authorization: Bearer $COMPUTE_API_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$payload"
    )"
    echo "$response" | jq .
}

job_status() {
    local simulation_id="$1"
    curl -fsS "$COMPUTE_API_URL/api/v1/jobs/$simulation_id" \
        -H "Authorization: Bearer $COMPUTE_API_TOKEN"
}

wait_for_step() {
    local simulation_id="$1" target_step="$2" deadline_seconds="$3" deadline body step
    deadline=$((SECONDS + deadline_seconds))
    while [ "$SECONDS" -lt "$deadline" ]; do
        body="$(job_status "$simulation_id")"
        step="$(echo "$body" | jq -r .step)"
        if [ "$step" = "$target_step" ]; then
            echo "$body" | jq .
            return 0
        fi
        if [ "$(echo "$body" | jq -r .status)" = "failed" ]; then
            echo "$body" | jq .
            echo "::error::Job failed before reaching step '$target_step'"
            return 1
        fi
        sleep 5
    done
    echo "::error::Timed out waiting for step '$target_step'"
    return 1
}

poll_job_to_completion() {
    local simulation_id="$1" deadline_seconds="$2" deadline body status
    deadline=$((SECONDS + deadline_seconds))
    while [ "$SECONDS" -lt "$deadline" ]; do
        body="$(job_status "$simulation_id")"
        echo "$body" | jq -c .
        status="$(echo "$body" | jq -r .status)"
        case "$status" in
            completed)
                echo "$body" > "final-status-${simulation_id}.json"
                return 0
                ;;
            failed)
                echo "$body" > "final-status-${simulation_id}.json"
                echo "::error::Job ended FAILED instead of completing"
                return 1
                ;;
        esac
        sleep 10
    done
    echo "::error::Job did not complete before timeout"
    return 1
}

scenario_crash_and_requeue() {
    echo "--- Scenario 1: kill worker mid-tsunami, expect auto-requeue + checkpoint resume ---"

    submit_simulation "$CRASH_SIMULATION_ID"
    wait_for_step "$CRASH_SIMULATION_ID" "tsunami" 600
    echo "In tsunami step; waiting ${TSUNAMI_CHECKPOINT_WAIT_SECONDS}s for checkpoints to accumulate"
    sleep "$TSUNAMI_CHECKPOINT_WAIT_SECONDS"

    # Recovering an expired lease increments the same queue row's attempt.
    local queue_job_id before_attempts
    queue_job_id="$(
        psql_c "SELECT id FROM $COMPUTE_QUEUE_SCHEMA.jobs
                WHERE task = 'api.run_simulation'
                  AND payload->>'compute_job_id' =
                      (SELECT id::text FROM compute.jobs
                       WHERE simulation_id = '$CRASH_SIMULATION_ID'::uuid)"
    )"
    test -n "$queue_job_id"
    before_attempts="$(psql_c "SELECT attempt FROM $COMPUTE_QUEUE_SCHEMA.jobs WHERE id = '$queue_job_id'::uuid")"

    echo "Killing worker (SIGKILL) to simulate a crash"
    docker compose kill -s SIGKILL worker

    echo "Waiting up to 240s for rqueue to recover the expired lease and requeue it"
    local deadline requeued=0
    deadline=$((SECONDS + 240))
    while [ "$SECONDS" -lt "$deadline" ]; do
        local attempts status
        attempts="$(psql_c "SELECT attempt FROM $COMPUTE_QUEUE_SCHEMA.jobs WHERE id = '$queue_job_id'::uuid")"
        status="$(job_status "$CRASH_SIMULATION_ID" | jq -r .status)"
        if [ "$status" = "failed" ]; then
            echo "::error::Job was marked FAILED instead of being requeued"
            return 1
        fi
        if [ "${attempts:-0}" -gt "${before_attempts:-0}" ]; then
            requeued=1
            break
        fi
        sleep 10
    done
    test "$requeued" = "1" || {
        echo "::error::Job was never requeued after the worker crash"
        return 1
    }
    echo "Confirmed: attempt incremented on the same queue job, not marked FAILED"

    poll_job_to_completion "$CRASH_SIMULATION_ID" 1800

    docker compose logs worker --no-color | grep -q "resuming tsunami run from step" || {
        echo "::error::Worker log has no evidence of resuming from a checkpoint"
        return 1
    }
    echo "Confirmed: worker log shows checkpoint resume"

    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$CRASH_SIMULATION_ID/metadata.json"
}

scenario_ttl_sweep() {
    echo "--- Scenario 2: TTL sweep removes a terminally-FAILED job's work_dir ---"

    local sweep_job_id work_dir
    sweep_job_id="$(cat /proc/sys/kernel/random/uuid)"
    work_dir="/var/tmp/jobs/${sweep_job_id}"

    docker compose exec -T worker sh -c "mkdir -p '$work_dir' && touch '$work_dir/marker'"

    psql_c "
        INSERT INTO compute.jobs (id, simulation_id, status, input_params, details, finished_at)
        VALUES (gen_random_uuid(), '${sweep_job_id}'::uuid, 'failed', '{}'::jsonb,
                'synthetic e2e row', now() - interval '25 hours')
    " > /dev/null

    docker compose exec -T worker uv run --no-dev python -c "
import asyncio

from api.core import db
from api.core.settings import worker_pool_size
from api.core.tasks import sweep_abandoned_work_dirs


async def main():
    minimum, maximum = worker_pool_size()
    await db.open_pool(min_size=minimum, max_size=maximum)
    try:
        await sweep_abandoned_work_dirs()
    finally:
        await db.close_pool()


asyncio.run(main())
"

    if docker compose exec -T worker test -e "$work_dir"; then
        echo "::error::sweep_abandoned_work_dirs did not remove $work_dir"
        return 1
    fi
    echo "Confirmed: expired FAILED job's work_dir was swept"
}

scenario_transient_retry() {
    echo "--- Scenario 3: MinIO outage during finalize triggers TRANSIENT_RETRY, not a failure ---"

    submit_simulation "$TRANSIENT_SIMULATION_ID"
    wait_for_step "$TRANSIENT_SIMULATION_ID" "copy_ttt_pdf" 1800
    echo "Reached the last pipeline step; stopping MinIO to force finalize's upload to fail"
    docker compose stop minio

    # Give the queue time to record the transient retry.
    sleep 30
    local details
    details="$(job_status "$TRANSIENT_SIMULATION_ID" | jq -r .details)"
    echo "$details"
    case "$details" in
        *"Retrying after transient error"*) ;;
        *)
            echo "::error::Expected an in-flight TRANSIENT_RETRY, got: $details"
            docker compose start minio
            return 1
            ;;
    esac
    echo "Confirmed: TRANSIENT_RETRY recorded a retry instead of failing the job"

    docker compose start minio
    poll_job_to_completion "$TRANSIENT_SIMULATION_ID" 300
}

wait_for_api
create_results_bucket
scenario_crash_and_requeue
scenario_ttl_sweep
scenario_transient_retry
