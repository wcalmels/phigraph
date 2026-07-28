from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import DeploymentSettings


def verify_api_key(
    settings: DeploymentSettings,
    x_api_key: str | None,
) -> None:
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
