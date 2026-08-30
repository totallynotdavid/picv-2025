import json
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

import urllib3
from minio import Minio

from api.core.settings import (
    ARTIFACT_URL_TTL,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
)
from tsdhn.engine import ArtifactBundle

__all__ = ["ArtifactStore", "artifact_store"]


class ArtifactStore:
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
        # Presigned URLs are handed to a browser, so they must be signed
        # against the endpoint the browser can reach -- not the in-cluster
        # one this process dials. Signing is offline (no request is made),
        # so this second client never needs to connect.
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
        app_job_id: str,
        compute_job_id: str,
        bundle: ArtifactBundle,
        metadata: dict[str, Any],
    ) -> tuple[str, str]:
        self.ensure_bucket()

        prefix = f"simulations/{app_job_id}"
        metadata_key = f"{prefix}/metadata.json"

        for artifact in bundle.artifacts:
            self._client.fput_object(
                bucket_name=self.bucket,
                object_name=f"{prefix}/artifacts/{artifact.path.name}",
                file_path=str(artifact.path),
                content_type=artifact.content_type,
                metadata={
                    "app-job-id": app_job_id,
                    "compute-job-id": compute_job_id,
                    "artifact-name": artifact.name,
                },
            )

        payload = json.dumps(metadata, ensure_ascii=True, separators=(",", ":")).encode(
            "utf-8"
        )
        self._client.put_object(
            bucket_name=self.bucket,
            object_name=metadata_key,
            data=BytesIO(payload),
            length=len(payload),
            content_type="application/json",
        )

        return self.bucket, metadata_key

    def presigned_url(self, object_name: str, *, filename: str) -> str:
        """A time-limited GET URL a browser can follow directly.

        This is how artifacts reach users: the control plane checks
        ownership and redirects here, so report PDFs never stream through
        the Node process or through FastAPI. `response-content-disposition`
        makes the browser save the file under its artifact name rather than
        the object key's basename.
        """
        try:
            return self._public_client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=timedelta(seconds=ARTIFACT_URL_TTL),
                response_headers={
                    "response-content-disposition": (
                        f'attachment; filename="{filename}"'
                    )
                },
            )
        except (MinioException, urllib3.exceptions.HTTPError, OSError) as e:
            raise TransientInfraError("presigning artifact URL failed") from e


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


artifact_store = ArtifactStore()
