from __future__ import annotations

import hmac

from fastapi import HTTPException, status

from .config import DeploymentSettings


def verify_api_key(
    settings: DeploymentSettings,
    x_api_key: str | None,
) -> None:
    """Reject requests when a deployment API key is configured but missing/wrong.

    Uses constant-time comparison. When no key is configured (local/dev),
    authentication is intentionally skipped.
    """
    expected = settings.api_key
    if not expected:
        return
    provided = x_api_key or ""
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
