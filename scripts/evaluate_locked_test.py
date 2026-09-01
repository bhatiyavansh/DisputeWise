#!/usr/bin/env python3
"""OFFICIAL final evaluation on the frozen, locked held-out test set.

This script is strictly read-only with respect to the dataset. It:
  - verifies the locked test checksum BEFORE evaluating (refuses to run on a
    drifted test set)
  - loads the already-trained model and its already-fitted calibrator
  - uses the operating threshold selected during training on validation
  - re-verifies the checksum AFTER evaluating, proving nothing was mutated

It never retrains, never refits calibration, never re-tunes the threshold, and
never writes anything under data/locked/test/.

Usage:
    python scripts/evaluate_locked_test.py
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

from dataset_common import LOCKED_TEST_DIR, METADATA_DIR  # noqa: E402
from generate_dataset import sha256_of_dir  # noqa: E402

from app.ml import schema  # noqa: E402
from app.ml.baseline import baseline_scores, best_baseline  # noqa: E402
from app.ml.data import load_split  # noqa: E402
from app.ml.features import build_features, extract_target  # noqa: E402
from app.ml.metrics import classification_metrics, format_metrics  # noqa: E402
from app.ml.model import load_model  # noqa: E402


def locked_checksum() -> tuple[str, str | None]:
    metadata_path = METADATA_DIR / "locked_test_metadata.json"
    recorded = json.loads(metadata_path.read_text())["checksum_sha256"] if metadata_path.exists() else None
    return sha256_of_dir(LOCKED_TEST_DIR), recorded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print("=== Locked test set: pre-flight integrity check ===")
    actual_before, recorded = locked_checksum()
    if recorded is None:
        raise SystemExit("FAIL: no locked test metadata found -- refusing to evaluate.")
    if actual_before != recorded:
        raise SystemExit(
            "FAIL: locked test checksum mismatch -- the frozen evaluation set has changed.\n"
            f"  recorded: {recorded}\n  actual:   {actual_before}\n"
            "Refusing to produce an official evaluation against a drifted test set."
        )
    print(f"  OK: checksum matches ({actual_before})")

    model = load_model()
    threshold = float(model.config["operating_threshold"])
    print(f"\nModel {model.model_version} / {model.feature_schema_version}")
    print(f"Calibration: {model.calibration_method}   threshold (from validation): {threshold}")

    trained_against = model.config.get("locked_test_checksum_at_training")
    if trained_against and trained_against != actual_before:
        print(
            "  WARNING: the locked test set differs from the one recorded when this model was "
            "trained. Metrics below are not comparable to earlier runs."
        )

    data = load_split("test")
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    y_true = extract_target(data.outcomes, features.index).to_numpy()

    raw = model.predict_raw(features)
    calibrated = model.calibrate(raw)

    raw_metrics = classification_metrics(y_true, raw, threshold)
    calibrated_metrics = classification_metrics(y_true, calibrated, threshold)

    print(f"\n=== LOCKED TEST (n={len(y_true)}) ===")
    print(f"  raw        {format_metrics(raw_metrics)}")
    print(f"  calibrated {format_metrics(calibrated_metrics)}")
    print(
        f"\n  confusion @ {threshold}: "
        f"TP={calibrated_metrics['true_positive']} TN={calibrated_metrics['true_negative']} "
        f"FP={calibrated_metrics['false_positive']} FN={calibrated_metrics['false_negative']}"
    )
    print(
        f"  FPR={calibrated_metrics['false_positive_rate']:.4f}  "
        f"FNR={calibrated_metrics['false_negative_rate']:.4f}"
    )

    print("\n=== evidence-completeness baselines ===")
    scores = baseline_scores(features)
    winner, _, aucs = best_baseline(scores, y_true)
    baseline_metrics = {}
    for name, score in scores.items():
        metrics = classification_metrics(y_true, score, threshold)
        baseline_metrics[name] = metrics
        marker = "  <- strongest" if name == winner else ""
        print(f"  {name:30s} {format_metrics(metrics)}{marker}")

    headline = baseline_metrics[winner]
    print("\n=== model vs strongest baseline (locked test) ===")
    for label, key in [("ROC-AUC", "roc_auc"), ("PR-AUC", "pr_auc"), ("F1", "f1"), ("Brier", "brier_score")]:
        print(
            f"  {label:8s} baseline={headline[key]:.4f}  model={calibrated_metrics[key]:.4f}  "
            f"delta={calibrated_metrics[key] - headline[key]:+.4f}"
        )

    print("\n=== Locked test set: post-evaluation integrity check ===")
    actual_after, _ = locked_checksum()
    if actual_after != actual_before:
        raise SystemExit(
            f"FAIL: locked test set was modified during evaluation!\n"
            f"  before: {actual_before}\n  after:  {actual_after}"
        )
    print(f"  OK: checksum unchanged ({actual_after})")

    report = {
        "evaluation_type": "official_locked_test",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model.model_version,
        "feature_schema_version": model.feature_schema_version,
        "dataset_version": schema.DATASET_VERSION,
        "calibration_method": model.calibration_method,
        "operating_threshold": threshold,
        "threshold_source": "selected on validation during training; not tuned on this test set",
        "locked_test_checksum_before": actual_before,
        "locked_test_checksum_after": actual_after,
        "locked_test_checksum_recorded": recorded,
        "n_rows": int(len(y_true)),
        "model": {"raw": raw_metrics, "calibrated": calibrated_metrics},
        "baselines": baseline_metrics,
        "baseline_roc_auc": aucs,
        "strongest_baseline": winner,
    }

    out_path = Path(args.out) if args.out else schema.evaluation_dir() / "locked_test_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
