#!/usr/bin/env python3
"""Evaluate the trained model on the VALIDATION split, against the baseline.

Reports discrimination, threshold metrics at the operating point chosen during
training, and the evidence-completeness baseline comparison.

The operating threshold is read from the model config -- it was selected on
validation during training and is NOT re-tuned here, and the locked test set
is never read.

Usage:
    python scripts/evaluate_model.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")

from app.ml import schema  # noqa: E402
from app.ml.baseline import baseline_scores, best_baseline  # noqa: E402
from app.ml.data import load_split  # noqa: E402
from app.ml.features import build_features, extract_target  # noqa: E402
from app.ml.metrics import classification_metrics, format_metrics  # noqa: E402
from app.ml.model import load_model  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="validation", choices=["train", "validation"])
    parser.add_argument("--out", default=None, help="where to write the JSON report")
    args = parser.parse_args()

    model = load_model()
    threshold = float(model.config["operating_threshold"])

    print(f"Model {model.model_version} / {model.feature_schema_version}")
    print(f"Calibration: {model.calibration_method}   operating threshold: {threshold}")

    data = load_split(args.split)
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    y_true = extract_target(data.outcomes, features.index).to_numpy()

    raw = model.predict_raw(features)
    calibrated = model.calibrate(raw)

    print(f"\n=== {args.split} ===")
    raw_metrics = classification_metrics(y_true, raw, threshold)
    calibrated_metrics = classification_metrics(y_true, calibrated, threshold)
    print(f"  raw        {format_metrics(raw_metrics)}")
    print(f"  calibrated {format_metrics(calibrated_metrics)}")

    print("\n=== evidence-completeness baselines ===")
    scores = baseline_scores(features)
    winner, winner_scores, aucs = best_baseline(scores, y_true)
    baseline_metrics = {}
    for name, score in scores.items():
        metrics = classification_metrics(y_true, score, threshold)
        baseline_metrics[name] = metrics
        marker = "  <- strongest" if name == winner else ""
        print(f"  {name:30s} {format_metrics(metrics)}{marker}")

    headline_baseline = baseline_metrics[winner]
    print("\n=== model vs strongest baseline ===")
    for label, metric_key in [("ROC-AUC", "roc_auc"), ("PR-AUC", "pr_auc"), ("F1", "f1"), ("Brier", "brier_score")]:
        baseline_value = headline_baseline[metric_key]
        model_value = calibrated_metrics[metric_key]
        delta = model_value - baseline_value
        print(f"  {label:8s} baseline={baseline_value:.4f}  model={model_value:.4f}  delta={delta:+.4f}")

    report = {
        "split": args.split,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model.model_version,
        "feature_schema_version": model.feature_schema_version,
        "calibration_method": model.calibration_method,
        "operating_threshold": threshold,
        "note": (
            "Threshold was selected on validation during training and is not re-tuned here. "
            "The locked test set is not read by this script. Calibration was fitted on part of "
            "this split during training, so calibration metrics reported here on 'validation' are "
            "partially in-sample; see training_metrics.json for out-of-fold calibration numbers."
        ),
        "model": {"raw": raw_metrics, "calibrated": calibrated_metrics},
        "baselines": baseline_metrics,
        "baseline_roc_auc": aucs,
        "strongest_baseline": winner,
    }

    out_path = Path(args.out) if args.out else schema.evaluation_dir() / f"{args.split}_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
