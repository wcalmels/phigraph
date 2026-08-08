from __future__ import annotations

import os

from phigraph.core_v3.service import CoreV3Service
from phigraph.deployment.config import DeploymentSettings


def resolve_receipt_signing_key(settings: DeploymentSettings) -> str | None:
    return os.getenv("PHIGRAPH_RECEIPT_SIGNING_KEY")


def require_receipt_signing_key(settings: DeploymentSettings) -> str | None:
    key = resolve_receipt_signing_key(settings)
    if settings.environment in {"staging", "production"} and not key:
        raise ValueError("PHIGRAPH_RECEIPT_SIGNING_KEY is required for staging/production")
    return key


def build_core_service(settings: DeploymentSettings) -> CoreV3Service:
    receipt_signing_key = require_receipt_signing_key(settings)
    return CoreV3Service(
        data_dir=settings.data_dir,
        receipt_signing_key=receipt_signing_key,
    )
