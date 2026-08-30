import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import routes
from api.core import repository
from api.core.storage import output_store
from api.main import app

routes_module: Any = routes

TOKEN = "test-compute-api-token"
SAMPLE = {
    "Mw": 8.0,
    "h": 10.0,
    "lat0": -20.5,
    "lon0": -70.5,
    "hhmm": "0000",
    "dia": "23",
}
SIMULATION_ID = "4cfe522f-7e7d-46e0-96ca-7b98743fb9f5"


@pytest.fixture(autouse=True)
def _service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTE_API_TOKEN", TOKEN)
    monkeypatch.setenv("TSDHN_MODEL_DIR", str(Path("model").resolve()))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_health_is_unauthenticated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repository, "is_database_connected", lambda: True)
    monkeypatch.setattr(output_store, "is_connected", lambda: True)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert set(response.json()) == {
        "status",
        "timestamp",
        "database_connected",
        "storage_connected",
    }


def test_health_reports_degraded_when_a_dependency_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repository, "is_database_connected", lambda: True)
    monkeypatch.setattr(output_store, "is_connected", lambda: False)

    assert client.get("/api/v1/health").json()["status"] == "degraded"


def test_version(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert response.json()["name"] == "tsdhn-api"


def test_get_job_returns_repository_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        repository,
        "get_job_status",
        lambda _simulation_id: {
            "status": "running",
            "details": "Processing tsunami",
            "step": "tsunami",
            "step_index": 3,
            "total_steps": 8,
            "outputs": [],
        },
    )

    response = client.get(f"/api/v1/jobs/{SIMULATION_ID}", headers=_auth())

    assert response.status_code == 200
    assert response.json()["simulation_id"] == SIMULATION_ID
    assert response.json()["status"] == "running"
    assert response.json()["step_index"] == 3


def test_get_job_maps_unknown_job_to_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unknown(_simulation_id: str) -> dict[str, Any]:
        raise ValueError("unknown")

    monkeypatch.setattr(
        repository,
        "get_job_status",
        unknown,
    )

    response = client.get(f"/api/v1/jobs/{SIMULATION_ID}", headers=_auth())

    assert response.status_code == 404


def test_calculations_rejects_missing_token(client: TestClient) -> None:
    response = client.post("/api/v1/calculations", json=SAMPLE)
    assert response.status_code == 401


def test_calculations_returns_preview(client: TestClient) -> None:
    response = client.post("/api/v1/calculations", headers=_auth(), json=SAMPLE)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"calculation", "travel_times"}
    assert body["calculation"]["length"] > 0
    assert body["calculation"]["width"] > 0
    assert body["travel_times"]["arrival_times"]


def test_jobs_rejects_missing_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/jobs",
        json={"simulation_id": SIMULATION_ID, "input": SAMPLE},
    )
    assert response.status_code == 401


def test_jobs_use_simulation_id_to_reuse_an_existing_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def create_or_get_job(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "status": "queued",
        }

    monkeypatch.setattr(repository, "create_or_get_job", create_or_get_job)

    response = client.post(
        "/api/v1/jobs",
        headers=_auth(),
        json={"simulation_id": SIMULATION_ID, "input": SAMPLE},
    )

    assert response.status_code == 201
    assert response.json() == {
        "simulation_id": SIMULATION_ID,
        "status": "queued",
    }
    assert calls[0]["simulation_id"] == SIMULATION_ID


def test_outputs_require_a_token(client: TestClient) -> None:
    assert client.get(f"/api/v1/jobs/{SIMULATION_ID}/outputs").status_code == 401


def test_outputs_list_is_empty_until_the_job_completes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repository, "get_outputs", lambda _id: [])

    response = client.get(f"/api/v1/jobs/{SIMULATION_ID}/outputs", headers=_auth())
    assert response.status_code == 200
    assert response.json() == {"simulation_id": SIMULATION_ID, "outputs": []}


def test_outputs_list_names_what_the_job_produced(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        repository,
        "get_outputs",
        lambda _id: [
            {
                "name": "max_height_map",
                "key": f"simulations/{SIMULATION_ID}/outputs/maxola.pdf",
                "filename": "maxola.pdf",
                "content_type": "application/pdf",
            }
        ],
    )

    response = client.get(f"/api/v1/jobs/{SIMULATION_ID}/outputs", headers=_auth())
    assert response.status_code == 200
    assert response.json()["outputs"] == [
        {
            "name": "max_height_map",
            "filename": "maxola.pdf",
            "content_type": "application/pdf",
        }
    ]
    # Storage object keys must not reach the client.
    assert "key" not in response.text


