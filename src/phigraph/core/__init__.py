"""Stable PhiGraph Core public API.

Import application code from ``phigraph.core`` rather than ``phigraph.core_v3``.
The legacy package remains available during the 4.x migration window.
"""
from phigraph.protocol import *  # noqa: F401,F403
from phigraph.core_v3 import (
    AgentAdapter, AgentProposal, CoreV3Service, EvidenceLedger,
    JsonLedgerBackend, LedgerBackend, LegacyBridge, LegacyIntegrationPaths,
    PhiGraphCoreRuntime, PolicyEngine, PolicyRule, PostgreSQLLedgerBackend,
    RuntimeReport, SQLiteLedgerBackend, StaticAgentAdapter,
)

CoreService = CoreV3Service
CoreRuntime = PhiGraphCoreRuntime

__all__ = [
    "CoreService", "CoreRuntime", "CoreV3Service", "PhiGraphCoreRuntime",
    "RuntimeReport", "EvidenceLedger", "PolicyRule", "PolicyEngine",
    "AgentAdapter", "AgentProposal", "StaticAgentAdapter", "LedgerBackend",
    "JsonLedgerBackend", "SQLiteLedgerBackend", "PostgreSQLLedgerBackend",
    "LegacyBridge", "LegacyIntegrationPaths",
]
