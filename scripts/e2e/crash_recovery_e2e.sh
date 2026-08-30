#!/usr/bin/env bash
# Live crash-recovery checks against the Compose stack.
#
# The script checks three cases:
#   1. A worker crash, heartbeat requeue, and tsunami checkpoint resume.
#   2. Cleanup of an old failed job workspace.
#   3. A transient MinIO failure during artifact upload.
#
# Expects the backend stack (postgres, minio, compute-migrate, api, worker)
# already built and started via docker compose, same as
# scripts/e2e/backend_stack_smoke.sh -- see .github/workflows/crash-recovery.yml.
set -euo pipefail

: "${CRASH_JOB_ID:=b6e1f5a0-2c1b-4a7c-9c7a-3f7b6a5d9e11}"
: "${TRANSIENT_JOB_ID:=c1a2b3c4-5d6e-4f70-8a9b-0c1d2e3f4a5b}"
: "${BACKEND_SERVICE_TOKEN:=compose-e2e-token}"
: "${MINIO_ACCESS_KEY:=minioadmin}"
: "${MINIO_SECRET_KEY:=minioadmin}"
: "${MINIO_BUCKET:=tsdhn-results}"
: "${API_BASE_URL:=http://localhost:8000}"
# Wait long enough for the tsunami step to write a checkpoint before the
# worker is killed.
: "${TSUNAMI_CHECKPOINT_WAIT_SECONDS:=120}"

psql_c() {
    docker compose exec -T postgres psql -U tsdhn -d tsdhn -tAc "$1"
}

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

dispatch_job() {
    local app_job_id="$1" payload response
    payload="$(
        jq -cn --arg app_job_id "$app_job_id" '{
          app_job_id: $app_job_id,
          input: { Mw: 8.0, h: 10.0, lat0: -20.5, lon0: -70.5, hhmm: "0000", dia: "23" }
        }'
    )"
    response="$(
        curl -fsS -X POST "$API_BASE_URL/api/v1/jobs" \
            -H "Authorization: Bearer $BACKEND_SERVICE_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$payload"
    )"
    echo "$response" | jq .
}

job_status() {
    local app_job_id="$1"
    curl -fsS "$API_BASE_URL/api/v1/jobs/$app_job_id" \
        -H "Authorization: Bearer $BACKEND_SERVICE_TOKEN"
}

wait_for_step() {
    local app_job_id="$1" target_step="$2" deadline_seconds="$3" deadline body step
    deadline=$((SECONDS + deadline_seconds))
    while [ "$SECONDS" -lt "$deadline" ]; do
        body="$(job_status "$app_job_id")"
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
    local app_job_id="$1" deadline_seconds="$2" deadline body status
    deadline=$((SECONDS + deadline_seconds))
    while [ "$SECONDS" -lt "$deadline" ]; do
        body="$(job_status "$app_job_id")"
        echo "$body" | jq -c .
        status="$(echo "$body" | jq -r .status)"
        case "$status" in
            completed)
                echo "$body" > "final-status-${app_job_id}.json"
                return 0
                ;;
            failed)
                echo "$body" > "final-status-${app_job_id}.json"
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

    dispatch_job "$CRASH_JOB_ID"
    wait_for_step "$CRASH_JOB_ID" "tsunami" 600
    echo "In tsunami step; waiting ${TSUNAMI_CHECKPOINT_WAIT_SECONDS}s for checkpoints to accumulate"
    sleep "$TSUNAMI_CHECKPOINT_WAIT_SECONDS"

    # The queue attempt counter records the requeue.
    local queue_job_id before_attempts
    queue_job_id="$(
        psql_c "SELECT id FROM procrastinate_jobs
                WHERE task_name = 'api.run_simulation'
                  AND task_kwargs->>'compute_job_id' =
                      (SELECT id::text FROM compute.jobs
                       WHERE external_id = '$CRASH_JOB_ID'::uuid)"
    )"
    test -n "$queue_job_id"
    before_attempts="$(psql_c "SELECT attempts FROM procrastinate_jobs WHERE id = $queue_job_id")"

    echo "Killing worker (SIGKILL) to simulate a crash"
    docker compose kill -s SIGKILL worker

    # Wait for the heartbeat timeout and the reaper's two-minute schedule.
    echo "Waiting up to 240s for the reaper to detect the stale job and requeue it"
    local deadline requeued=0
    deadline=$((SECONDS + 240))
    while [ "$SECONDS" -lt "$deadline" ]; do
        local attempts status
        attempts="$(psql_c "SELECT attempts FROM procrastinate_jobs WHERE id = $queue_job_id")"
        status="$(job_status "$CRASH_JOB_ID" | jq -r .status)"
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
    echo "Confirmed: attempts incremented on the same queue job, not marked FAILED"

    poll_job_to_completion "$CRASH_JOB_ID" 1800

    docker compose logs worker --no-color | grep -q "resuming tsunami run from step" || {
        echo "::error::Worker log has no evidence of resuming from a checkpoint"
        return 1
    }
    echo "Confirmed: worker log shows checkpoint resume"

    docker compose exec -T minio mc stat "local/$MINIO_BUCKET/simulations/$CRASH_JOB_ID/metadata.json"
}

scenario_ttl_sweep() {
    echo "--- Scenario 2: TTL sweep removes a terminally-FAILED job's work_dir ---"

    local sweep_job_id work_dir
    sweep_job_id="$(cat /proc/sys/kernel/random/uuid)"
    work_dir="/var/tmp/jobs/${sweep_job_id}"

    docker compose exec -T worker sh -c "mkdir -p '$work_dir' && touch '$work_dir/marker'"

    psql_c "
        INSERT INTO compute.jobs (id, external_id, status, input_params, details, finished_at)
        VALUES (gen_random_uuid(), '${sweep_job_id}'::uuid, 'failed', '{}'::jsonb,
                'synthetic e2e row', now() - interval '25 hours')
    " > /dev/null

    docker compose exec -T worker uv run --no-dev python -c "
from api.core.tasks import sweep_abandoned_work_dirs_task
sweep_abandoned_work_dirs_task(0)
"

    if docker compose exec -T worker test -e "$work_dir"; then
        echo "::error::sweep_abandoned_work_dirs_task did not remove $work_dir"
        return 1
    fi
    echo "Confirmed: expired FAILED job's work_dir was swept"
}

scenario_transient_retry() {
    echo "--- Scenario 3: MinIO outage during finalize triggers TRANSIENT_RETRY, not a failure ---"

    dispatch_job "$TRANSIENT_JOB_ID"
    wait_for_step "$TRANSIENT_JOB_ID" "copy_ttt_pdf" 1800
    echo "Reached the last pipeline step; stopping MinIO to force finalize's upload to fail"
    docker compose stop minio

    # exponential_wait=15 -> first retry attempt lands ~15s after the
    # failure; give it margin before asserting the retry was recorded.
    sleep 30
    local details
    details="$(job_status "$TRANSIENT_JOB_ID" | jq -r .details)"
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
    poll_job_to_completion "$TRANSIENT_JOB_ID" 300
}

wait_for_api
create_results_bucket
scenario_crash_and_requeue
scenario_ttl_sweep
scenario_transient_retry
