"""Phase 7B -- decision policy playground.

Re-routes an already-scored portfolio under a HYPOTHETICAL policy config and
compares it to the production default.

This is not a new decision engine. It builds a DecisionConfig instance from
the requested overrides and hands it to the existing batch_decide() /
summarize_buckets() from app/decision/evaluation.py -- the same functions
`scripts/evaluate_decisions.py` uses. No threshold logic, no economics and no
bucket math is reimplemented here or in the frontend.

decision-v1's stored defaults are NEVER mutated: get_decision_config() is
lru_cached and returns the production config, so the playground constructs a
separate throwaway DecisionConfig instead of touching it. A test asserts the
production config is identical after a playground run.

The contest-everything baseline is included on purpose. At the prototype
contest cost of Rs.300 it can out-earn the default routing on realized value,
because contest cost is small relative to dispute value. That finding is
surfaced, not tuned away -- making policy sensitivity visible is the point of
the tool.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decision.config import DecisionConfig, get_decision_config
from app.decision.schema import DECISION_POLICY_VERSION
from app.decision.evaluation import (
    baseline_contest_everything,
    batch_decide,
    summarize_buckets,
    summarize_simple_policy,
)
from app.ml.model import RiskModel
from app.services.portfolio_service import DEFAULT_SPLIT, ScoredPortfolio, get_scored_portfolio

#: The only fields the playground may override. Everything else in
#: DecisionConfig (notably the evidence gate and sensitivity deltas) stays
#: exactly as decision-v1 defines it.
TUNABLE_FIELDS = (
    "contest_cost",
    "recovery_rate",
    "high_confidence_probability",
    "low_confidence_probability",
    "min_expected_net_value",
    "review_margin",
)

ECONOMICS_EXPLANATION = (
    "Expected recovery = P(win) x recoverable amount, where recoverable amount = "
    "dispute amount x recovery rate. Expected net value = expected recovery - contest cost. "
    "A case is only eligible for CONTEST if its expected net value clears the minimum by more "
    "than the review margin AND the model is at least high-confidence; the mirror condition "
    "applies to DO_NOT_CONTEST. Anything in between is routed to HUMAN_REVIEW."
)


@dataclass(frozen=True)
class PolicyComparison:
    split: str
    n_cases: int
    default_policy: dict
    scenario_policy: dict
    contest_everything_baseline: dict
    default_config: dict
    scenario_config: dict
    changed_fields: list[str]
    model_version: str
    feature_schema_version: str
    decision_policy_version: str


def build_scenario_config(overrides: dict) -> DecisionConfig:
    """A throwaway DecisionConfig with the requested overrides applied."""
    production = get_decision_config()
    applied = {field: value for field, value in overrides.items() if value is not None}
    unknown = sorted(set(applied) - set(TUNABLE_FIELDS))
    if unknown:
        raise ValueError(f"policy fields cannot be overridden here: {unknown}")

    # Constructing a fresh instance re-runs decision-v1's own field and model
    # validators (ranges, non-negative costs, threshold ordering), so invalid
    # playground input is rejected by the production rules rather than by a
    # second copy of them. The cached production instance is not touched.
    return DecisionConfig(**{**production.model_dump(), **applied})


def _summarize(portfolio: ScoredPortfolio, config: DecisionConfig, label: str) -> dict:
    decisions = batch_decide(
        portfolio.dispute_ids,
        portfolio.calibrated_probability,
        portfolio.dispute_amount,
        portfolio.missing_high_relevance,
        config,
    )
    return summarize_buckets(decisions, portfolio.favorable_outcome, config, label)


def compare_policies(
    overrides: dict,
    *,
    risk_model: RiskModel,
    split: str = DEFAULT_SPLIT,
) -> PolicyComparison:
    """Route the portfolio under production decision-v1 and under the
    hypothetical policy, plus the contest-everything baseline."""
    portfolio = get_scored_portfolio(risk_model, split)
    production = get_decision_config()
    scenario = build_scenario_config(overrides)

    changed = [
        field
        for field in TUNABLE_FIELDS
        if getattr(scenario, field) != getattr(production, field)
    ]

    baseline_decisions = baseline_contest_everything(portfolio.dispute_ids)

    return PolicyComparison(
        split=portfolio.split,
        n_cases=portfolio.n_cases,
        default_policy=_summarize(portfolio, production, "decision-v1 (production default)"),
        scenario_policy=_summarize(portfolio, scenario, "scenario policy"),
        contest_everything_baseline=summarize_simple_policy(
            baseline_decisions,
            portfolio.calibrated_probability,
            portfolio.dispute_amount,
            portfolio.favorable_outcome,
            scenario,
            "contest everything (baseline)",
        ),
        default_config={field: getattr(production, field) for field in TUNABLE_FIELDS},
        scenario_config={field: getattr(scenario, field) for field in TUNABLE_FIELDS},
        changed_fields=changed,
        model_version=portfolio.model_version,
        feature_schema_version=portfolio.feature_schema_version,
        decision_policy_version=DECISION_POLICY_VERSION,
    )
