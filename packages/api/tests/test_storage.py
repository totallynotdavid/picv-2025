from pathlib import Path
from typing import Any

import pytest
from minio.error import MinioException

from api.core.errors import TransientInfraError
from api.core.storage import OutputStore
from tsdhn.engine import OutputFile, SimulationOutputs


class _RaisingMinioClient:
    def bucket_exists(self, bucket_name: str) -> bool:
        return True

    def fput_object(self, **kwargs: object) -> None:
        raise MinioException("simulated MinIO outage")


class _RaisingPresignClient:
    def presigned_get_object(self, **kwargs: object) -> str:
        raise MinioException("simulated MinIO outage")


class _RecordingMinioClient:
    def __init__(self) -> None:
        self.created_bucket = False
        self.uploads: list[dict[str, Any]] = []
        self.metadata_uploads: list[dict[str, Any]] = []
        self.presign: dict[str, Any] | None = None

    def bucket_exists(self, bucket_name: str) -> bool:
        return self.created_bucket

    def make_bucket(self, bucket_name: str) -> None:
        self.created_bucket = True

    def fput_object(self, **kwargs: Any) -> None:
        self.uploads.append(kwargs)

    def put_object(self, **kwargs: Any) -> None:
        payload = kwargs["data"].read()
        self.metadata_uploads.append({**kwargs, "payload": payload})

    def presigned_get_object(self, **kwargs: Any) -> str:
        self.presign = kwargs
        return "https://minio.example/signed"


def test_upload_simulation_result_wraps_minio_failure(tmp_path: Path) -> None:
    store = OutputStore.__new__(OutputStore)
    store.bucket = "tsdhn-results"
    store._client = _RaisingMinioClient()  # type: ignore[assignment]

    output_path = tmp_path / "maxola.pdf"
    output_path.write_bytes(b"%PDF-1.4\n")
    outputs = SimulationOutputs(
        root=tmp_path,
        files=(OutputFile("max_height_map", output_path, "application/pdf"),),
    )

    with pytest.raises(TransientInfraError):
        store.upload_simulation_result(
            simulation_id="job-1",
            compute_job_id="compute-1",
            outputs=outputs,
            metadata={},
        )


def test_presigned_url_wraps_minio_failure() -> None:
    store = OutputStore.__new__(OutputStore)
    store.bucket = "tsdhn-results"
    store._public_client = _RaisingPresignClient()  # type: ignore[assignment]

    with pytest.raises(TransientInfraError, match="presigning output URL failed"):
        store.presigned_url("simulations/job-1/result.pdf", filename="result.pdf")


def test_upload_simulation_result_creates_bucket_and_persists_manifest(
    tmp_path: Path,
) -> None:
    store = OutputStore.__new__(OutputStore)
    store.bucket = "tsdhn-results"
    client = _RecordingMinioClient()
    store._client = client  # type: ignore[assignment]

    output_path = tmp_path / "maxola.pdf"
    output_path.write_bytes(b"pdf")
    outputs = SimulationOutputs(
        root=tmp_path,
        files=(OutputFile("max_height_map", output_path, "application/pdf"),),
    )

    bucket, metadata_key = store.upload_simulation_result(
        simulation_id="job-1",
        compute_job_id="compute-1",
        outputs=outputs,
        metadata={"status": "completed"},
    )

    assert (bucket, metadata_key) == (
        "tsdhn-results",
        "simulations/job-1/metadata.json",
    )
    assert client.created_bucket
    assert client.uploads[0]["object_name"] == ("simulations/job-1/outputs/maxola.pdf")
    assert client.uploads[0]["metadata"] == {
        "simulation-id": "job-1",
        "compute-job-id": "compute-1",
        "output-name": "max_height_map",
    }
    assert client.metadata_uploads[0]["payload"] == b'{"status":"completed"}'
    assert client.metadata_uploads[0]["content_type"] == "application/json"


def test_presigned_url_uses_public_storage_and_download_filename() -> None:
    store = OutputStore.__new__(OutputStore)
    store.bucket = "tsdhn-results"
    client = _RecordingMinioClient()
    store._public_client = client  # type: ignore[assignment]

    url = store.presigned_url("simulations/job-1/result.pdf", filename="result.pdf")

    assert url == "https://minio.example/signed"
    assert client.presign is not None
    assert client.presign["bucket_name"] == "tsdhn-results"
    assert client.presign["object_name"] == "simulations/job-1/result.pdf"
    assert client.presign["response_headers"] == {
        "response-content-disposition": 'attachment; filename="result.pdf"'
    }
