"""PhiGraph Core v3 canonical protocol and governed runtime."""
from .models import (
    Claim, ClaimStatus, Evidence, EvidenceStatus, Verification,
    ActionProposal, PolicyDecision, DecisionEffect, Outcome, RuntimeMode,
)
from .ledger import EvidenceLedger
from .policy import PolicyRule, PolicyEngine
from .adapters import AgentAdapter, AgentProposal, StaticAgentAdapter
from .runtime import PhiGraphCoreRuntime, RuntimeReport
from .service import CoreV3Service
from .integrations import LegacyBridge, LegacyIntegrationPaths

__all__ = [
    "Claim", "ClaimStatus", "Evidence", "EvidenceStatus", "Verification",
    "ActionProposal", "PolicyDecision", "DecisionEffect", "Outcome", "RuntimeMode",
    "EvidenceLedger", "PolicyRule", "PolicyEngine", "AgentAdapter", "AgentProposal",
    "StaticAgentAdapter", "PhiGraphCoreRuntime", "RuntimeReport", "CoreV3Service",
    "LegacyBridge", "LegacyIntegrationPaths", "LedgerBackend", "JsonLedgerBackend",
    "SQLiteLedgerBackend", "PostgreSQLLedgerBackend", "IdempotencyStore",
    "LockKind", "LockRef", "ScopedRecordResult", "CompareAndSetResult",
    "LedgerError", "DuplicateCanonicalKey", "ScopedRecordNotFound",
    "VersionConflict", "TransactionUnavailable", "LedgerIntegrityError",
    "UndeclaredLockRef",
    "canonical_scoped_payload_hash",
]

from .backends import PostgreSQLLedgerBackend, LedgerBackend, JsonLedgerBackend, SQLiteLedgerBackend
from .transactions import (
    CompareAndSetResult,
    DuplicateCanonicalKey,
    LedgerError,
    LedgerIntegrityError,
    LockKind,
    LockRef,
    ScopedRecordNotFound,
    ScopedRecordResult,
    TransactionUnavailable,
    UndeclaredLockRef,
    VersionConflict,
    canonical_scoped_payload_hash,
)
from .idempotency import IdempotencyStore

from .code_benchmark import (
    AgentReport,
    CodeVerifier,
    GitHubRepositoryDescriptor,
    PhiGraphCodeBenchmark,
    RepositoryIndexer,
)