def test_output_download_redirects_to_a_presigned_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        repository,
        "get_outputs",
        lambda _id: [
            {
                "name": "max_height_map",
                "key": f"simulations/{SIMULATION_ID}/outputs/maxola.pdf",
                "filename": "maxola.pdf",
                "content_type": "application/pdf",
            }
        ],
    )
    monkeypatch.setattr(
        output_store,
        "presigned_url",
        lambda key, *, filename: f"https://minio.example/{key}?sig=abc",
    )

    response = client.get(
        f"/api/v1/jobs/{SIMULATION_ID}/outputs/max_height_map",
        headers=_auth(),
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://minio.example/simulations/")


def test_unknown_output_name_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repository, "get_outputs", lambda _id: [])

    response = client.get(
        f"/api/v1/jobs/{SIMULATION_ID}/outputs/nope",
        headers=_auth(),
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_output_download_maps_an_unknown_job_to_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unknown(_simulation_id: str) -> list[dict[str, str]]:
        raise ValueError("unknown")

    monkeypatch.setattr(repository, "get_outputs", unknown)

    response = client.get(
        f"/api/v1/jobs/{SIMULATION_ID}/outputs/max_height_map",
        headers=_auth(),
        follow_redirects=False,
    )

    assert response.status_code == 404


def test_job_events_maps_an_invalid_job_id_to_not_found(client: TestClient) -> None:
    response = client.get(
        "/api/v1/jobs/not-a-uuid/events",
        headers=_auth(),
    )

    assert response.status_code == 404


class _FakeAsyncConnection:
    def __init__(self, *, notify: bool) -> None:
        self.notify = notify
        self.executed: list[str] = []
        self.closed = False

    async def execute(self, statement: str) -> None:
        self.executed.append(statement)

    async def notifies(
        self, *, timeout: float, stop_after: int
    ) -> AsyncIterator[object]:
        if self.notify:
            yield object()

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_job_events_emits_a_terminal_snapshot_without_opening_a_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def status(_simulation_id: str) -> dict[str, Any]:
        return {"status": "completed", "outputs": ["result"]}

    monkeypatch.setattr(routes, "_job_status", status)

    response = await routes.job_events(SIMULATION_ID)
    chunks = [chunk async for chunk in response.body_iterator]

    assert len(chunks) == 1
    assert json.loads(cast(str, chunks[0])[len("data: ") : -2]) == {
        "simulation_id": SIMULATION_ID,
        "status": "completed",
        "outputs": ["result"],
    }


@pytest.mark.asyncio
async def test_job_events_emits_an_sse_error_for_an_unknown_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unknown(_simulation_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=404)

    monkeypatch.setattr(routes, "_job_status", unknown)

    response = await routes.job_events(SIMULATION_ID)
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == ['event: error\ndata: {"error": "unknown job"}\n\n']


@pytest.mark.asyncio
async def test_job_events_reads_a_changed_snapshot_and_closes_the_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = iter(
        [
            {"status": "running", "step": "tsunami"},
            {"status": "completed", "step": "tsunami"},
        ]
    )
    connection = _FakeAsyncConnection(notify=True)

    async def status(_simulation_id: str) -> dict[str, Any]:
        return next(snapshots)

    async def connect(*args: Any, **kwargs: Any) -> _FakeAsyncConnection:
        return connection

    monkeypatch.setattr(routes, "_job_status", status)
    monkeypatch.setattr(routes_module.psycopg.AsyncConnection, "connect", connect)
    monkeypatch.setattr(routes_module.anyio, "current_time", lambda: 0.0)

    response = await routes.job_events(SIMULATION_ID)
    chunks = [chunk async for chunk in response.body_iterator]

    assert len(chunks) == 2
    assert '"status": "completed"' in chunks[1]
    assert connection.executed == ["LISTEN tsdhn_job_4cfe522f7e7d46e096ca7b98743fb9f5"]
    assert connection.closed


@pytest.mark.asyncio
async def test_job_events_sends_keepalive_when_state_does_not_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {"status": "running", "step": "tsunami"}
    connection = _FakeAsyncConnection(notify=False)
    snapshots = iter([snapshot, snapshot])
    clock = iter([0.0, 0.0, float("inf")])

    async def status(_simulation_id: str) -> dict[str, Any]:
        return next(snapshots)

    async def connect(*args: Any, **kwargs: Any) -> _FakeAsyncConnection:
        return connection

    monkeypatch.setattr(routes, "_job_status", status)
    monkeypatch.setattr(routes_module.psycopg.AsyncConnection, "connect", connect)
    monkeypatch.setattr(routes_module.anyio, "current_time", lambda: next(clock))

    response = await routes.job_events(SIMULATION_ID)
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks[-1] == ": keepalive\n\n"
    assert connection.closed


def test_legacy_simulations_endpoint_is_removed(client: TestClient) -> None:
    response = client.post(
        "/api/v1/simulations",
        headers=_auth(),
        json={"simulation_id": SIMULATION_ID, "input": SAMPLE},
    )
    assert response.status_code == 404


def test_public_error_does_not_leak_exception_message() -> None:
    leaky = FileNotFoundError(
        "[Errno 2] No such file or directory: "
        "'/home/dubu/picv-2025/jobs/f5171f2a/tsunami'"
    )

    with_step = repository._public_error(leaky, "tsunami")
    without_step = repository._public_error(leaky, None)

    assert with_step == "Simulation failed at step 'tsunami' (FileNotFoundError)"
    assert without_step == "Simulation failed (FileNotFoundError)"
    for message in (with_step, without_step):
        assert "/home/" not in message
        assert "jobs" not in message
