"""Database-free tests for retry, failure, and notification behavior."""

import uuid

from procrastinate.jobs import Job as ProcrastinateJob

from api.core.db import notify_channel
from api.core.errors import TransientInfraError
from api.core.tasks import MAX_ATTEMPTS, TRANSIENT_RETRY, reap_action


def _job(attempts: int, job_id: int | None = None) -> ProcrastinateJob:
    return ProcrastinateJob(
        id=job_id,
        queue="simulations",
        lock=None,
        queueing_lock=None,
        task_name="api.run_simulation",
        task_kwargs={"compute_job_id": "11111111-1111-4111-8111-111111111111"},
        attempts=attempts,
    )


def test_transient_retry_retries_transient_infra_error_within_budget() -> None:
    decision = TRANSIENT_RETRY.get_retry_decision(
        exception=TransientInfraError("db down"), job=_job(attempts=0)
    )
    assert decision is not None


def test_transient_retry_gives_up_once_attempts_exhausted() -> None:
    decision = TRANSIENT_RETRY.get_retry_decision(
        exception=TransientInfraError("db down"),
        job=_job(attempts=MAX_ATTEMPTS),
    )
    assert decision is None


def test_transient_retry_does_not_retry_other_exceptions() -> None:
    decision = TRANSIENT_RETRY.get_retry_decision(
        exception=RuntimeError("bad epicenter"), job=_job(attempts=0)
    )
    assert decision is None


def test_notify_channel_is_a_bare_identifier_per_job() -> None:
    simulation_id = uuid.UUID("4cfe522f-7e7d-46e0-96ca-7b98743fb9f5")
    channel = notify_channel(simulation_id)

    assert channel == "tsdhn_job_4cfe522f7e7d46e096ca7b98743fb9f5"
    # No hyphens or quoting needed: it goes straight into LISTEN/NOTIFY.
    assert channel.replace("_", "").isalnum()
    assert notify_channel(uuid.uuid4()) != channel


def test_reap_action_retries_a_stalled_job_within_budget() -> None:
    assert reap_action(_job(attempts=0)) == "retry"
    assert reap_action(_job(attempts=MAX_ATTEMPTS - 1)) == "retry"


def test_reap_action_gives_up_once_the_budget_is_spent() -> None:
    assert reap_action(_job(attempts=MAX_ATTEMPTS)) == "exhausted"
    assert reap_action(_job(attempts=MAX_ATTEMPTS + 1)) == "exhausted"
