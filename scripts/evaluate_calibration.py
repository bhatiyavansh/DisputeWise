#!/usr/bin/env python3
"""Assess probability calibration quality on the validation split.

Reports Brier score, Expected Calibration Error, and a reliability curve for
the raw vs. calibrated probabilities, plus the out-of-fold calibration
comparison recorded at training time (which is what actually selected the
calibration method).

The locked test set is NOT used to select or assess the calibration method.

Usage:
    python scripts/evaluate_calibration.py
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
from app.ml.calibration import (  # noqa: E402
    brier_score,
    calibration_curve_points,
    expected_calibration_error,
)
from app.ml.data import load_split  # noqa: E402
from app.ml.features import build_features, extract_target  # noqa: E402
from app.ml.model import load_model  # noqa: E402


def render_curve(points: list[dict]) -> str:
    lines = ["    bin            n     predicted   observed    gap"]
    for point in points:
        gap = point["mean_predicted"] - point["observed_frequency"]
        lines.append(
            f"    [{point['bin_lower']:.1f},{point['bin_upper']:.1f})  {point['count']:5d}   "
            f"{point['mean_predicted']:.4f}      {point['observed_frequency']:.4f}   {gap:+.4f}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    model = load_model()
    data = load_split("validation")
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    y_true = extract_target(data.outcomes, features.index).to_numpy()

    raw = model.predict_raw(features)
    calibrated = model.calibrate(raw)

    print(f"Model {model.model_version}  calibration method: {model.calibration_method}")
    print(f"Validation rows: {len(y_true)}\n")

    summary = {}
    for label, probability in [("raw", raw), ("calibrated", calibrated)]:
        summary[label] = {
            "brier_score": brier_score(y_true, probability),
            "ece": expected_calibration_error(y_true, probability, n_bins=args.bins),
            "mean_predicted": float(probability.mean()),
            "observed_positive_rate": float(y_true.mean()),
            "calibration_curve": calibration_curve_points(y_true, probability, n_bins=args.bins),
        }
        print(f"=== {label} ===")
        print(
            f"  Brier={summary[label]['brier_score']:.5f}  ECE={summary[label]['ece']:.5f}  "
            f"mean_predicted={summary[label]['mean_predicted']:.4f}  "
            f"observed={summary[label]['observed_positive_rate']:.4f}"
        )
        print(render_curve(summary[label]["calibration_curve"]))
        print()

    # The numbers that actually drove method selection, recorded at training time.
    training_metrics_path = schema.models_dir() / schema.TRAINING_METRICS_FILENAME
    selection = {}
    if training_metrics_path.exists():
        training_metrics = json.loads(training_metrics_path.read_text())
        selection = training_metrics.get("calibration", {})
        print("=== out-of-fold calibration comparison (from training; drove the choice) ===")
        for method, values in selection.items():
            marker = "  <- chosen" if method == model.calibration_method else ""
            print(f"  {method:13s} Brier={values['oof_brier']:.5f}  ECE={values['oof_ece']:.5f}{marker}")

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model.model_version,
        "calibration_method": model.calibration_method,
        "split": "validation",
        "n_bins": args.bins,
        "note": (
            "Calibration was fitted on a customer-disjoint half of validation during training, so "
            "the in-sample numbers here are mildly optimistic. The out_of_fold_selection block "
            "holds the cross-fitted numbers that actually selected the method. The locked test set "
            "was not used for either."
        ),
        "in_sample_validation": summary,
        "out_of_fold_selection": selection,
    }

    out_path = Path(args.out) if args.out else schema.evaluation_dir() / "calibration_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
