from __future__ import annotations

from dataclasses import dataclass


DERIVED_EQUIVALENCE = "DERIVED_EQUIVALENCE"
CONDITIONAL_EQUIVALENCE = "CONDITIONAL_EQUIVALENCE"
DIMENSIONAL_MATCH_ONLY = "DIMENSIONAL_MATCH_ONLY"
NO_EQUIVALENCE = "NO_EQUIVALENCE"


@dataclass(frozen=True)
class EquivalenceEvidence:
    """Evidence used to assess whether two independently derived objects are equivalent.

    The gate is intentionally fail-closed. Equal dimensions are not sufficient for
    equivalence. For subspaces, promotion requires projector identity plus compatible
    operator evidence and independent provenance.
    """

    claim_id: str
    left_origin: str
    right_origin: str
    left_target_informed: bool = False
    right_target_informed: bool = False
    dimension_match: bool = False
    projector_overlap_trace: float | None = None
    expected_rank: int | None = None
    projector_difference_residual: float | None = None
    operator_commutator_residual: float | None = None


@dataclass(frozen=True)
class EquivalenceAssessment:
    claim_id: str
    status: str
    evidence_class: str
    independent_origins: bool
    projector_exact: bool
    commutation_ok: bool
    promotion_allowed: bool
    tolerance: float

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "independent_origins": self.independent_origins,
            "projector_exact": self.projector_exact,
            "commutation_ok": self.commutation_ok,
            "promotion_allowed": self.promotion_allowed,
            "tolerance": self.tolerance,
        }


def assess_equivalence(
    evidence: EquivalenceEvidence,
    *,
    tolerance: float = 1e-8,
) -> EquivalenceAssessment:
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")

    independent = (
        evidence.left_origin != evidence.right_origin
        and not evidence.left_target_informed
        and not evidence.right_target_informed
    )

    projector_exact = (
        evidence.projector_overlap_trace is not None
        and evidence.expected_rank is not None
        and evidence.projector_difference_residual is not None
        and abs(evidence.projector_overlap_trace - evidence.expected_rank) < tolerance
        and evidence.projector_difference_residual < tolerance
    )

    commutation_ok = (
        evidence.operator_commutator_residual is None
        or evidence.operator_commutator_residual < tolerance
    )

    if independent and projector_exact and commutation_ok:
        status = DERIVED_EQUIVALENCE
        evidence_class = "INDEPENDENT_CONSTRUCTION_PROJECTOR_IDENTITY"
        promotion_allowed = True
    elif projector_exact and commutation_ok:
        status = CONDITIONAL_EQUIVALENCE
        evidence_class = "PROJECTOR_IDENTITY_ORIGIN_DEPENDENCE_NOT_CLOSED"
        promotion_allowed = False
    elif evidence.dimension_match:
        status = DIMENSIONAL_MATCH_ONLY
        evidence_class = "INSUFFICIENT_FOR_EQUIVALENCE"
        promotion_allowed = False
    else:
        status = NO_EQUIVALENCE
        evidence_class = "NO_STRUCTURAL_MATCH"
        promotion_allowed = False

    return EquivalenceAssessment(
        claim_id=evidence.claim_id,
        status=status,
        evidence_class=evidence_class,
        independent_origins=independent,
        projector_exact=projector_exact,
        commutation_ok=commutation_ok,
        promotion_allowed=promotion_allowed,
        tolerance=tolerance,
    )


def equivalence_provenance_edges(evidence: EquivalenceEvidence) -> tuple[dict, ...]:
    """Return PhiGraph-ready provenance relations for an equivalence claim."""

    edges = [
        {
            "src": evidence.left_origin,
            "dst": evidence.claim_id,
            "relation": "independent_derivation_left",
        },
        {
            "src": evidence.right_origin,
            "dst": evidence.claim_id,
            "relation": "independent_derivation_right",
        },
        {
            "src": evidence.claim_id,
            "dst": "promotion_gate",
            "relation": "requires_projector_identity",
        },
    ]
    if evidence.left_target_informed:
        edges.append(
            {
                "src": evidence.left_origin,
                "dst": evidence.claim_id,
                "relation": "target_informed_by",
            }
        )
    if evidence.right_target_informed:
        edges.append(
            {
                "src": evidence.right_origin,
                "dst": evidence.claim_id,
                "relation": "target_informed_by",
            }
        )
    return tuple(edges)
