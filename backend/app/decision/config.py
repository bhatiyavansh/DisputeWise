"""Central, validated configuration for the Phase 3 decision policy.

Every economic assumption used by the decision engine lives here -- nothing
is hardcoded elsewhere in app/decision/. All defaults below are PROTOTYPE
ASSUMPTIONS for this buildathon submission, not verified Razorpay production
economics. See docs/phase3.md for the full transparency statement.

Override any field with an environment variable prefixed DISPUTEWISE_, e.g.:

    DISPUTEWISE_CONTEST_COST=450
    DISPUTEWISE_RECOVERY_RATE=0.9
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DecisionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DISPUTEWISE_", env_file=".env", extra="ignore")

    # --- cost model -----------------------------------------------------
    contest_cost: float = 300.0
    """Flat estimated cost (currency units matching dispute_amount, i.e. INR
    in this dataset) of preparing and submitting a contest: operational time,
    evidence assembly, network/processor fees. PROTOTYPE ASSUMPTION -- a
    single flat number, not itemized (no per-network-fee or per-evidence-type
    cost breakdown; see docs/phase3.md for why this is deliberately simple)."""

    recovery_rate: float = 1.0
    """Fraction of dispute_amount actually recoverable if the contest is won
    (0.0-1.0). Real-world recovery is rarely 100% of face value once
    processor/network fees are netted out; 1.0 is the simplest possible
    prototype assumption, made explicit rather than hidden. PROTOTYPE
    ASSUMPTION."""

    # --- decision thresholds ---------------------------------------------
    min_expected_net_value: float = 0.0
    """The expected_net_value an eligible CONTEST must clear. Also the
    reference point review_margin is measured from."""

    review_margin: float = 50.0
    """Width of the "too close to call on economics alone" band, in currency
    units, straddling min_expected_net_value. A case whose expected_net_value
    falls within [min_expected_net_value - review_margin,
    min_expected_net_value + review_margin) can never be a firm CONTEST or
    DO_NOT_CONTEST -- it is always routed to HUMAN_REVIEW, regardless of
    model confidence."""

    high_confidence_probability: float = 0.65
    """Minimum calibrated_probability required (in addition to a clearly
    positive expected_net_value) for a CONTEST recommendation."""

    low_confidence_probability: float = 0.35
    """Maximum calibrated_probability allowed (in addition to a clearly
    negative expected_net_value) for a DO_NOT_CONTEST recommendation."""

    # --- evidence-aware routing -------------------------------------------
    require_high_relevance_evidence_for_contest: bool = True
    """If true, a CONTEST recommendation is downgraded to HUMAN_REVIEW when
    one or more high-relevance evidence types (per this case's reason code)
    are missing entirely. Rationale: a CONTEST recommendation asks a human to
    spend contest_cost on the strength of evidence that, per Phase 1's own
    evidence taxonomy, doesn't exist for the type of dispute this is -- no
    matter how confident the model is from other signals (customer history,
    amount, etc). This is the ONE evidence-based override in the policy; it
    only ever downgrades CONTEST -> HUMAN_REVIEW, never the reverse, and it
    never touches DO_NOT_CONTEST or the probability itself. It does not
    duplicate the LightGBM model -- it reads the same evidence_summary the
    /score endpoint already returns."""

    sensitivity_deltas: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10)
    """Probability offsets reported in the sensitivity-analysis explainability
    surface. Presentational only -- never used to change the decision."""

    # --- validation ---------------------------------------------------------
    @field_validator("contest_cost")
    @classmethod
    def _contest_cost_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError(f"contest_cost must be >= 0, got {value}")
        return value

    @field_validator("recovery_rate")
    @classmethod
    def _recovery_rate_in_range(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"recovery_rate must be in [0, 1] (a fraction of dispute_amount), got {value}")
        return value

    @field_validator("review_margin")
    @classmethod
    def _review_margin_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError(f"review_margin must be >= 0, got {value}")
        return value

    @field_validator("high_confidence_probability", "low_confidence_probability")
    @classmethod
    def _probability_threshold_in_range(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"probability thresholds must be in [0, 1], got {value}")
        return value

    @model_validator(mode="after")
    def _thresholds_are_ordered(self) -> "DecisionConfig":
        if self.high_confidence_probability <= self.low_confidence_probability:
            raise ValueError(
                "high_confidence_probability "
                f"({self.high_confidence_probability}) must be strictly greater than "
                f"low_confidence_probability ({self.low_confidence_probability})"
            )
        return self


@lru_cache
def get_decision_config() -> DecisionConfig:
    return DecisionConfig()
