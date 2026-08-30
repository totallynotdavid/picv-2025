"""Authentication for requests from the SvelteKit server to the compute API."""

import os
import secrets

from fastapi import Header, HTTPException, status


def require_compute_api_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected = os.environ.get("COMPUTE_API_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Compute API token not configured",
        )

    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()

    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing compute API token",
        )
