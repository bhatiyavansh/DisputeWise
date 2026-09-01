#!/usr/bin/env python3
"""Error analysis: where does the winnability model get it wrong, and for whom?

Segments performance by reason code, scenario archetype, transaction-amount
bucket, and evidence-completeness bucket, and characterizes the false
positives (cases wrongly called winnable) and false negatives (winnable cases
wrongly rejected).

`scenario_archetype` is used here purely as an ANALYSIS dimension. It is a
synthetic-generator label and is explicitly excluded from the model's
features (see app/ml/schema.FORBIDDEN_COLUMNS).

Defaults to the validation split. Pass --split test to analyze the locked
test set read-only (it is never modified).

Usage:
    python scripts/error_analysis.py
    python scripts/error_analysis.py --split test
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")

from app.ml import schema  # noqa: E402
from app.ml.data import load_split  # noqa: E402
from app.ml.features import build_features, extract_target  # noqa: E402
from app.ml.metrics import classification_metrics  # noqa: E402
from app.ml.model import load_model  # noqa: E402

MIN_SEGMENT_SIZE = 50


def segment_report(
    y_true: np.ndarray, probability: np.ndarray, groups: pd.Series, threshold: float
) -> dict:
    report: dict = {}
    for value in sorted(groups.dropna().unique(), key=str):
        mask = (groups == value).to_numpy()
        if mask.sum() < MIN_SEGMENT_SIZE:
            continue
        metrics = classification_metrics(y_true[mask], probability[mask], threshold)
        report[str(value)] = metrics
    return report


def print_segment(title: str, report: dict) -> None:
    print(f"\n=== {title} ===")
    header = f"  {'segment':30s} {'n':>6s} {'base':>7s} {'AUC':>7s} {'P':>7s} {'R':>7s} {'F1':>7s} {'FPR':>7s} {'FNR':>7s}"
    print(header)
    for name, metrics in report.items():
        auc = metrics["roc_auc"]
        print(
            f"  {name:30s} {metrics['n']:6d} {metrics['positive_rate']:7.3f} "
            f"{(f'{auc:.4f}' if auc is not None else '   n/a'):>7s} "
            f"{metrics['precision']:7.4f} {metrics['recall']:7.4f} {metrics['f1']:7.4f} "
            f"{metrics['false_positive_rate']:7.4f} {metrics['false_negative_rate']:7.4f}"
        )


def characterize_errors(features: pd.DataFrame, y_true: np.ndarray, predicted: np.ndarray) -> dict:
    """Compare the average evidence profile of FPs / FNs against correct cases."""
    false_positive = (predicted == 1) & (y_true == 0)
    false_negative = (predicted == 0) & (y_true == 1)
    true_positive = (predicted == 1) & (y_true == 1)
    true_negative = (predicted == 0) & (y_true == 0)

    interesting = [
        "evidence_completeness_ratio",
        "high_relevance_completeness_ratio",
        "high_relevance_strength_mean",
        "evidence_strength_mean",
        "strong_evidence_count",
        "authentication_evidence_strength_mean",
        "fulfillment_evidence_strength_mean",
        "three_ds_authenticated",
        "customer_success_ratio",
        "transaction_amount",
    ]

    profile: dict = {}
    for label, mask in [
        ("true_positive", true_positive),
        ("true_negative", true_negative),
        ("false_positive", false_positive),
        ("false_negative", false_negative),
    ]:
        if mask.sum() == 0:
            continue
        subset = features.loc[mask]
        profile[label] = {"count": int(mask.sum())}
        for column in interesting:
            if column in subset.columns:
                profile[label][column] = round(float(subset[column].mean(skipna=True)), 4)
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="validation", choices=["train", "validation", "test"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    model = load_model()
    threshold = float(model.config["operating_threshold"])

    data = load_split(args.split)
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    y_true = extract_target(data.outcomes, features.index).to_numpy()
    probability = model.predict_calibrated(features)
    predicted = (probability >= threshold).astype(int)

    overall = classification_metrics(y_true, probability, threshold)
    print(f"Error analysis -- split={args.split}  model={model.model_version}  threshold={threshold}")
    print(
        f"\nOverall: n={overall['n']} ROC-AUC={overall['roc_auc']:.4f} F1={overall['f1']:.4f} "
        f"FP={overall['false_positive']} FN={overall['false_negative']} "
        f"FPR={overall['false_positive_rate']:.4f} FNR={overall['false_negative_rate']:.4f}"
    )

    dispute_meta = data.disputes.set_index("dispute_id").reindex(features.index)

    reason_report = segment_report(y_true, probability, dispute_meta["reason_code"], threshold)
    print_segment("by reason code", reason_report)

    archetype_report = {}
    if "scenario_archetype" in dispute_meta.columns:
        archetype_report = segment_report(
            y_true, probability, dispute_meta["scenario_archetype"], threshold
        )
        print_segment("by scenario archetype (analysis dimension only, never a feature)", archetype_report)

    amount_bucket = pd.cut(
        features["transaction_amount"],
        bins=[0, 500, 1500, 5000, 20000, np.inf],
        labels=["<500", "500-1.5k", "1.5k-5k", "5k-20k", ">20k"],
    )
    amount_report = segment_report(y_true, probability, pd.Series(amount_bucket, index=features.index), threshold)
    print_segment("by transaction amount", amount_report)

    completeness_bucket = pd.cut(
        features["evidence_completeness_ratio"],
        bins=[-0.01, 0.5, 0.7, 0.85, 1.01],
        labels=["<=50%", "50-70%", "70-85%", ">85%"],
    )
    completeness_report = segment_report(
        y_true, probability, pd.Series(completeness_bucket, index=features.index), threshold
    )
    print_segment("by evidence completeness", completeness_report)

    high_relevance_bucket = pd.cut(
        features["high_relevance_completeness_ratio"],
        bins=[-0.01, 0.5, 0.8, 1.01],
        labels=["<=50%", "50-80%", ">80%"],
    )
    high_relevance_report = segment_report(
        y_true, probability, pd.Series(high_relevance_bucket, index=features.index), threshold
    )
    print_segment("by high-relevance evidence completeness", high_relevance_report)

    profile = characterize_errors(features, y_true, predicted)
    print("\n=== error profile (mean feature values by outcome quadrant) ===")
    keys = [k for k in profile.get("true_positive", {}) if k != "count"]
    print(f"  {'feature':42s} " + " ".join(f"{label[:9]:>10s}" for label in profile))
    for key in keys:
        print(f"  {key:42s} " + " ".join(f"{profile[label].get(key, float('nan')):10.4f}" for label in profile))

    report = {
        "split": args.split,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model.model_version,
        "operating_threshold": threshold,
        "overall": overall,
        "by_reason_code": reason_report,
        "by_scenario_archetype": archetype_report,
        "by_amount_bucket": amount_report,
        "by_evidence_completeness": completeness_report,
        "by_high_relevance_completeness": high_relevance_report,
        "error_profile": profile,
        "notes": {
            "scenario_archetype": "analysis dimension only; excluded from model features",
            "min_segment_size": MIN_SEGMENT_SIZE,
        },
    }

    out_path = Path(args.out) if args.out else schema.evaluation_dir() / f"error_analysis_{args.split}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
