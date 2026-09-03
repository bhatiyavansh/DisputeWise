"""Phases 7B/7C -- one scored portfolio, shared by the policy playground and
the portfolio risk view.

Scores a whole split ONCE (features -> risk-v1 -> calibration) and caches the
result in memory. Both callers then only re-run the decision policy, which is
pure Python-level arithmetic per case (app/decision/evaluation.py's
batch_decide) -- so changing a policy parameter re-routes the portfolio
without any model inference at all.

WHICH SPLIT, AND WHY NOT THE LOCKED TEST SET
--------------------------------------------
These are interactive tools: the playground exists so a user can move
thresholds and watch routing change. Doing that against the locked test set
-- while its realized outcomes are on screen -- is threshold tuning against
the held-out benchmark, which is exactly what Phase 2/3 were careful not to
do. So both tools default to the VALIDATION split, the split whose purpose
is decision-making, and every response says which split it summarizes.

The locked test set stays reserved for `scripts/evaluate_locked_test.py` and
`scripts/evaluate_locked_decisions.py`, which read it once for the official
number. Nothing here writes to any split.

SHAP is deliberately not computed here (predict_calibrated, not score_cases):
portfolio aggregates never need per-case attributions, and computing them for
thousands of cases would be slow for no benefit.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from app.decision.evaluation import missing_high_relevance_flags
from app.ml.data import load_split
from app.ml.features import build_features, extract_target
from app.ml.model import RiskModel

DEFAULT_SPLIT = "validation"


@dataclass(frozen=True)
class ScoredPortfolio:
    """A whole split, scored once. Read-only."""

    split: str
    dispute_ids: pd.Index
    calibrated_probability: np.ndarray
    dispute_amount: pd.Series
    reason_code: pd.Series
    missing_high_relevance: pd.Series
    #: Ground-truth labels, present only for retrospective evaluation. Never
    #: an input to scoring or to any decision -- see summarize_buckets.
    favorable_outcome: pd.Series
    #: Per-case share of this reason code's high-relevance evidence on file.
    high_relevance_completeness: pd.Series
    model_version: str
    feature_schema_version: str

    @property
    def n_cases(self) -> int:
        return len(self.dispute_ids)


def _high_relevance_completeness(evidence: pd.DataFrame, dispute_ids: pd.Index) -> pd.Series:
    """Fraction of each case's high-relevance evidence types that are on file.

    Mirrors the ratio scoring_service's evidence_summary reports per case
    (high_relevance_available / high_relevance_total), computed once for a
    whole split.
    """
    working = evidence.copy()
    availability = working["available"]
    if availability.dtype != bool:
        availability = availability.astype(str).map({"True": True, "False": False}).fillna(False)
    working["_available"] = availability
    high = working[working["relevance"].astype(str) == "high"]

    if high.empty:
        return pd.Series(1.0, index=dispute_ids)

    grouped = high.groupby("dispute_id")["_available"].agg(["sum", "count"])
    ratio = (grouped["sum"] / grouped["count"]).reindex(dispute_ids)
    return ratio.fillna(1.0)


def score_portfolio(split: str, model: RiskModel) -> ScoredPortfolio:
    """Score one split end to end. Not cached -- see get_scored_portfolio."""
    data = load_split(split)
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)

    probability = model.predict_calibrated(features)
    dispute_ids = features.index

    disputes = data.disputes.set_index("dispute_id").reindex(dispute_ids)

    return ScoredPortfolio(
        split=split,
        dispute_ids=dispute_ids,
        calibrated_probability=probability,
        dispute_amount=pd.to_numeric(disputes["dispute_amount"], errors="coerce"),
        reason_code=disputes["reason_code"],
        missing_high_relevance=missing_high_relevance_flags(data.evidence, dispute_ids),
        # Labels come from the one function that is allowed to touch the
        # outcomes table, and only ever for retrospective reporting.
        favorable_outcome=extract_target(data.outcomes, dispute_ids),
        high_relevance_completeness=_high_relevance_completeness(data.evidence, dispute_ids),
        model_version=model.model_version,
        feature_schema_version=model.feature_schema_version,
    )


@lru_cache(maxsize=len(("train", "validation", "test")))
def _cached_portfolio(split: str, model_version: str) -> ScoredPortfolio:
    from app.ml.model import get_model

    return score_portfolio(split, get_model())


def get_scored_portfolio(model: RiskModel, split: str = DEFAULT_SPLIT) -> ScoredPortfolio:
    """Cached scored split. Keyed by model_version so reloading a different
    model artifact can never serve stale probabilities."""
    return _cached_portfolio(split, model.model_version)


def reset_portfolio_cache() -> None:
    _cached_portfolio.cache_clear()
