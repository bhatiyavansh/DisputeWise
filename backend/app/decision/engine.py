"""Deterministic expected-value math for the Phase 3 decision engine.

Every function here is a pure function of its arguments -- no I/O, no model
inference, no randomness -- so the same case + same DecisionConfig always
produces the same numbers. The LightGBM model and its probability are an
input to this module, never recomputed by it (see docs/phase2.md /
docs/phase3.md: Phase 3 must not duplicate the Phase 2 model).

    calibrated_probability, dispute_amount, DecisionConfig
        -> recoverable_amount, expected_recovery, expected_net_value,
           break_even_probability, sensitivity curve
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.decision.config import DecisionConfig
from app.decision.schema import SENSITIVITY_PROBABILITY_DELTAS


class InvalidCaseInputError(ValueError):
    """Raised when the inputs to the economic model are not sane.

    Distinguished from DecisionConfig's pydantic ValidationError: this is
    about a specific CASE's probability/amount, not the policy configuration.
    """


def _validate_probability(calibrated_probability: float | None) -> float:
    if calibrated_probability is None:
        raise InvalidCaseInputError("calibrated_probability is missing")
    if isinstance(calibrated_probability, float) and math.isnan(calibrated_probability):
        raise InvalidCaseInputError("calibrated_probability is NaN")
    if not (0.0 <= calibrated_probability <= 1.0):
        raise InvalidCaseInputError(
            f"calibrated_probability must be in [0, 1], got {calibrated_probability}"
        )
    return float(calibrated_probability)


def _validate_amount(dispute_amount: float | None) -> float:
    if dispute_amount is None:
        raise InvalidCaseInputError("dispute_amount is missing")
    if isinstance(dispute_amount, float) and math.isnan(dispute_amount):
        raise InvalidCaseInputError("dispute_amount is NaN")
    if dispute_amount < 0:
        raise InvalidCaseInputError(f"dispute_amount cannot be negative, got {dispute_amount}")
    if not math.isfinite(dispute_amount):
        raise InvalidCaseInputError(f"dispute_amount must be finite, got {dispute_amount}")
    return float(dispute_amount)


@dataclass(frozen=True)
class ExpectedValueBreakdown:
    """Every intermediate number that produced expected_net_value.

    Nothing is hidden behind a single score -- each field here is surfaced
    directly in the /decision API response.
    """

    calibrated_probability: float
    dispute_amount: float
    recovery_rate: float
    recoverable_amount: float
    contest_cost: float
    expected_recovery: float
    expected_net_value: float
    break_even_probability: float | None
    break_even_explanation: str
    sensitivity: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "calibrated_probability": round(self.calibrated_probability, 6),
            "dispute_amount": round(self.dispute_amount, 2),
            "recovery_rate": self.recovery_rate,
            "recoverable_amount": round(self.recoverable_amount, 2),
            "contest_cost": round(self.contest_cost, 2),
            "expected_recovery": round(self.expected_recovery, 2),
            "expected_net_value": round(self.expected_net_value, 2),
            "break_even_probability": (
                round(self.break_even_probability, 6) if self.break_even_probability is not None else None
            ),
            "break_even_explanation": self.break_even_explanation,
            "sensitivity": self.sensitivity,
        }


def recoverable_amount(dispute_amount: float, recovery_rate: float) -> float:
    """The portion of the disputed amount actually recoverable if won.

    A documented, configurable recovery factor -- not the full dispute
    amount by assumption. See DecisionConfig.recovery_rate.
    """
    return dispute_amount * recovery_rate


def expected_recovery(calibrated_probability: float, amount_recoverable: float) -> float:
    return calibrated_probability * amount_recoverable


def expected_net_value(value_expected_recovery: float, contest_cost: float) -> float:
    return value_expected_recovery - contest_cost


def break_even_probability(contest_cost: float, amount_recoverable: float) -> tuple[float | None, str]:
    """The win probability at which expected_net_value crosses zero.

    break_even_probability = contest_cost / recoverable_amount

    Undefined (None) when recoverable_amount is zero -- there is no
    probability that makes a $0-recoverable case worth a positive-cost
    contest, so "break-even probability" has no meaningful value.
    """
    if amount_recoverable <= 0:
        return None, "Undefined: the recoverable amount is zero, so no win probability makes this worth contesting."

    probability = contest_cost / amount_recoverable
    if probability > 1.0:
        return (
            probability,
            f"Break-even probability ({probability:.1%}) exceeds 100% -- this case cannot be "
            "profitable to contest at any win probability under current cost assumptions.",
        )
    return (
        probability,
        f"At current assumptions, this case becomes economically positive above a "
        f"{probability:.1%} win probability.",
    )


def sensitivity_curve(
    calibrated_probability: float,
    amount_recoverable: float,
    contest_cost: float,
    deltas: tuple[float, ...] = SENSITIVITY_PROBABILITY_DELTAS,
) -> list[dict]:
    """Expected net value under nearby probability assumptions.

    Explainability surface only (see docs/phase3.md §9) -- never used to
    change the decision itself. Deltas that would push the probability
    outside [0, 1] are clipped, and duplicate resulting probabilities
    (e.g. multiple deltas clipping to 0.0) are collapsed.
    """
    seen: set[float] = set()
    points: list[dict] = []
    for delta in deltas:
        probability = min(1.0, max(0.0, calibrated_probability + delta))
        rounded = round(probability, 6)
        if rounded in seen:
            continue
        seen.add(rounded)
        recovery = expected_recovery(probability, amount_recoverable)
        points.append(
            {
                "probability": rounded,
                "delta": round(probability - calibrated_probability, 6),
                "expected_recovery": round(recovery, 2),
                "expected_net_value": round(expected_net_value(recovery, contest_cost), 2),
            }
        )
    return sorted(points, key=lambda p: p["probability"])


def compute_breakdown(
    calibrated_probability: float,
    dispute_amount: float,
    config: DecisionConfig,
) -> ExpectedValueBreakdown:
    """The full, deterministic economic breakdown for one case.

    Raises InvalidCaseInputError for garbage inputs (missing/NaN/out-of-range
    probability, missing/negative/non-finite amount) rather than silently
    computing nonsense. Degenerate-but-valid inputs (amount == 0,
    recovery_rate == 0, contest_cost == 0) are handled gracefully and never
    raise.
    """
    probability = _validate_probability(calibrated_probability)
    amount = _validate_amount(dispute_amount)

    recoverable = recoverable_amount(amount, config.recovery_rate)
    recovery = expected_recovery(probability, recoverable)
    net_value = expected_net_value(recovery, config.contest_cost)
    break_even, break_even_text = break_even_probability(config.contest_cost, recoverable)
    sensitivity = sensitivity_curve(probability, recoverable, config.contest_cost, config.sensitivity_deltas)

    return ExpectedValueBreakdown(
        calibrated_probability=probability,
        dispute_amount=amount,
        recovery_rate=config.recovery_rate,
        recoverable_amount=recoverable,
        contest_cost=config.contest_cost,
        expected_recovery=recovery,
        expected_net_value=net_value,
        break_even_probability=break_even,
        break_even_explanation=break_even_text,
        sensitivity=sensitivity,
    )
