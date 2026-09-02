"""The three-way CONTEST / HUMAN_REVIEW / DO_NOT_CONTEST decision policy.

Deliberately simple: two threshold checks (economic + confidence), one
evidence-based override that only ever downgrades CONTEST, and a
deterministic, templated explanation string. No ML, no LLM, no learned
weights -- every branch is auditable by reading this file.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decision.config import DecisionConfig
from app.decision.engine import ExpectedValueBreakdown, compute_breakdown
from app.decision.schema import (
    DECISION_CONTEST,
    DECISION_DO_NOT_CONTEST,
    DECISION_HUMAN_REVIEW,
    DECISION_POLICY_VERSION,
    DISCLAIMER,
)


@dataclass(frozen=True)
class PolicyResult:
    decision: str
    reason: str
    evidence_gap_downgrade: bool


def _is_clearly_positive(net_value: float, config: DecisionConfig) -> bool:
    return net_value >= config.min_expected_net_value + config.review_margin


def _is_clearly_negative(net_value: float, config: DecisionConfig) -> bool:
    return net_value < config.min_expected_net_value - config.review_margin


def decide(
    breakdown: ExpectedValueBreakdown,
    config: DecisionConfig,
    missing_high_relevance_evidence: list[str] | None = None,
) -> PolicyResult:
    """Apply the decision policy to one case's expected-value breakdown.

    Primary signal is expected_net_value; calibrated_probability is a
    secondary CONFIDENCE gate on top of it (a case is never recommended for
    CONTEST purely because the model is confident, nor purely because the
    economics look good -- both must hold). Everything in between is
    HUMAN_REVIEW by construction.
    """
    probability = breakdown.calibrated_probability
    net_value = breakdown.expected_net_value
    missing_high_relevance_evidence = missing_high_relevance_evidence or []

    clearly_positive = _is_clearly_positive(net_value, config)
    clearly_negative = _is_clearly_negative(net_value, config)
    confident_win = probability >= config.high_confidence_probability
    confident_loss = probability <= config.low_confidence_probability

    if clearly_positive and confident_win:
        if config.require_high_relevance_evidence_for_contest and missing_high_relevance_evidence:
            return PolicyResult(
                decision=DECISION_HUMAN_REVIEW,
                reason=(
                    f"Economics and model confidence both favor contesting (expected net value "
                    f"{net_value:+.2f}, P(win)={probability:.0%}), but key evidence for this "
                    f"reason code is missing on file ({', '.join(missing_high_relevance_evidence)}). "
                    "Routed to human review rather than recommending CONTEST on evidence that may "
                    "not actually exist to submit."
                ),
                evidence_gap_downgrade=True,
            )
        return PolicyResult(
            decision=DECISION_CONTEST,
            reason=(
                f"Expected recovery materially exceeds estimated contest cost "
                f"(expected net value {net_value:+.2f}) and the model is confident of a favorable "
                f"outcome (P(win)={probability:.0%})."
            ),
            evidence_gap_downgrade=False,
        )

    if clearly_negative and confident_loss:
        return PolicyResult(
            decision=DECISION_DO_NOT_CONTEST,
            reason=(
                f"Expected recovery does not justify estimated contest cost "
                f"(expected net value {net_value:+.2f}), and the model has low confidence in a "
                f"favorable outcome (P(win)={probability:.0%})."
            ),
            evidence_gap_downgrade=False,
        )

    reasons = []
    if not (clearly_positive or clearly_negative):
        reasons.append("expected net value is close to the decision boundary")
    if clearly_positive and not confident_win:
        reasons.append(f"economics favor contesting but model confidence ({probability:.0%}) is not high enough")
    if clearly_negative and not confident_loss:
        reasons.append(
            f"economics disfavor contesting but the model is not confident enough of a loss "
            f"({probability:.0%}) to rule it out"
        )

    return PolicyResult(
        decision=DECISION_HUMAN_REVIEW,
        reason="Routed to human review: " + "; ".join(reasons) + ".",
        evidence_gap_downgrade=False,
    )


def evaluate_case(
    calibrated_probability: float,
    dispute_amount: float,
    missing_high_relevance_evidence: list[str] | None,
    config: DecisionConfig,
) -> dict:
    """The single entrypoint both the API and offline scripts call.

    Combines the deterministic economic breakdown (engine.py) with the
    decision policy (this module) into one dict, so there is exactly one
    code path from (probability, amount, evidence) to a decision -- no
    duplicated glue logic between the API service and the evaluation
    scripts.
    """
    breakdown = compute_breakdown(calibrated_probability, dispute_amount, config)
    result = decide(breakdown, config, missing_high_relevance_evidence)

    return {
        "decision_policy_version": DECISION_POLICY_VERSION,
        "decision": result.decision,
        "reason": result.reason,
        "evidence_gap_downgrade": result.evidence_gap_downgrade,
        "disclaimer": DISCLAIMER,
        **breakdown.to_dict(),
    }
