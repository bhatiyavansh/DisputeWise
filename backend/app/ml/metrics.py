"""Canonical evaluation metrics, shared by every Phase 2 evaluation script.

One implementation so validation, calibration, locked-test, and error-analysis
reports are always computed identically and are directly comparable.
"""

from __future__ import annotations

import numpy as np

from app.ml.calibration import brier_score, expected_calibration_error


def classification_metrics(y_true: np.ndarray, probability: np.ndarray, threshold: float) -> dict:
    """Discrimination + calibration + confusion metrics at one threshold."""
    from sklearn.metrics import (
        average_precision_score,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    y_true = np.asarray(y_true, dtype=int)
    probability = np.asarray(probability, dtype=float)
    predicted = (probability >= threshold).astype(int)

    true_positive = int(((predicted == 1) & (y_true == 1)).sum())
    true_negative = int(((predicted == 0) & (y_true == 0)).sum())
    false_positive = int(((predicted == 1) & (y_true == 0)).sum())
    false_negative = int(((predicted == 0) & (y_true == 1)).sum())

    single_class = len(np.unique(y_true)) < 2

    return {
        "n": int(len(y_true)),
        "positive_rate": float(y_true.mean()) if len(y_true) else 0.0,
        "roc_auc": float(roc_auc_score(y_true, probability)) if not single_class else None,
        "pr_auc": float(average_precision_score(y_true, probability)) if not single_class else None,
        "precision": float(precision_score(y_true, predicted, zero_division=0)),
        "recall": float(recall_score(y_true, predicted, zero_division=0)),
        "f1": float(f1_score(y_true, predicted, zero_division=0)),
        "brier_score": brier_score(y_true, probability),
        "ece": expected_calibration_error(y_true, probability),
        "threshold": float(threshold),
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "false_positive_rate": float(false_positive / max(false_positive + true_negative, 1)),
        "false_negative_rate": float(false_negative / max(false_negative + true_positive, 1)),
    }


def format_metrics(metrics: dict) -> str:
    def fmt(key: str, spec: str = ".4f") -> str:
        value = metrics.get(key)
        return format(value, spec) if isinstance(value, (int, float)) else "n/a"

    return (
        f"n={metrics['n']:<6d} ROC-AUC={fmt('roc_auc')} PR-AUC={fmt('pr_auc')} "
        f"P={fmt('precision')} R={fmt('recall')} F1={fmt('f1')} "
        f"Brier={fmt('brier_score')} ECE={fmt('ece')} FPR={fmt('false_positive_rate')}"
    )
