"""Constants and versioning for the Phase 3 decision policy.

Mirrors the pattern established by app/ml/schema.py: one module holding
every version string, enum value, and default so nothing is scattered across
the codebase.
"""

from __future__ import annotations

DECISION_POLICY_VERSION = "decision-v1"

DECISION_CONTEST = "CONTEST"
DECISION_HUMAN_REVIEW = "HUMAN_REVIEW"
DECISION_DO_NOT_CONTEST = "DO_NOT_CONTEST"
DECISIONS = (DECISION_CONTEST, DECISION_HUMAN_REVIEW, DECISION_DO_NOT_CONTEST)

# Probability offsets used for the sensitivity-analysis explainability surface
# (see docs/phase3.md §9). Purely presentational -- never used to change the
# decision itself.
SENSITIVITY_PROBABILITY_DELTAS: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10)

DISCLAIMER = (
    "Decision support only, not an instruction to act: no dispute is submitted, contested, or "
    "otherwise acted upon automatically. This is an economic recommendation based on prototype "
    "cost assumptions (see docs/phase3.md) for a human reviewer to weigh."
)
