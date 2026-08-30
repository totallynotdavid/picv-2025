"""Row-to-status mapping. Pure, so it needs no database.

What a client sees is built here; these tests pin the parts that are easy
to break silently -- the artifact manifest being reduced to names, and
compute-plane internals staying out of the response.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from api.core import repository
from api.core.repository import status_from_row
from tsdhn.domain import JobStatus

CREATED = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "external_id": uuid.uuid4(),
        "status": JobStatus.QUEUED.value,
        "input_params": {},
        "details": "Queued for simulation worker",
        "step": None,
        "step_index": None,
        "total_steps": None,
        "calculation": None,
        "travel_times": None,
        "artifacts": [],
        "result_bucket": None,
        "result_key": None,
        "error": None,
        "created_at": CREATED,
        "updated_at": CREATED,
        "started_at": None,
        "finished_at": None,
    }
    return row | overrides


def test_status_exposes_artifact_names_only() -> None:
    """The object key is compute-plane detail: the control plane addresses
    artifacts by name and never sees where they live."""
    status = status_from_row(
        _row(
            status=JobStatus.COMPLETED.value,
            artifacts=[
                {
                    "name": "max_height_map",
                    "key": "simulations/abc/artifacts/maxola.pdf",
                    "filename": "maxola.pdf",
                    "content_type": "application/pdf",
                }
            ],
        )
    )

    assert status["artifacts"] == ["max_height_map"]
    assert "simulations/abc" not in str(status)


def test_status_has_no_artifacts_before_completion() -> None:
    assert status_from_row(_row())["artifacts"] == []


def test_status_handles_a_null_artifacts_column() -> None:
    """Rows written before the column had a default read back as NULL."""
    assert status_from_row(_row(artifacts=None))["artifacts"] == []


def test_status_serializes_timestamps_as_iso_strings() -> None:
    status = status_from_row(_row(started_at=CREATED))

    assert status["created_at"] == CREATED.isoformat()
    assert status["started_at"] == CREATED.isoformat()
    assert status["finished_at"] is None


def test_status_carries_step_progress() -> None:
    status = status_from_row(
        _row(
            status=JobStatus.RUNNING.value, step="tsunami", step_index=3, total_steps=8
        )
    )

    assert (status["step"], status["step_index"], status["total_steps"]) == (
        "tsunami",
        3,
        8,
    )


class _FakeConn:
    """Records statements instead of running them."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, list[Any] | None]] = []
        self.committed = False

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        self.executed.append((sql, params))

    def commit(self) -> None:
        self.committed = True


def _notifies(conn: _FakeConn) -> list[str]:
    return [sql for sql, _ in conn.executed if sql.startswith("NOTIFY ")]


def test_mark_started_sets_running_and_notifies() -> None:
    conn = _FakeConn()
    external_id = uuid.UUID("4cfe522f-7e7d-46e0-96ca-7b98743fb9f5")

    repository.mark_started(conn, uuid.uuid4(), external_id)  # type: ignore[arg-type]

    update_sql, params = conn.executed[0]
    assert "started_at = COALESCE(started_at, now())" in update_sql
    assert params is not None
    assert params[0] == JobStatus.RUNNING.value
    assert _notifies(conn) == ["NOTIFY tsdhn_job_4cfe522f7e7d46e096ca7b98743fb9f5"]
    assert conn.committed


def test_record_progress_notifies_on_every_update() -> None:
    """The SSE stream sleeps on LISTEN, so a progress write that forgets to
    NOTIFY would silently stall every watcher until the keepalive tick."""
    conn = _FakeConn()

    repository.record_progress(
        conn,  # type: ignore[arg-type]
        uuid.uuid4(),
        uuid.uuid4(),
        "Processing tsunami",
        {"step": "tsunami", "step_index": 3, "total_steps": 8},
    )

    assert len(_notifies(conn)) == 1
    assert conn.committed


def test_record_progress_leaves_unset_fields_alone() -> None:
    """Progress callbacks are partial: a step update must not blank out the
    calculation an earlier callback stored."""
    conn = _FakeConn()

    repository.record_progress(
        conn,  # type: ignore[arg-type]
        uuid.uuid4(),
        uuid.uuid4(),
        "Processing tsunami",
        {"step": "tsunami"},
    )

    update_sql, params = conn.executed[0]
    assert "calculation = COALESCE(%s, calculation)" in update_sql
    assert params is not None
    assert params[5] is None  # calculation left untouched


def test_fail_job_records_a_terminal_failure_and_notifies() -> None:
    conn = _FakeConn()

    repository.fail_job(conn, uuid.uuid4(), uuid.uuid4(), "worker vanished")  # type: ignore[arg-type]

    update_sql, params = conn.executed[0]
    assert "finished_at = now()" in update_sql
    assert params is not None
    assert params[0] == JobStatus.FAILED.value
    assert params[2] == "worker vanished"
    assert len(_notifies(conn)) == 1
