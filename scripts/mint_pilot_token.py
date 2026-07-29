#!/usr/bin/env python3
"""Mint HS256 pilot JWTs for closed-pilot customers.

Each client gets its own tenant_id / project_id so ledger records stay
scope-tagged. Tokens are signed with PHIGRAPH_JWT_SECRET (or --secret).

Example:
  set PHIGRAPH_JWT_SECRET=...
  python scripts/mint_pilot_token.py --subject acme-ops --tenant tenant-acme --days 90
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from typing import Any


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_token(
    *,
    secret: str,
    subject: str,
    tenant_id: str,
    project_id: str,
    role: str,
    issuer: str,
    audience: str,
    ttl_seconds: int,
) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    h = _b64(json.dumps(header, separators=(",", ":")).encode())
    p = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(
        hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    )
    return f"{h}.{p}.{sig}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True, help="Client subject id")
    parser.add_argument("--tenant", required=True, help="tenant_id claim")
    parser.add_argument("--project", default="pilot", help="project_id claim")
    parser.add_argument(
        "--role",
        default="operator",
        choices=["viewer", "operator", "verifier", "admin"],
        help="RBAC role embedded in the token",
    )
    parser.add_argument("--days", type=int, default=90, help="Token lifetime")
    parser.add_argument(
        "--secret",
        default=os.getenv("PHIGRAPH_JWT_SECRET"),
        help="HS256 secret (default: PHIGRAPH_JWT_SECRET)",
    )
    parser.add_argument(
        "--issuer",
        default=os.getenv("PHIGRAPH_JWT_ISSUER", "phigraph-pilot"),
    )
    parser.add_argument(
        "--audience",
        default=os.getenv("PHIGRAPH_JWT_AUDIENCE", "phigraph-api"),
    )
    args = parser.parse_args(argv)

    if not args.secret:
        print("error: provide --secret or set PHIGRAPH_JWT_SECRET", file=sys.stderr)
        return 2
    if args.days <= 0 or args.days > 365:
        print("error: --days must be between 1 and 365", file=sys.stderr)
        return 2

    token = mint_token(
        secret=args.secret,
        subject=args.subject,
        tenant_id=args.tenant,
        project_id=args.project,
        role=args.role,
        issuer=args.issuer,
        audience=args.audience,
        ttl_seconds=args.days * 86400,
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
