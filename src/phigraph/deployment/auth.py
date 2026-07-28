from __future__ import annotations

from fastapi import Header, HTTPException, status

from phigraph.platform import Principal


def principal_from_headers(
    x_subject: str | None,
    x_roles: str | None,
) -> Principal:
    if not x_subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Subject header.",
        )
    roles = tuple(
        item.strip()
        for item in (x_roles or "viewer").split(",")
        if item.strip()
    )
    return Principal(subject=x_subject, roles=roles)
