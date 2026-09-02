"""Validation tests for DecisionConfig."""

import pytest
from pydantic import ValidationError

from app.decision.config import DecisionConfig


def test_default_config_is_valid():
    config = DecisionConfig()
    assert config.contest_cost == 300.0
    assert config.recovery_rate == 1.0
    assert config.high_confidence_probability > config.low_confidence_probability


def test_valid_custom_config_accepted():
    config = DecisionConfig(contest_cost=500, recovery_rate=0.9, high_confidence_probability=0.7, low_confidence_probability=0.3)
    assert config.contest_cost == 500
    assert config.recovery_rate == 0.9


@pytest.mark.parametrize("recovery_rate", [-0.1, 1.5, 2.0])
def test_invalid_recovery_rate_rejected(recovery_rate):
    with pytest.raises(ValidationError, match="recovery_rate"):
        DecisionConfig(recovery_rate=recovery_rate)


def test_recovery_rate_boundaries_accepted():
    assert DecisionConfig(recovery_rate=0.0).recovery_rate == 0.0
    assert DecisionConfig(recovery_rate=1.0).recovery_rate == 1.0


def test_invalid_contest_cost_rejected():
    with pytest.raises(ValidationError, match="contest_cost"):
        DecisionConfig(contest_cost=-1.0)


def test_zero_contest_cost_accepted():
    assert DecisionConfig(contest_cost=0.0).contest_cost == 0.0


def test_invalid_review_margin_rejected():
    with pytest.raises(ValidationError, match="review_margin"):
        DecisionConfig(review_margin=-5.0)


@pytest.mark.parametrize("field", ["high_confidence_probability", "low_confidence_probability"])
def test_invalid_probability_threshold_rejected(field):
    with pytest.raises(ValidationError, match="probability thresholds"):
        DecisionConfig(**{field: 1.5})
    with pytest.raises(ValidationError, match="probability thresholds"):
        DecisionConfig(**{field: -0.1})


def test_inverted_thresholds_rejected():
    """high_confidence_probability must exceed low_confidence_probability."""
    with pytest.raises(ValidationError, match="must be strictly greater"):
        DecisionConfig(high_confidence_probability=0.3, low_confidence_probability=0.6)


def test_equal_thresholds_rejected():
    with pytest.raises(ValidationError, match="must be strictly greater"):
        DecisionConfig(high_confidence_probability=0.5, low_confidence_probability=0.5)


def test_env_var_override(monkeypatch):
    monkeypatch.setenv("DISPUTEWISE_CONTEST_COST", "750")
    monkeypatch.setenv("DISPUTEWISE_RECOVERY_RATE", "0.85")
    config = DecisionConfig()
    assert config.contest_cost == 750.0
    assert config.recovery_rate == 0.85


def test_get_decision_config_is_cached():
    from app.decision.config import get_decision_config

    assert get_decision_config() is get_decision_config()
