import json
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

import urllib3
from minio import Minio
from minio.error import MinioException

from api.core.errors import TransientInfraError
from api.core.settings import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    OUTPUT_URL_TTL,
)
from tsdhn.engine import SimulationOutputs

__all__ = ["OutputStore", "output_store"]


class OutputStore:
    def __init__(self) -> None:
        self.bucket = MINIO_BUCKET
        self._client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
            http_client=urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=2.0, read=2.0),
                retries=False,
            ),
        )
        # Browser downloads may use a different endpoint from MinIO uploads.
        self._public_client = Minio(
            MINIO_PUBLIC_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )

    def is_connected(self) -> bool:
        try:
            self._client.bucket_exists(self.bucket)
            return True
        except Exception:
            return False

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def upload_simulation_result(
        self,
        *,
        simulation_id: str,
        compute_job_id: str,
        outputs: SimulationOutputs,
        metadata: dict[str, Any],
    ) -> tuple[str, str]:
        prefix = f"simulations/{simulation_id}"
        metadata_key = f"{prefix}/metadata.json"

        try:
            self.ensure_bucket()

            for output in outputs.files:
                self._client.fput_object(
                    bucket_name=self.bucket,
                    object_name=f"{prefix}/outputs/{output.path.name}",
                    file_path=str(output.path),
                    content_type=output.content_type,
                    metadata={
                        "simulation-id": simulation_id,
                        "compute-job-id": compute_job_id,
                        "output-name": output.name,
                    },
                )

            payload = json.dumps(
                metadata, ensure_ascii=True, separators=(",", ":")
            ).encode("utf-8")
            self._client.put_object(
                bucket_name=self.bucket,
                object_name=metadata_key,
                data=BytesIO(payload),
                length=len(payload),
                content_type="application/json",
            )
        except (MinioException, urllib3.exceptions.HTTPError, OSError) as e:
            # Storage outages are transient. Let the task retry the upload.
            raise TransientInfraError("output upload failed") from e

        return self.bucket, metadata_key

    def presigned_url(self, object_name: str, *, filename: str) -> str:
        """Return a short-lived URL for downloading an output file."""
        try:
            return self._public_client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=timedelta(seconds=OUTPUT_URL_TTL),
                response_headers={
                    "response-content-disposition": (
                        f'attachment; filename="{filename}"'
                    )
                },
            )
        except (MinioException, urllib3.exceptions.HTTPError, OSError) as e:
            raise TransientInfraError("presigning output URL failed") from e


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


output_store = OutputStore()
