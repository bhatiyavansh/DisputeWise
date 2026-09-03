"""Phase 7C -- GET /portfolio/summary.

Portfolio-level aggregation, computed server-side from the same scored split
the policy playground uses, under the production decision-v1 policy. The
browser never loads per-case rows to compute these.

Every number here is derived from real data. Where a figure cannot be
computed honestly it is simply absent rather than estimated -- in particular
there is no "recovery to date", "SLA", or "team throughput" metric, because
nothing in this dataset supports one.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import numpy as np
import pandas as pd

from app.api.scoring import get_risk_model
from app.decision.config import get_decision_config
from app.decision.evaluation import batch_decide
from app.decision.schema import DECISIONS, DECISION_POLICY_VERSION
from app.ml.model import RiskModel
from app.services.portfolio_service import get_scored_portfolio

router = APIRouter(tags=["portfolio"], prefix="/portfolio")

NOTE = (
    "Aggregated from the validation split under the production decision-v1 policy. "
    "Expected figures are model-based projections using PROTOTYPE cost assumptions; realized "
    "figures are retrospective, computed against known historical outcomes for this split."
)

PROBABILITY_BANDS = (
    ("0-20%", 0.0, 0.2),
    ("20-40%", 0.2, 0.4),
    ("40-60%", 0.4, 0.6),
    ("60-80%", 0.6, 0.8),
    ("80-100%", 0.8, 1.0001),
)

EVIDENCE_BANDS = (
    ("complete", 1.0, 1.0001),
    ("partial", 0.5, 1.0),
    ("sparse", 0.0, 0.5),
)


class BucketSummary(BaseModel):
    decision: str
    count: int
    percentage: float
    total_amount: float
    expected_recovery: float
    expected_net_value: float
    actual_favorable_outcome_rate: float | None
    evidence_gap_downgrades: int


class GroupSummary(BaseModel):
    key: str
    count: int
    total_amount: float
    mean_probability: float


class PortfolioSummaryResponse(BaseModel):
    split: str
    n_cases: int
    total_disputed_amount: float
    total_expected_recovery: float
    total_expected_net_value: float
    contest_only_expected_net_value: float
    contest_only_realized_net_value: float
    mean_calibrated_probability: float
    cases_with_missing_high_relevance_evidence: int

    decisions: list[BucketSummary]
    by_reason_code: list[GroupSummary]
    by_probability_band: list[GroupSummary]
    by_evidence_completeness: list[GroupSummary]

    model_version: str
    feature_schema_version: str
    decision_policy_version: str
    note: str


def _group(keys: pd.Series, amounts: pd.Series, probability: pd.Series) -> list[GroupSummary]:
    frame = pd.DataFrame({"key": keys, "amount": amounts, "probability": probability})
    grouped = frame.groupby("key", dropna=False).agg(
        count=("amount", "size"), total_amount=("amount", "sum"), mean_probability=("probability", "mean")
    )
    return [
        GroupSummary(
            key=str(key),
            count=int(row["count"]),
            total_amount=round(float(row["total_amount"]), 2),
            mean_probability=round(float(row["mean_probability"]), 4),
        )
        for key, row in grouped.sort_values("total_amount", ascending=False).iterrows()
    ]


def _banded(
    values: pd.Series, bands, amounts: pd.Series, probability: pd.Series
) -> list[GroupSummary]:
    labels = pd.Series(index=values.index, dtype=object)
    for label, low, high in bands:
        labels[(values >= low) & (values < high)] = label
    labels = labels.fillna("unknown")
    ordered = [label for label, _, _ in bands]
    summaries = {summary.key: summary for summary in _group(labels, amounts, probability)}
    return [summaries[label] for label in ordered if label in summaries]


@router.get("/summary", response_model=PortfolioSummaryResponse)
def portfolio_summary(model: RiskModel = Depends(get_risk_model)) -> PortfolioSummaryResponse:
    """Portfolio-level risk and routing, aggregated server-side.

    Uses the production decision-v1 policy (the playground's hypothetical
    policies never affect this view) and the validation split, never the
    locked test set.
    """
    try:
        portfolio = get_scored_portfolio(model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Portfolio data is not available: {exc}")

    config = get_decision_config()
    decisions = batch_decide(
        portfolio.dispute_ids,
        portfolio.calibrated_probability,
        portfolio.dispute_amount,
        portfolio.missing_high_relevance,
        config,
    )
    decisions = decisions.assign(favorable_outcome=portfolio.favorable_outcome.reindex(decisions.index))

    n_total = len(decisions)
    probability = pd.Series(portfolio.calibrated_probability, index=portfolio.dispute_ids)

    buckets: list[BucketSummary] = []
    for label in DECISIONS:
        subset = decisions[decisions["decision"] == label]
        count = len(subset)
        buckets.append(
            BucketSummary(
                decision=label,
                count=count,
                percentage=round(100.0 * count / n_total, 2) if n_total else 0.0,
                total_amount=round(float(subset["dispute_amount"].sum()), 2),
                expected_recovery=round(float(subset["expected_recovery"].sum()), 2),
                expected_net_value=round(float(subset["expected_net_value"].sum()), 2),
                actual_favorable_outcome_rate=(
                    round(float(subset["favorable_outcome"].mean()), 4) if count else None
                ),
                evidence_gap_downgrades=int(subset["evidence_gap_downgrade"].sum()) if count else 0,
            )
        )

    contested = decisions[decisions["decision"] == "CONTEST"]
    contest_realized = float((contested["recoverable_amount"] * contested["favorable_outcome"]).sum())
    contest_cost_total = config.contest_cost * len(contested)

    return PortfolioSummaryResponse(
        split=portfolio.split,
        n_cases=n_total,
        total_disputed_amount=round(float(portfolio.dispute_amount.sum()), 2),
        total_expected_recovery=round(float(decisions["expected_recovery"].sum()), 2),
        total_expected_net_value=round(float(decisions["expected_net_value"].sum()), 2),
        # What the policy would actually capture: only contested cases can
        # recover anything, and each incurs the contest cost.
        contest_only_expected_net_value=round(float(contested["expected_net_value"].sum()), 2),
        contest_only_realized_net_value=round(contest_realized - contest_cost_total, 2),
        mean_calibrated_probability=round(float(np.mean(portfolio.calibrated_probability)), 4),
        cases_with_missing_high_relevance_evidence=int(portfolio.missing_high_relevance.sum()),
        decisions=buckets,
        by_reason_code=_group(portfolio.reason_code, portfolio.dispute_amount, probability),
        by_probability_band=_banded(
            probability, PROBABILITY_BANDS, portfolio.dispute_amount, probability
        ),
        by_evidence_completeness=_banded(
            portfolio.high_relevance_completeness, EVIDENCE_BANDS, portfolio.dispute_amount, probability
        ),
        model_version=portfolio.model_version,
        feature_schema_version=portfolio.feature_schema_version,
        decision_policy_version=DECISION_POLICY_VERSION,
        note=NOTE,
    )
