"""Tests for the three-way decision policy in app/decision/policy.py."""

import pytest

from app.decision.config import DecisionConfig
from app.decision.engine import compute_breakdown
from app.decision.policy import decide, evaluate_case
from app.decision.schema import DECISION_CONTEST, DECISION_DO_NOT_CONTEST, DECISION_HUMAN_REVIEW


@pytest.fixture()
def config() -> DecisionConfig:
    return DecisionConfig(
        contest_cost=300.0,
        recovery_rate=1.0,
        min_expected_net_value=0.0,
        review_margin=50.0,
        high_confidence_probability=0.65,
        low_confidence_probability=0.35,
    )


def _decide(probability, amount, config, missing_evidence=None):
    breakdown = compute_breakdown(probability, amount, config)
    return decide(breakdown, config, missing_evidence)


def test_clearly_positive_ev_and_high_confidence_yields_contest(config):
    result = _decide(0.90, 10000, config)
    assert result.decision == DECISION_CONTEST
    assert "materially exceeds" in result.reason


def test_clearly_negative_ev_and_low_confidence_yields_do_not_contest(config):
    result = _decide(0.10, 500, config)
    assert result.decision == DECISION_DO_NOT_CONTEST
    assert "does not justify" in result.reason


def test_near_zero_ev_yields_human_review(config):
    """Expected net value within the review_margin band is always HUMAN_REVIEW."""
    # contest_cost=300, amount chosen so EV lands inside [-50, +50)
    result = _decide(0.90, 333.33, config)  # EV = 0.9*333.33 - 300 ≈ 0.0
    assert result.decision == DECISION_HUMAN_REVIEW
    assert "boundary" in result.reason


def test_positive_ev_but_low_confidence_yields_human_review(config):
    """Good economics alone is not sufficient without model confidence."""
    result = _decide(0.50, 10000, config)  # EV clearly positive, P=0.5 is neither confident nor low
    assert result.decision == DECISION_HUMAN_REVIEW
    assert "confidence" in result.reason


def test_negative_ev_but_not_low_confidence_yields_human_review(config):
    """Bad economics alone does not trigger a firm rejection without low confidence."""
    result = _decide(0.60, 100, config)  # EV negative, but P=0.6 isn't <= low_confidence_probability
    assert result.decision == DECISION_HUMAN_REVIEW


def test_decision_depends_on_expected_value_not_probability_alone(config):
    """A high probability on a tiny amount must not automatically CONTEST."""
    result = _decide(0.99, 100, config)  # EV = 99 - 300 = -201: clearly negative
    assert result.decision != DECISION_CONTEST


def test_low_probability_high_amount_is_not_automatically_contest(config):
    result = _decide(0.20, 100000, config)  # big EV, but P=0.2 too low for CONTEST... wait EV positive
    # EV = 0.2*100000-300 = 19700 (clearly positive) but confidence (0.20) is actually "low"
    # -> not confident_win, not confident_loss's threshold direction (EV positive) -> human review
    assert result.decision == DECISION_HUMAN_REVIEW


# ---------------------------------------------------------------------------
# Evidence-aware downgrade
# ---------------------------------------------------------------------------


def test_missing_high_relevance_evidence_downgrades_contest(config):
    result = _decide(0.90, 10000, config, missing_evidence=["proof_of_delivery"])
    assert result.decision == DECISION_HUMAN_REVIEW
    assert result.evidence_gap_downgrade is True
    assert "proof_of_delivery" in result.reason


def test_complete_evidence_does_not_downgrade(config):
    result = _decide(0.90, 10000, config, missing_evidence=[])
    assert result.decision == DECISION_CONTEST
    assert result.evidence_gap_downgrade is False


def test_evidence_gap_never_downgrades_do_not_contest(config):
    """The evidence gate only ever touches CONTEST, never DO_NOT_CONTEST."""
    result = _decide(0.10, 500, config, missing_evidence=["proof_of_delivery", "tracking_available"])
    assert result.decision == DECISION_DO_NOT_CONTEST
    assert result.evidence_gap_downgrade is False


def test_evidence_gap_never_upgrades_human_review_to_contest(config):
    result = _decide(0.50, 10000, config, missing_evidence=[])  # would be HUMAN_REVIEW anyway
    assert result.decision == DECISION_HUMAN_REVIEW


def test_evidence_requirement_can_be_disabled():
    config = DecisionConfig(require_high_relevance_evidence_for_contest=False)
    result = _decide(0.90, 10000, config, missing_evidence=["proof_of_delivery"])
    assert result.decision == DECISION_CONTEST
    assert result.evidence_gap_downgrade is False


# ---------------------------------------------------------------------------
# evaluate_case (the combined entrypoint)
# ---------------------------------------------------------------------------


def test_evaluate_case_returns_full_breakdown(config):
    payload = evaluate_case(0.82, 10000, [], config)
    expected_keys = {
        "decision_policy_version",
        "decision",
        "reason",
        "evidence_gap_downgrade",
        "disclaimer",
        "calibrated_probability",
        "dispute_amount",
        "recovery_rate",
        "recoverable_amount",
        "contest_cost",
        "expected_recovery",
        "expected_net_value",
        "break_even_probability",
        "break_even_explanation",
        "sensitivity",
    }
    assert expected_keys <= set(payload)
    assert payload["decision_policy_version"] == "decision-v1"


def test_evaluate_case_deterministic(config):
    first = evaluate_case(0.82, 10000, ["proof_of_delivery"], config)
    second = evaluate_case(0.82, 10000, ["proof_of_delivery"], config)
    assert first == second


def test_evaluate_case_same_config_same_result_object_equality(config):
    """Same case + same config -> same decision AND same calculations (spec §18)."""
    payload_a = evaluate_case(0.75, 5000, [], config)
    payload_b = evaluate_case(0.75, 5000, [], config)
    assert payload_a["decision"] == payload_b["decision"]
    assert payload_a["expected_net_value"] == payload_b["expected_net_value"]
    assert payload_a["break_even_probability"] == payload_b["break_even_probability"]


def test_evaluate_case_different_config_can_change_decision():
    """Sanity check that the config actually matters -- proves it isn't ignored."""
    lenient = DecisionConfig(contest_cost=10.0, high_confidence_probability=0.5, low_confidence_probability=0.2)
    strict = DecisionConfig(contest_cost=5000.0, high_confidence_probability=0.9, low_confidence_probability=0.1)

    lenient_result = evaluate_case(0.6, 1000, [], lenient)
    strict_result = evaluate_case(0.6, 1000, [], strict)

    assert lenient_result["decision"] == DECISION_CONTEST
    assert strict_result["decision"] != DECISION_CONTEST
