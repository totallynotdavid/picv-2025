"""Database-free tests for retry policy and payload decoding."""

import uuid

import pytest
from rqueue import PermanentFailure

from api.core.errors import TransientInfraError
from api.core.tasks import MAX_ATTEMPTS, RUN_SIMULATION, TRANSIENT_RETRY, decode_payload


def test_transient_retry_retries_transient_infra_error_within_budget() -> None:
    assert TRANSIENT_RETRY.should_retry(TransientInfraError("db down"), attempt=1)
    assert TRANSIENT_RETRY.should_retry(
        TransientInfraError("db down"), attempt=MAX_ATTEMPTS - 1
    )


def test_transient_retry_gives_up_once_attempts_exhausted() -> None:
    assert not TRANSIENT_RETRY.should_retry(
        TransientInfraError("db down"), attempt=MAX_ATTEMPTS
    )


def test_transient_retry_does_not_retry_other_exceptions() -> None:
    # retry_on is an allowlist: a pipeline error is terminal on attempt one.
    assert not TRANSIENT_RETRY.should_retry(RuntimeError("bad epicenter"), attempt=1)


def test_transient_retry_never_retries_a_permanent_failure() -> None:
    assert not TRANSIENT_RETRY.should_retry(PermanentFailure("unknown job"), attempt=1)


def test_transient_retry_backs_off_exponentially_from_fifteen_seconds() -> None:
    first = TRANSIENT_RETRY.backoff_seconds(1)
    second = TRANSIENT_RETRY.backoff_seconds(2)

    # Jitter is +/-10%, so these are ranges rather than exact values.
    assert 13.5 <= first <= 16.5
    assert 27.0 <= second <= 33.0


def test_the_task_name_is_the_one_already_deployed() -> None:
    # Renaming this strands every job a running deployment has already queued.
    assert RUN_SIMULATION == "api.run_simulation"


def test_decode_payload_reads_the_compute_job_id() -> None:
    compute_job_id = uuid.uuid4()

    assert decode_payload({"compute_job_id": str(compute_job_id)}) == compute_job_id


@pytest.mark.parametrize(
    "payload",
    [None, [], "compute_job_id", {}, {"compute_job_id": "not-a-uuid"}],
)
def test_decode_payload_rejects_anything_it_cannot_name_a_job_from(
    payload: object,
) -> None:
    # A decode failure is durable in rqueue and costs no retry budget, so it
    # has to raise rather than return a placeholder.
    with pytest.raises((ValueError, KeyError, TypeError)):
        decode_payload(payload)
