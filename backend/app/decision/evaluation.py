"""Batch decision-policy evaluation, shared by evaluate_decisions.py and
evaluate_locked_decisions.py so both scripts compute buckets identically.

Everything here operates on already-computed probabilities/amounts/evidence
flags -- it does not touch the database or re-run the LightGBM model, and it
does not fit or tune anything. It is read-only summarization.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.decision.config import DecisionConfig
from app.decision.policy import evaluate_case
from app.decision.schema import DECISION_CONTEST, DECISION_DO_NOT_CONTEST, DECISION_HUMAN_REVIEW, DECISIONS


def batch_decide(
    dispute_ids: pd.Index,
    calibrated_probability: np.ndarray,
    dispute_amount: pd.Series,
    missing_high_relevance: pd.Series,
    config: DecisionConfig,
) -> pd.DataFrame:
    """Apply the Phase 3 decision policy to every case in a split.

    One evaluate_case() call per row -- pure Python-level math, no model
    inference here (probabilities are precomputed by the caller), so this is
    fast even at tens of thousands of rows.
    """
    records = []
    for dispute_id, probability, amount, has_gap in zip(
        dispute_ids, calibrated_probability, dispute_amount.to_numpy(), missing_high_relevance.to_numpy()
    ):
        missing = ["evidence_gap"] if has_gap else []
        payload = evaluate_case(float(probability), float(amount), missing, config)
        records.append(
            {
                "dispute_id": dispute_id,
                "decision": payload["decision"],
                "evidence_gap_downgrade": payload["evidence_gap_downgrade"],
                "calibrated_probability": payload["calibrated_probability"],
                "dispute_amount": payload["dispute_amount"],
                "recoverable_amount": payload["recoverable_amount"],
                "expected_recovery": payload["expected_recovery"],
                "expected_net_value": payload["expected_net_value"],
            }
        )
    return pd.DataFrame(records).set_index("dispute_id")


def missing_high_relevance_flags(evidence: pd.DataFrame, dispute_ids: pd.Index) -> pd.Series:
    """Per-dispute boolean: is at least one high-relevance evidence type unavailable?

    Vectorized equivalent of what scoring_service.py's `_evidence_summary`
    computes per-case from ORM rows -- here computed once for a whole split
    directly from the evidence CSV/table.
    """
    working = evidence.copy()
    availability = working["available"]
    if availability.dtype != bool:
        availability = availability.astype(str).map({"True": True, "False": False}).fillna(False)
    is_high = working["relevance"].astype(str) == "high"
    gap_rows = working.loc[is_high & ~availability, "dispute_id"]
    flagged = set(gap_rows)
    return pd.Series([dispute_id in flagged for dispute_id in dispute_ids], index=dispute_ids)


def summarize_buckets(
    decisions: pd.DataFrame,
    y_true: pd.Series,
    config: DecisionConfig,
    policy_label: str,
) -> dict:
    """Per-bucket economics + a portfolio-level realized-vs-expected comparison.

    "Expected" numbers come from the policy's own probability-based math.
    "Realized" numbers use the actual favorable_outcome labels -- this is an
    offline evaluation against known ground truth, so we can honestly check
    how the policy's expectations compare to what actually happened.
    """
    n_total = len(decisions)
    y = y_true.reindex(decisions.index).to_numpy(dtype=float)
    decisions = decisions.copy()
    decisions["favorable_outcome"] = y

    buckets: dict[str, dict] = {}
    for label in DECISIONS:
        subset = decisions[decisions["decision"] == label]
        count = len(subset)
        realized_recovery = float(
            (subset["recoverable_amount"] * subset["favorable_outcome"]).sum()
        )
        contest_cost_total = config.contest_cost * count if label == DECISION_CONTEST else 0.0
        buckets[label] = {
            "count": count,
            "percentage": round(100.0 * count / n_total, 2) if n_total else 0.0,
            "actual_favorable_outcome_rate": (
                round(float(subset["favorable_outcome"].mean()), 4) if count else None
            ),
            "expected_recovery_total": round(float(subset["expected_recovery"].sum()), 2),
            "expected_net_value_total": round(float(subset["expected_net_value"].sum()), 2),
            "realized_recovery_total": round(realized_recovery, 2),
            "estimated_contest_cost_total": round(contest_cost_total, 2),
            "realized_net_value_total": round(realized_recovery - contest_cost_total, 2),
            "evidence_gap_downgrades": int(subset["evidence_gap_downgrade"].sum()) if "evidence_gap_downgrade" in subset else 0,
        }

    contest_bucket = buckets.get(DECISION_CONTEST, {})
    return {
        "policy": policy_label,
        "n_total": n_total,
        "buckets": buckets,
        "portfolio": {
            "total_expected_net_value": round(
                sum(b["expected_net_value_total"] for b in buckets.values()), 2
            ),
            "contest_only_expected_net_value": contest_bucket.get("expected_net_value_total", 0.0),
            "contest_only_realized_net_value": contest_bucket.get("realized_net_value_total", 0.0),
            "contest_volume": contest_bucket.get("count", 0),
            "review_volume": buckets.get(DECISION_HUMAN_REVIEW, {}).get("count", 0),
            "do_not_contest_volume": buckets.get(DECISION_DO_NOT_CONTEST, {}).get("count", 0),
        },
    }


# ---------------------------------------------------------------------------
# Baselines (spec §15) -- simple, honest, not tuned to look weak
# ---------------------------------------------------------------------------

BASELINE_PROBABILITY_THRESHOLD = 0.5
BASELINE_EVIDENCE_COMPLETENESS_THRESHOLD = 0.7


def baseline_contest_everything(dispute_ids: pd.Index) -> pd.Series:
    """Baseline A: contest every single case, no policy at all."""
    return pd.Series(DECISION_CONTEST, index=dispute_ids)


def baseline_probability_threshold(
    calibrated_probability: np.ndarray, dispute_ids: pd.Index, threshold: float = BASELINE_PROBABILITY_THRESHOLD
) -> pd.Series:
    """Baseline B: contest iff P(win) >= threshold. No economics, no review band."""
    decisions = np.where(calibrated_probability >= threshold, DECISION_CONTEST, DECISION_DO_NOT_CONTEST)
    return pd.Series(decisions, index=dispute_ids)


def baseline_evidence_completeness(
    high_relevance_completeness_ratio: pd.Series,
    threshold: float = BASELINE_EVIDENCE_COMPLETENESS_THRESHOLD,
) -> pd.Series:
    """Baseline C: contest iff enough of the relevant evidence is on file.
    No probability, no economics -- pure evidence-completeness heuristic."""
    decisions = np.where(
        high_relevance_completeness_ratio.to_numpy() >= threshold, DECISION_CONTEST, DECISION_DO_NOT_CONTEST
    )
    return pd.Series(decisions, index=high_relevance_completeness_ratio.index)


def summarize_simple_policy(
    decisions: pd.Series,
    calibrated_probability: np.ndarray,
    dispute_amount: pd.Series,
    y_true: pd.Series,
    config: DecisionConfig,
    policy_label: str,
) -> dict:
    """Same bucket summary as summarize_buckets, for a baseline that only
    outputs a decision label (no per-case EV breakdown of its own) -- EV is
    still computed using the SAME probability/amount/cost model as the main
    policy, so the comparison is apples-to-apples."""
    recoverable = dispute_amount * config.recovery_rate
    recovery = calibrated_probability * recoverable.to_numpy()
    net_value = recovery - config.contest_cost

    frame = pd.DataFrame(
        {
            "decision": decisions,
            "calibrated_probability": calibrated_probability,
            "dispute_amount": dispute_amount,
            "recoverable_amount": recoverable,
            "expected_recovery": recovery,
            "expected_net_value": net_value,
            "evidence_gap_downgrade": False,
        },
        index=decisions.index,
    )
    return summarize_buckets(frame, y_true, config, policy_label)
