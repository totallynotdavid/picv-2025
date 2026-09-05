"""Compute repository behavior against PostgreSQL."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from rqueue import Queue

from api.core import db, repository
from api.core.errors import TransientInfraError
from api.core.settings import COMPUTE_QUEUE, COMPUTE_QUEUE_SCHEMA
from api.core.storage import output_store
from api.core.tasks import RUN_SIMULATION, enqueue_simulation
from tsdhn.domain import CalculationResponse, EarthquakeInput, TsunamiTravelResponse
from tsdhn.engine import OutputFile, SimulationOutputs, SimulationResult
from tsdhn.runtime import RuntimeContext

pytestmark = pytest.mark.integration

INPUT = EarthquakeInput(Mw=8.0, h=10.0, lat0=-20.5, lon0=-70.5, hhmm="0000", dia="23")


async def _create_job(*, data: EarthquakeInput = INPUT) -> tuple[str, uuid.UUID]:
    simulation_id = uuid.uuid4()
    deferred: list[uuid.UUID] = []

    async def defer(_conn: Any, compute_job_id: uuid.UUID) -> None:
        deferred.append(compute_job_id)

    await repository.create_or_get_job(
        data=data, simulation_id=str(simulation_id), defer=defer
    )

    assert len(deferred) == 1
    return str(simulation_id), deferred[0]


async def _queue_rows(queue: Queue) -> list[Any]:
    async with db.acquire() as conn:
        return list(
            await conn.fetch(
                f"SELECT * FROM {COMPUTE_QUEUE_SCHEMA}.jobs ORDER BY seq"  # noqa: S608
            )
        )


@pytest.mark.asyncio
async def test_create_or_get_job_is_idempotent_and_rejects_changed_input(
    queue: Queue,
) -> None:
    simulation_id, compute_job_id = await _create_job()

    second_defer: list[uuid.UUID] = []

    async def defer(_conn: Any, job_id: uuid.UUID) -> None:
        second_defer.append(job_id)

    same = await repository.create_or_get_job(
        data=INPUT, simulation_id=simulation_id, defer=defer
    )

    assert same["status"] == "queued"
    assert second_defer == []

    changed = INPUT.model_copy(update={"Mw": 8.1})

    async def unreached(*_args: Any) -> None:
        pytest.fail("a conflicting submission must not reach the queue")

    with pytest.raises(ValueError, match="different input"):
        await repository.create_or_get_job(
            data=changed, simulation_id=simulation_id, defer=unreached
        )

    persisted = await repository.get_job_status(simulation_id)
    assert persisted["status"] == "queued"
    async with db.acquire() as conn:
        persisted_id = await conn.fetchval(
            "SELECT id FROM compute.jobs WHERE simulation_id = $1",
            uuid.UUID(simulation_id),
        )
    assert persisted_id == compute_job_id


@pytest.mark.asyncio
async def test_the_job_row_and_its_queue_entry_commit_together(queue: Queue) -> None:
    simulation_id = str(uuid.uuid4())

    job_status = await repository.create_or_get_job(
        data=INPUT, simulation_id=simulation_id, defer=enqueue_simulation
    )
    assert job_status["status"] == "queued"

    (row,) = await _queue_rows(queue)
    async with db.acquire() as conn:
        compute_job_id = await conn.fetchval(
            "SELECT id FROM compute.jobs WHERE simulation_id = $1",
            uuid.UUID(simulation_id),
        )
    assert row["task"] == RUN_SIMULATION
    assert row["queue"] == COMPUTE_QUEUE
    assert row["state"] == "pending"
    assert row["dedupe_key"] == f"simulation:{compute_job_id}"


@pytest.mark.asyncio
async def test_a_rolled_back_producer_leaves_neither_row(queue: Queue) -> None:
    simulation_id = str(uuid.uuid4())

    async def enqueue_then_fail(conn: Any, compute_job_id: uuid.UUID) -> None:
        await enqueue_simulation(conn, compute_job_id)
        raise RuntimeError("queue unavailable")

    with pytest.raises(RuntimeError, match="queue unavailable"):
        await repository.create_or_get_job(
            data=INPUT, simulation_id=simulation_id, defer=enqueue_then_fail
        )

    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        await repository.get_job_status(simulation_id)
    assert await _queue_rows(queue) == []


@pytest.mark.asyncio
async def test_a_repeated_submission_enqueues_exactly_one_job(queue: Queue) -> None:
    simulation_id = str(uuid.uuid4())

    for _ in range(2):
        await repository.create_or_get_job(
            data=INPUT, simulation_id=simulation_id, defer=enqueue_simulation
        )

    assert len(await _queue_rows(queue)) == 1


@pytest.mark.asyncio
async def test_concurrent_identical_submissions_create_one_job(queue: Queue) -> None:
    simulation_id = str(uuid.uuid4())
    deferred: list[uuid.UUID] = []

    async def defer(_conn: Any, compute_job_id: uuid.UUID) -> None:
        deferred.append(compute_job_id)

    results = await asyncio.gather(
        *(
            repository.create_or_get_job(
                data=INPUT, simulation_id=simulation_id, defer=defer
            )
            for _ in range(2)
        )
    )

    assert {result["status"] for result in results} == {"queued"}
    assert len(deferred) == 1
    async with db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM compute.jobs WHERE simulation_id = $1",
            uuid.UUID(simulation_id),
        )
    assert count == 1


@pytest.mark.asyncio
async def test_job_lookup_rejects_invalid_and_unknown_simulation_ids(
    queue: Queue,
) -> None:
    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        await repository.get_job_status("not-a-uuid")
    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        await repository.get_job_status(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_outputs_are_empty_before_completion_and_unknown_jobs_are_rejected(
    queue: Queue,
) -> None:
    simulation_id, _compute_job_id = await _create_job()

    assert await repository.get_outputs(simulation_id) == []
    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        await repository.get_outputs(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_job_state_updates_are_persisted_as_client_visible_behavior(
    queue: Queue,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)

    async with db.acquire() as conn:
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        await repository.record_progress(
            conn,
            compute_job_id,
            simulation_id,
            "Processing tsunami",
            {"step": "tsunami", "step_index": 3, "total_steps": 8},
            1,
        )
        assert await repository.get_current_step(conn, compute_job_id) == "tsunami"

    running = await repository.get_job_status(simulation_id_text)
    assert running["status"] == "running"
    assert running["details"] == "Processing tsunami"
    assert (running["step"], running["step_index"], running["total_steps"]) == (
        "tsunami",
        3,
        8,
    )


@pytest.mark.asyncio
async def test_progress_json_survives_the_text_jsonb_round_trip(queue: Queue) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)
    calculation = {"length": 1.5, "corners": [[1, 2], [3, 4]], "warning": None}

    async with db.acquire() as conn:
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        await repository.record_progress(
            conn,
            compute_job_id,
            simulation_id,
            "Processing tsunami",
            {"step": "tsunami", "calculation": calculation},
            1,
        )
        # A second write that mentions neither column must leave both alone.
        await repository.record_progress(
            conn,
            compute_job_id,
            simulation_id,
            "Processing maxola",
            {"step": "maxola"},
            1,
        )

    status = await repository.get_job_status(simulation_id_text)
    assert status["calculation"] == calculation
    assert status["travel_times"] is None
    assert status["step"] == "maxola"


@pytest.mark.asyncio
async def test_a_notification_is_only_delivered_once_its_update_commits(
    queue: Queue,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)
    seen: list[str] = []

    listener = await db.connect()
    try:
        await listener.add_listener(
            db.notify_channel(simulation_id),
            lambda *_args: seen.append("notified"),
        )
        async with db.acquire() as conn:
            await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        # asyncpg dispatches the notification on the connection's own reads.
        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.02)
        assert seen, "mark_started must wake a listening SSE stream"
        # The row the client is about to re-read is already committed.
        assert (await repository.get_job_status(simulation_id_text))[
            "status"
        ] == "running"
    finally:
        await listener.close()


@pytest.mark.asyncio
async def test_list_abandoned_work_dirs_returns_only_old_failed_jobs(
    queue: Queue,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)
    fresh_simulation_id_text, fresh_job_id = await _create_job()
    fresh_simulation_id = uuid.UUID(fresh_simulation_id_text)
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    async with db.acquire() as conn:
        for job_id, external_id in (
            (compute_job_id, simulation_id),
            (fresh_job_id, fresh_simulation_id),
        ):
            await repository.mark_started(conn, job_id, external_id, 1)
            await repository.record_failure(
                conn,
                job_id,
                external_id,
                RuntimeError("worker vanished"),
                step="tsunami",
                will_retry=False,
                attempt=1,
            )
        await conn.execute(
            "UPDATE compute.jobs SET finished_at = $1 WHERE id = $2",
            cutoff - timedelta(minutes=1),
            compute_job_id,
        )

    abandoned = await repository.list_abandoned_work_dirs(cutoff)
    assert simulation_id_text in abandoned
    assert fresh_simulation_id_text not in abandoned


@pytest.mark.asyncio
async def test_record_failure_keeps_running_for_a_transient_retry(
    queue: Queue,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)

    async with db.acquire() as conn:
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        await repository.record_failure(
            conn,
            compute_job_id,
            simulation_id,
            TransientInfraError("minio down"),
            step="maxola",
            will_retry=True,
            attempt=1,
        )

    status = await repository.get_job_status(simulation_id_text)
    assert status["status"] == "running"
    assert status["details"] == "Retrying after transient error (TransientInfraError)"
    assert status["finished_at"] is None


@pytest.mark.asyncio
async def test_record_failure_persists_a_sanitized_terminal_error(
    queue: Queue,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)

    async with db.acquire() as conn:
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        await repository.record_failure(
            conn,
            compute_job_id,
            simulation_id,
            FileNotFoundError("/private/jobs/secret/tsunami"),
            step="tsunami",
            will_retry=False,
            attempt=1,
        )

    status = await repository.get_job_status(simulation_id_text)
    assert status["status"] == "failed"
    assert status["details"] == "Pipeline failed - check error logs"
    assert status["error"] == "Simulation failed at step 'tsunami' (FileNotFoundError)"
    assert "/private/jobs" not in status["error"]


@pytest.mark.asyncio
async def test_is_database_connected_reports_a_closed_pool(queue: Queue) -> None:
    assert await repository.is_database_connected() is True
    await db.close_pool()
    assert await repository.is_database_connected() is False


def _result(tmp_path: Path, output_path: Path) -> SimulationResult:
    calculation = CalculationResponse(
        length=1.0,
        width=2.0,
        dislocation=3.0,
        seismic_moment=4.0,
        tsunami_warning="none",
        distance_to_coast=5.0,
        azimuth=6.0,
        dip=7.0,
        epicenter_location="0.00/0.00",
        rectangle_parameters={},
        rectangle_corners=[],
    )
    travel_times = TsunamiTravelResponse(
        arrival_times={"PORT": "01:00"},
        distances={"PORT": 100.0},
        epicenter_info={"lat": "0.0"},
    )
    return SimulationResult(
        calculation=calculation,
        travel_times=travel_times,
        runtime=RuntimeContext(
            model_dir=tmp_path, model_version="test", capabilities={}
        ),
        outputs=SimulationOutputs(
            root=tmp_path,
            files=(OutputFile("calculation", output_path, "application/json"),),
        ),
    )


@pytest.mark.asyncio
async def test_complete_job_persists_the_uploaded_manifest_and_result(
    queue: Queue,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    output_path = tmp_path / "calculation.json"
    output_path.write_text("{}", encoding="utf-8")
    result = _result(tmp_path, output_path)
    uploaded: dict[str, Any] = {}

    def fake_upload(**kwargs: Any) -> tuple[str, str]:
        uploaded.update(kwargs)
        return "results", "simulations/result/metadata.json"

    monkeypatch.setattr(output_store, "upload_simulation_result", fake_upload)

    async with db.acquire() as conn:
        simulation_id = uuid.UUID(simulation_id_text)
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        row = await repository.fetch_by_id(conn, compute_job_id)
        assert row is not None
        await repository.complete_job(conn, row, result, 1)

    status = await repository.get_job_status(simulation_id_text)
    assert status["status"] == "completed"
    assert status["calculation"] == result.calculation.model_dump(mode="json")
    assert status["travel_times"] == result.travel_times.model_dump(mode="json")
    assert status["outputs"] == ["calculation"]
    assert uploaded["simulation_id"] == simulation_id_text

    assert await repository.get_outputs(simulation_id_text) == [
        {
            "name": "calculation",
            "key": f"simulations/{simulation_id_text}/outputs/calculation.json",
            "filename": "calculation.json",
            "content_type": "application/json",
        }
    ]


@pytest.mark.asyncio
async def test_a_backend_killed_mid_statement_reports_as_transient(
    queue: Queue,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)

    async with db.acquire() as conn, db.acquire() as killer:
        backend_pid = await conn.fetchval("SELECT pg_backend_pid()")
        await killer.execute("SELECT pg_terminate_backend($1)", backend_pid)
        await asyncio.sleep(0.3)

        # A database restart under a running simulation lands here, not on
        # acquire(). TRANSIENT_RETRY only retries TransientInfraError, so an
        # untranslated asyncpg error would turn an outage into a dead job.
        with pytest.raises(TransientInfraError, match="database unavailable"):
            await repository.record_progress(
                conn, compute_job_id, simulation_id, "Processing tsunami", {}, 1
            )


@pytest.mark.asyncio
async def test_record_failure_never_overwrites_a_finished_job(queue: Queue) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE compute.jobs SET status = 'completed', "
            "details = 'Simulation completed successfully' WHERE id = $1",
            compute_job_id,
        )
        # complete_job's UPDATE can commit and the connection still drop before
        # the caller learns it did, so the caller reports a failure for a job
        # that actually finished. Neither branch may act on that.
        await repository.record_failure(
            conn,
            compute_job_id,
            simulation_id,
            TransientInfraError("output upload failed"),
            step="copy_ttt_pdf",
            will_retry=True,
            attempt=1,
        )
        await repository.record_failure(
            conn,
            compute_job_id,
            simulation_id,
            RuntimeError("bad epicenter"),
            step="copy_ttt_pdf",
            will_retry=False,
            attempt=1,
        )

    status = await repository.get_job_status(simulation_id_text)
    assert status["status"] == "completed"
    assert status["details"] == "Simulation completed successfully"
    assert status["error"] is None


@pytest.mark.asyncio
async def test_complete_job_reports_a_result_it_could_not_record(
    queue: Queue,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    output_path = tmp_path / "calculation.json"
    output_path.write_text("{}", encoding="utf-8")
    result = _result(tmp_path, output_path)
    monkeypatch.setattr(
        output_store,
        "upload_simulation_result",
        lambda **_kwargs: ("results", "simulations/orphan/metadata.json"),
    )

    async with db.acquire() as conn:
        simulation_id = uuid.UUID(simulation_id_text)
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        row = await repository.fetch_by_id(conn, compute_job_id)
        assert row is not None
        # A newer attempt owns the row by the time this one finishes.
        await repository.mark_started(conn, compute_job_id, simulation_id, 2)

        with caplog.at_level("ERROR"):
            recorded = await repository.complete_job(conn, row, result, 1)

    # The upload already happened, so a silent no-op here would leave objects
    # in MinIO with nothing in compute.jobs pointing at them and no trace why.
    assert recorded is False
    assert "simulations/orphan/metadata.json" in caplog.text
    assert (await repository.get_job_status(simulation_id_text))["status"] == "running"


@pytest.mark.asyncio
async def test_a_claim_cannot_reopen_a_completed_job(queue: Queue) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)

    async with db.acquire() as conn:
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        await conn.execute(
            "UPDATE compute.jobs SET status = 'completed', finished_at = now() "
            "WHERE id = $1",
            compute_job_id,
        )
        # A redelivered attempt. The refusal has to be part of the UPDATE: a
        # separate SELECT before it leaves room for a job to complete in between.
        assert not await repository.mark_started(conn, compute_job_id, simulation_id, 2)

    status = await repository.get_job_status(simulation_id_text)
    assert status["status"] == "completed"
    assert status["finished_at"] is not None


@pytest.mark.asyncio
async def test_a_reclaimed_job_does_not_keep_the_previous_failure(
    queue: Queue,
) -> None:
    simulation_id_text, compute_job_id = await _create_job()
    simulation_id = uuid.UUID(simulation_id_text)

    async with db.acquire() as conn:
        await repository.mark_started(conn, compute_job_id, simulation_id, 1)
        await repository.record_failure(
            conn,
            compute_job_id,
            simulation_id,
            RuntimeError("bad epicenter"),
            step="tsunami",
            will_retry=False,
            attempt=1,
        )
        failed = await repository.get_job_status(simulation_id_text)
        assert failed["error"] is not None
        assert failed["finished_at"] is not None

        # An operator retry, or a later attempt, reclaims it.
        assert await repository.mark_started(conn, compute_job_id, simulation_id, 2)

    # `running` alongside a previous attempt's error and finish time is not a
    # state any client can read correctly -- status_from_row hands all three to
    # the status endpoint and to SSE together.
    running = await repository.get_job_status(simulation_id_text)
    assert running["status"] == "running"
    assert running["error"] is None
    assert running["finished_at"] is None
    assert running["started_at"] is not None
