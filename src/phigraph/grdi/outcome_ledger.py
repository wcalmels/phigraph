from __future__ import annotations

from phigraph.grdi.models import EffectAssessment, EffectAssessmentState, ShadowOutcomeState

OUTCOME_ORIGIN_SHADOW = "SHADOW_SIMULATION"


def validate_effect_assessments(assessments: tuple[EffectAssessment, ...]) -> None:
    if not assessments:
        raise ValueError("effect_assessments_required")
    seen: set[str] = set()
    for assessment in assessments:
        effect = assessment.expected_effect.strip()
        if not effect:
            raise ValueError("expected_effect_required")
        if not assessment.simulated_observation.strip():
            raise ValueError("simulated_observation_required")
        if effect in seen:
            raise ValueError("duplicate_expected_effect")
        seen.add(effect)


def aggregate_outcome_state(
    expected_effects: tuple[str, ...],
    assessments: tuple[EffectAssessment, ...],
) -> ShadowOutcomeState:
    if not expected_effects:
        return ShadowOutcomeState.NOT_EVALUATED

    assessment_effects = [assessment.expected_effect for assessment in assessments]
    if len(assessment_effects) != len(set(assessment_effects)):
        return ShadowOutcomeState.NOT_EVALUATED

    expected_set = set(expected_effects)
    if set(assessment_effects) != expected_set:
        return ShadowOutcomeState.NOT_EVALUATED

    if any(assessment.state is EffectAssessmentState.NOT_EVALUATED for assessment in assessments):
        return ShadowOutcomeState.NOT_EVALUATED

    if any(assessment.state is EffectAssessmentState.DEVIATED for assessment in assessments):
        return ShadowOutcomeState.DEVIATED

    if all(assessment.state is EffectAssessmentState.MATCHED for assessment in assessments):
        return ShadowOutcomeState.CONSISTENT

    return ShadowOutcomeState.NOT_EVALUATED
