"""Frozen public PhiGraph protocol for the 4.0 release line.

The symbols exported here form the compatibility contract for 4.x. Internal
implementations may move, but these names and serialized field semantics must
remain backward compatible throughout the major release.
"""
from phigraph.core_v3.models import (
    ActionProposal, Claim, ClaimStatus, DecisionEffect, Evidence,
    EvidenceStatus, Outcome, PolicyDecision, RuntimeMode, Verification,
)

PROTOCOL_NAME = "phigraph-protocol"
from phigraph.version import CORE_VERSION, PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_NAME", "PROTOCOL_VERSION", "CORE_VERSION",
    "Claim", "ClaimStatus", "Evidence", "EvidenceStatus", "Verification",
    "ActionProposal", "PolicyDecision", "DecisionEffect", "Outcome", "RuntimeMode",
]
