from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_hav_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("PHIGRAPH_HAV_API_KEY")
    if not expected:
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid HAV API key")
