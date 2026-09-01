"""Evidence-completeness baselines.

The point of a baseline is to answer: "does the model actually add value over
the obvious heuristic a merchant would use anyway?" That test is only
meaningful if the baseline is a genuinely fair attempt, so three variants are
computed and the STRONGEST is reported as the headline comparison rather than
the weakest.

All three are pure functions of the evidence already in the feature matrix --
no fitting, no labels, no tuning.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BASELINE_VARIANTS = {
    # naive: what fraction of all 16 evidence types is on file
    "overall_completeness": "evidence_completeness_ratio",
    # reason-code aware: what fraction of the evidence that MATTERS for this
    # dispute's reason code is on file (uses the per-row `relevance` recorded
    # in the evidence table, so it respects the same taxonomy the model sees)
    "high_relevance_completeness": "high_relevance_completeness_ratio",
    # strength-weighted: how strong the highly relevant evidence actually is
    "high_relevance_strength": "high_relevance_strength_mean",
}


def baseline_scores(features: pd.DataFrame) -> dict[str, np.ndarray]:
    """Compute every baseline variant as a [0, 1] score."""
    scores: dict[str, np.ndarray] = {}
    for name, column in BASELINE_VARIANTS.items():
        if column not in features.columns:
            raise ValueError(f"baseline '{name}' needs feature column '{column}'")
        values = features[column].to_numpy(dtype=float)
        # Missing high-relevance strength means no such evidence is on file,
        # which is the weakest possible state -> 0.0, not "unknown".
        scores[name] = np.nan_to_num(values, nan=0.0)
    return scores


def best_baseline(
    scores: dict[str, np.ndarray], y_true: np.ndarray
) -> tuple[str, np.ndarray, dict[str, float]]:
    """Pick the baseline variant with the highest ROC-AUC.

    Selecting the *best* baseline (rather than a convenient weak one) is
    deliberate: it makes the model-vs-baseline comparison honest.
    """
    from sklearn.metrics import roc_auc_score

    aucs = {name: float(roc_auc_score(y_true, score)) for name, score in scores.items()}
    winner = max(aucs, key=aucs.get)
    return winner, scores[winner], aucs
