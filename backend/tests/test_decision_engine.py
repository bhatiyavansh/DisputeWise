"""Tests for the pure expected-value math in app/decision/engine.py."""

import math

import pytest

from app.decision.config import DecisionConfig
from app.decision.engine import (
    InvalidCaseInputError,
    break_even_probability,
    compute_breakdown,
    expected_net_value,
    expected_recovery,
    recoverable_amount,
    sensitivity_curve,
)


@pytest.fixture()
def config() -> DecisionConfig:
    return DecisionConfig(contest_cost=300.0, recovery_rate=1.0)


# ---------------------------------------------------------------------------
# Core arithmetic
# ---------------------------------------------------------------------------


def test_recoverable_amount():
    assert recoverable_amount(10000, 1.0) == 10000
    assert recoverable_amount(10000, 0.5) == 5000
    assert recoverable_amount(10000, 0.0) == 0


def test_expected_recovery():
    assert expected_recovery(0.82, 10000) == pytest.approx(8200)


def test_expected_net_value():
    assert expected_net_value(8200, 300) == pytest.approx(7900)
    assert expected_net_value(220, 300) == pytest.approx(-80)


def test_break_even_probability():
    probability, explanation = break_even_probability(300, 10000)
    assert probability == pytest.approx(0.03)
    assert "3.0%" in explanation


def test_break_even_probability_zero_recoverable():
    probability, explanation = break_even_probability(300, 0)
    assert probability is None
    assert "zero" in explanation.lower()


def test_break_even_probability_exceeds_one():
    """contest_cost > recoverable_amount -- no probability makes it worthwhile."""
    probability, explanation = break_even_probability(1000, 500)
    assert probability == 2.0
    assert "exceeds 100%" in explanation


# ---------------------------------------------------------------------------
# compute_breakdown (the full pipeline)
# ---------------------------------------------------------------------------


def test_compute_breakdown_matches_worked_example(config):
    breakdown = compute_breakdown(0.82, 10000, config)
    assert breakdown.recoverable_amount == pytest.approx(10000)
    assert breakdown.expected_recovery == pytest.approx(8200)
    assert breakdown.expected_net_value == pytest.approx(7900)
    assert breakdown.break_even_probability == pytest.approx(0.03)


def test_compute_breakdown_negative_example(config):
    breakdown = compute_breakdown(0.55, 400, config)
    assert breakdown.expected_recovery == pytest.approx(220)
    assert breakdown.expected_net_value == pytest.approx(-80)


def test_compute_breakdown_with_partial_recovery_rate():
    config = DecisionConfig(contest_cost=300, recovery_rate=0.9)
    breakdown = compute_breakdown(0.9, 1000, config)
    assert breakdown.recoverable_amount == pytest.approx(900)
    assert breakdown.expected_recovery == pytest.approx(810)


# ---------------------------------------------------------------------------
# Edge cases (section 10 of the spec)
# ---------------------------------------------------------------------------


def test_zero_dispute_amount_handled(config):
    breakdown = compute_breakdown(0.9, 0.0, config)
    assert breakdown.recoverable_amount == 0.0
    assert breakdown.expected_recovery == 0.0
    assert breakdown.expected_net_value == -config.contest_cost
    assert breakdown.break_even_probability is None


def test_negative_amount_rejected(config):
    with pytest.raises(InvalidCaseInputError, match="negative"):
        compute_breakdown(0.9, -100.0, config)


def test_missing_amount_rejected(config):
    with pytest.raises(InvalidCaseInputError, match="missing"):
        compute_breakdown(0.9, None, config)


def test_zero_recovery_rate_handled():
    config = DecisionConfig(contest_cost=300, recovery_rate=0.0)
    breakdown = compute_breakdown(0.9, 10000, config)
    assert breakdown.recoverable_amount == 0.0
    assert breakdown.expected_net_value == -300.0


def test_zero_contest_cost_handled():
    config = DecisionConfig(contest_cost=0.0, recovery_rate=1.0)
    breakdown = compute_breakdown(0.5, 1000, config)
    assert breakdown.expected_net_value == pytest.approx(500.0)
    assert breakdown.break_even_probability == 0.0


def test_missing_probability_rejected(config):
    with pytest.raises(InvalidCaseInputError, match="missing"):
        compute_breakdown(None, 1000, config)


def test_nan_probability_rejected(config):
    with pytest.raises(InvalidCaseInputError, match="NaN"):
        compute_breakdown(float("nan"), 1000, config)


def test_probability_below_zero_rejected(config):
    with pytest.raises(InvalidCaseInputError, match=r"\[0, 1\]"):
        compute_breakdown(-0.1, 1000, config)


def test_probability_above_one_rejected(config):
    with pytest.raises(InvalidCaseInputError, match=r"\[0, 1\]"):
        compute_breakdown(1.1, 1000, config)


def test_nan_amount_rejected(config):
    with pytest.raises(InvalidCaseInputError, match="NaN"):
        compute_breakdown(0.9, float("nan"), config)


def test_extremely_large_amount_handled(config):
    breakdown = compute_breakdown(0.5, 10_000_000_000.0, config)
    assert math.isfinite(breakdown.expected_net_value)
    assert breakdown.expected_recovery == pytest.approx(5_000_000_000.0)


def test_probability_boundaries_accepted(config):
    assert compute_breakdown(0.0, 1000, config).expected_recovery == 0.0
    assert compute_breakdown(1.0, 1000, config).expected_recovery == 1000.0


# ---------------------------------------------------------------------------
# Sensitivity analysis (explainability only)
# ---------------------------------------------------------------------------


def test_sensitivity_curve_is_monotonic_in_probability():
    points = sensitivity_curve(0.5, 10000, 300)
    values = [p["expected_net_value"] for p in points]
    assert values == sorted(values)


def test_sensitivity_curve_clips_to_valid_probability_range():
    points = sensitivity_curve(0.95, 10000, 300, deltas=(-0.1, 0.0, 0.1, 0.2))
    assert all(0.0 <= p["probability"] <= 1.0 for p in points)
    # 0.95+0.1 and 0.95+0.2 both clip to 1.0 -- duplicates collapsed
    probabilities = [p["probability"] for p in points]
    assert len(probabilities) == len(set(probabilities))


def test_sensitivity_curve_does_not_affect_decision():
    """The sensitivity curve is presentational; it must never feed back into
    compute_breakdown's own numbers."""
    config = DecisionConfig()
    breakdown = compute_breakdown(0.82, 10000, config)
    # the exact-probability point in the curve must equal the headline numbers
    exact = next(p for p in breakdown.sensitivity if p["probability"] == pytest.approx(0.82))
    assert exact["expected_net_value"] == pytest.approx(breakdown.expected_net_value)
