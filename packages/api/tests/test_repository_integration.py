"""Compute repository behavior against PostgreSQL."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from api.core import repository
from api.core.errors import TransientInfraError
from api.core.storage import output_store
from tsdhn.domain import CalculationResponse, EarthquakeInput, TsunamiTravelResponse
from tsdhn.engine import OutputFile, SimulationOutputs, SimulationResult
from tsdhn.runtime import RuntimeContext

pytestmark = pytest.mark.integration

INPUT = EarthquakeInput(Mw=8.0, h=10.0, lat0=-20.5, lon0=-70.5, hhmm="0000", dia="23")


@pytest.fixture
def database(
    isolated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    @contextmanager
    def pooled() -> Iterator[psycopg.Connection[dict[str, Any]]]:
        with psycopg.connect(isolated_database, row_factory=dict_row) as conn:
            yield conn

    # Keep the production query path while pointing it at the isolated database.
    monkeypatch.setattr(repository, "pooled", pooled)
    return isolated_database


def _create_job(
    database: str,
    *,
    data: EarthquakeInput = INPUT,
) -> tuple[str, uuid.UUID]:
    simulation_id = uuid.uuid4()
    deferred: list[uuid.UUID] = []

    repository.create_or_get_job(
        data=data,
        simulation_id=str(simulation_id),
        defer=lambda _conn, compute_job_id: deferred.append(compute_job_id),
    )

    assert len(deferred) == 1
    return str(simulation_id), deferred[0]


def test_create_or_get_job_is_idempotent_and_rejects_changed_input(
    database: str,
) -> None:
    simulation_id, compute_job_id = _create_job(database)

    second_defer: list[uuid.UUID] = []
    same = repository.create_or_get_job(
        data=INPUT,
        simulation_id=simulation_id,
        defer=lambda _conn, job_id: second_defer.append(job_id),
    )

    assert same["status"] == "queued"
    assert second_defer == []

    changed = INPUT.model_copy(update={"Mw": 8.1})
    with pytest.raises(ValueError, match="different input"):
        repository.create_or_get_job(
            data=changed,
            simulation_id=simulation_id,
            defer=lambda *_args: None,
        )

    persisted = repository.get_job_status(simulation_id)
    assert persisted["status"] == "queued"
    with psycopg.connect(database) as conn:
        persisted_id = conn.execute(
            "SELECT id FROM compute.jobs WHERE simulation_id = %s",
            [simulation_id],
        ).fetchone()
    assert persisted_id == (compute_job_id,)


def test_create_or_get_job_rolls_back_when_enqueue_fails(
    database: str,
) -> None:
    simulation_id = str(uuid.uuid4())

    def fail_to_enqueue(_conn: Any, _compute_job_id: uuid.UUID) -> None:
        raise RuntimeError("queue unavailable")

    with pytest.raises(RuntimeError, match="queue unavailable"):
        repository.create_or_get_job(
            data=INPUT,
            simulation_id=simulation_id,
            defer=fail_to_enqueue,
        )

    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        repository.get_job_status(simulation_id)


def test_concurrent_identical_submissions_create_one_job(
    database: str,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    simulation_id = str(uuid.uuid4())
    start = Barrier(2)
    deferred: list[uuid.UUID] = []

    def submit() -> dict[str, Any]:
        start.wait()
        return repository.create_or_get_job(
            data=INPUT,
            simulation_id=simulation_id,
            defer=lambda _conn, compute_job_id: deferred.append(compute_job_id),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: submit(), range(2)))

    assert {result["status"] for result in results} == {"queued"}
    assert len(deferred) == 1
    with psycopg.connect(database) as conn:
        count = conn.execute(
            "SELECT count(*) FROM compute.jobs WHERE simulation_id = %s",
            [simulation_id],
        ).fetchone()
    assert count == (1,)


def test_job_lookup_rejects_invalid_and_unknown_simulation_ids(
    database: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        repository.get_job_status("not-a-uuid")
    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        repository.get_job_status(str(uuid.uuid4()))


def test_outputs_are_empty_before_completion_and_unknown_jobs_are_rejected(
    database: str,
) -> None:
    simulation_id, _compute_job_id = _create_job(database)

    assert repository.get_outputs(simulation_id) == []
    with pytest.raises(ValueError, match="Invalid or unknown job ID"):
        repository.get_outputs(str(uuid.uuid4()))


def test_job_state_updates_are_persisted_as_client_visible_behavior(
    database: str,
) -> None:
    database_url = database
    simulation_id_text, compute_job_id = _create_job(database)
    simulation_id = uuid.UUID(simulation_id_text)

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        repository.mark_started(conn, compute_job_id, simulation_id)
        repository.record_progress(
            conn,
            compute_job_id,
            simulation_id,
            "Processing tsunami",
            {"step": "tsunami", "step_index": 3, "total_steps": 8},
        )
        assert repository.get_current_step(conn, compute_job_id) == "tsunami"

    running = repository.get_job_status(simulation_id_text)
    assert running["status"] == "running"
    assert running["details"] == "Processing tsunami"
    assert (running["step"], running["step_index"], running["total_steps"]) == (
        "tsunami",
        3,
        8,
    )

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        repository.fail_job(conn, compute_job_id, simulation_id, "worker vanished")

    failed = repository.get_job_status(simulation_id_text)
    assert failed["status"] == "failed"
    assert failed["error"] == "worker vanished"
    assert failed["finished_at"] is not None


def test_list_abandoned_work_dirs_returns_only_old_failed_jobs(
    database: str,
) -> None:
    database_url = database
    simulation_id_text, compute_job_id = _create_job(database)
    simulation_id = uuid.UUID(simulation_id_text)
    fresh_simulation_id_text, fresh_job_id = _create_job(database)
    fresh_simulation_id = uuid.UUID(fresh_simulation_id_text)
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        repository.fail_job(conn, compute_job_id, simulation_id, "worker vanished")
        repository.fail_job(conn, fresh_job_id, fresh_simulation_id, "worker vanished")
        conn.execute(
            "UPDATE compute.jobs SET finished_at = %s WHERE id = %s",
            [cutoff - timedelta(minutes=1), compute_job_id],
        )

    abandoned = repository.list_abandoned_work_dirs(cutoff)
    assert simulation_id_text in abandoned
    assert fresh_simulation_id_text not in abandoned


def test_record_failure_keeps_running_for_a_transient_retry(
    database: str,
) -> None:
    database_url = database
    simulation_id_text, compute_job_id = _create_job(database)
    simulation_id = uuid.UUID(simulation_id_text)

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        repository.mark_started(conn, compute_job_id, simulation_id)
        repository.record_failure(
            conn,
            compute_job_id,
            simulation_id,
            TransientInfraError("minio down"),
            step="maxola",
            will_retry=True,
        )

    status = repository.get_job_status(simulation_id_text)
    assert status["status"] == "running"
    assert status["details"] == "Retrying after transient error (TransientInfraError)"
    assert status["finished_at"] is None


def test_record_failure_persists_a_sanitized_terminal_error(
    database: str,
) -> None:
    database_url = database
    simulation_id_text, compute_job_id = _create_job(database)
    simulation_id = uuid.UUID(simulation_id_text)

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        repository.record_failure(
            conn,
            compute_job_id,
            simulation_id,
            FileNotFoundError("/private/jobs/secret/tsunami"),
            step="tsunami",
            will_retry=False,
        )

    status = repository.get_job_status(simulation_id_text)
    assert status["status"] == "failed"
    assert status["details"] == "Pipeline failed - check error logs"
    assert status["error"] == "Simulation failed at step 'tsunami' (FileNotFoundError)"
    assert "/private/jobs" not in status["error"]


def test_complete_job_persists_the_uploaded_manifest_and_result(
    database: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_url = database
    simulation_id_text, compute_job_id = _create_job(database)
    output_path = tmp_path / "calculation.json"
    output_path.write_text("{}", encoding="utf-8")

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
    outputs = SimulationOutputs(
        root=tmp_path,
        files=(OutputFile("calculation", output_path, "application/json"),),
    )
    result = SimulationResult(
        calculation=calculation,
        travel_times=travel_times,
        runtime=RuntimeContext(
            model_dir=tmp_path, model_version="test", capabilities={}
        ),
        outputs=outputs,
    )
    uploaded: dict[str, Any] = {}

    def fake_upload(**kwargs: Any) -> tuple[str, str]:
        uploaded.update(kwargs)
        return "results", "simulations/result/metadata.json"

    monkeypatch.setattr(output_store, "upload_simulation_result", fake_upload)

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        row = repository.fetch_by_id(conn, compute_job_id)
        assert row is not None
        repository.complete_job(conn, row, result)

    status = repository.get_job_status(simulation_id_text)
    assert status["status"] == "completed"
    assert status["calculation"] == calculation.model_dump(mode="json")
    assert status["travel_times"] == travel_times.model_dump(mode="json")
    assert status["outputs"] == ["calculation"]
    assert uploaded["simulation_id"] == simulation_id_text

    assert repository.get_outputs(simulation_id_text) == [
        {
            "name": "calculation",
            "key": f"simulations/{simulation_id_text}/outputs/calculation.json",
            "filename": "calculation.json",
            "content_type": "application/json",
        }
    ]
