from phigraph.governance import (
    CONDITIONAL_EQUIVALENCE,
    DERIVED_EQUIVALENCE,
    DIMENSIONAL_MATCH_ONLY,
    EquivalenceEvidence,
    assess_equivalence,
    equivalence_provenance_edges,
)


def test_dimension_match_alone_fails_closed():
    evidence = EquivalenceEvidence(
        claim_id="candidate",
        left_origin="geometry",
        right_origin="representation",
        dimension_match=True,
    )

    result = assess_equivalence(evidence)

    assert result.status == DIMENSIONAL_MATCH_ONLY
    assert result.evidence_class == "INSUFFICIENT_FOR_EQUIVALENCE"
    assert result.independent_origins
    assert not result.projector_exact
    assert not result.promotion_allowed


def test_independent_projector_identity_promotes_structurally():
    evidence = EquivalenceEvidence(
        claim_id="joint-block-16",
        left_origin="h4_joint_spectrum",
        right_origin="2i_character_decomposition",
        dimension_match=True,
        projector_overlap_trace=16.0,
        expected_rank=16,
        projector_difference_residual=3e-14,
        operator_commutator_residual=5e-13,
    )

    result = assess_equivalence(evidence)

    assert result.status == DERIVED_EQUIVALENCE
    assert result.projector_exact
    assert result.commutation_ok
    assert result.promotion_allowed


def test_target_informed_projector_match_is_conditional():
    evidence = EquivalenceEvidence(
        claim_id="target-informed",
        left_origin="geometry",
        right_origin="representation",
        right_target_informed=True,
        dimension_match=True,
        projector_overlap_trace=4.0,
        expected_rank=4,
        projector_difference_residual=1e-13,
    )

    result = assess_equivalence(evidence)

    assert result.status == CONDITIONAL_EQUIVALENCE
    assert not result.independent_origins
    assert not result.promotion_allowed


def test_bad_commutator_blocks_projector_promotion():
    evidence = EquivalenceEvidence(
        claim_id="incompatible-operators",
        left_origin="geometry",
        right_origin="representation",
        dimension_match=True,
        projector_overlap_trace=16.0,
        expected_rank=16,
        projector_difference_residual=1e-13,
        operator_commutator_residual=1e-2,
    )

    result = assess_equivalence(evidence)

    assert result.status == DIMENSIONAL_MATCH_ONLY
    assert result.projector_exact
    assert not result.commutation_ok
    assert not result.promotion_allowed


def test_equivalence_provenance_edges_are_explicit():
    evidence = EquivalenceEvidence(
        claim_id="equivalence-claim",
        left_origin="route-a",
        right_origin="route-b",
        right_target_informed=True,
    )

    edges = equivalence_provenance_edges(evidence)
    relations = {edge["relation"] for edge in edges}

    assert "independent_derivation_left" in relations
    assert "independent_derivation_right" in relations
    assert "requires_projector_identity" in relations
    assert "target_informed_by" in relations
