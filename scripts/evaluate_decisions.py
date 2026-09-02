#!/usr/bin/env python3
"""Evaluate the Phase 3 decision policy on the VALIDATION split.

Reports decision-bucket volumes, actual favorable-outcome rate per bucket,
expected vs. realized recovery/net value, and compares against three simple
baseline policies (contest everything, probability threshold, evidence
completeness). The policy itself is NOT tuned here or anywhere against the
locked test set -- its thresholds come straight from DecisionConfig
(app/decision/config.py), which is fixed before this script ever runs.

The goal is economic usefulness, not classification accuracy: a policy that
recommends CONTEST on fewer, more profitable cases can beat "contest
everything" on total net value while having lower raw "accuracy".

Usage:
    python scripts/evaluate_decisions.py
    python scripts/evaluate_decisions.py --split train
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")

from app.decision.config import get_decision_config  # noqa: E402
from app.decision.evaluation import (  # noqa: E402
    baseline_contest_everything,
    baseline_evidence_completeness,
    baseline_probability_threshold,
    batch_decide,
    missing_high_relevance_flags,
    summarize_buckets,
    summarize_simple_policy,
)
from app.decision.schema import DECISIONS  # noqa: E402
from app.ml.data import load_split  # noqa: E402
from app.ml.features import build_features, extract_target  # noqa: E402
from app.ml.model import load_model  # noqa: E402


def print_bucket_report(report: dict) -> None:
    print(f"\n=== {report['policy']} ===")
    print(f"  n = {report['n_total']}")
    header = f"  {'bucket':16s} {'n':>6s} {'%':>7s} {'favorable':>10s} {'E[recovery]':>13s} {'E[net]':>13s} {'realized[net]':>14s}"
    print(header)
    for label in DECISIONS:
        b = report["buckets"][label]
        fav = f"{b['actual_favorable_outcome_rate']:.3f}" if b["actual_favorable_outcome_rate"] is not None else "n/a"
        print(
            f"  {label:16s} {b['count']:6d} {b['percentage']:6.2f}% {fav:>10s} "
            f"{b['expected_recovery_total']:13,.2f} {b['expected_net_value_total']:13,.2f} "
            f"{b['realized_net_value_total']:14,.2f}"
        )
    p = report["portfolio"]
    print(
        f"  portfolio: contest_volume={p['contest_volume']} review_volume={p['review_volume']} "
        f"do_not_contest_volume={p['do_not_contest_volume']}"
    )
    print(
        f"  CONTEST bucket: expected_net_value={p['contest_only_expected_net_value']:,.2f}  "
        f"realized_net_value={p['contest_only_realized_net_value']:,.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="validation", choices=["train", "validation"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    config = get_decision_config()
    print("Decision policy configuration (from app/decision/config.py, env-overridable):")
    print(f"  {config.model_dump()}")

    model = load_model()
    data = load_split(args.split)
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    y_true = extract_target(data.outcomes, features.index)

    calibrated = model.predict_calibrated(features)
    dispute_amount = data.disputes.set_index("dispute_id")["dispute_amount"].reindex(features.index).astype(float)
    missing_evidence = missing_high_relevance_flags(data.evidence, features.index)

    print(f"\nEvaluating on '{args.split}' split (n={len(features)}) ...")
    decisions = batch_decide(features.index, calibrated, dispute_amount, missing_evidence, config)
    main_report = summarize_buckets(decisions, y_true, config, policy_label=f"DisputeWise decision-v1 ({args.split})")
    print_bucket_report(main_report)

    # --- baselines -----------------------------------------------------------
    print("\n\n########## Baseline comparison ##########")

    baseline_reports = {}

    everything = baseline_contest_everything(features.index)
    baseline_reports["A_contest_everything"] = summarize_simple_policy(
        everything, calibrated, dispute_amount, y_true, config, "Baseline A: contest everything"
    )
    print_bucket_report(baseline_reports["A_contest_everything"])

    threshold_decisions = baseline_probability_threshold(calibrated, features.index)
    baseline_reports["B_probability_threshold"] = summarize_simple_policy(
        threshold_decisions,
        calibrated,
        dispute_amount,
        y_true,
        config,
        "Baseline B: contest if P(win) >= 0.50",
    )
    print_bucket_report(baseline_reports["B_probability_threshold"])

    evidence_decisions = baseline_evidence_completeness(features["high_relevance_completeness_ratio"])
    baseline_reports["C_evidence_completeness"] = summarize_simple_policy(
        evidence_decisions,
        calibrated,
        dispute_amount,
        y_true,
        config,
        "Baseline C: contest if high-relevance evidence completeness >= 0.70",
    )
    print_bucket_report(baseline_reports["C_evidence_completeness"])

    print("\n\n=== Portfolio-level comparison (contest-bucket only) ===")
    print(f"  {'policy':45s} {'contest_n':>10s} {'E[net]':>13s} {'realized[net]':>14s}")
    for report in [main_report, *baseline_reports.values()]:
        p = report["portfolio"]
        print(
            f"  {report['policy']:45s} {p['contest_volume']:10d} "
            f"{p['contest_only_expected_net_value']:13,.2f} {p['contest_only_realized_net_value']:14,.2f}"
        )

    output = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "split": args.split,
        "decision_config": config.model_dump(),
        "phase3_policy": main_report,
        "baselines": baseline_reports,
    }

    from app.ml import schema as ml_schema

    out_path = Path(args.out) if args.out else ml_schema.evaluation_dir() / f"decision_evaluation_{args.split}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
