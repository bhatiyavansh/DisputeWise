#!/usr/bin/env python3
"""OFFICIAL final decision-policy evaluation on the frozen, locked test set.

Strictly read-only with respect to the dataset, mirroring
evaluate_locked_test.py's discipline:
  - verifies the locked test checksum BEFORE evaluating
  - uses the already-trained model and its already-fitted calibrator
  - uses DecisionConfig exactly as configured -- NOT tuned here
  - re-verifies the checksum AFTER evaluating

It never retrains, never refits calibration, never re-tunes decision
thresholds, and never writes anything under data/locked/test/.

Usage:
    python scripts/evaluate_locked_decisions.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")

from dataset_common import LOCKED_TEST_DIR, METADATA_DIR  # noqa: E402
from generate_dataset import sha256_of_dir  # noqa: E402

from app.decision.config import get_decision_config  # noqa: E402
from app.decision.evaluation import batch_decide, missing_high_relevance_flags, summarize_buckets  # noqa: E402
from app.decision.schema import DECISIONS  # noqa: E402
from app.ml import schema as ml_schema  # noqa: E402
from app.ml.data import load_split  # noqa: E402
from app.ml.features import build_features, extract_target  # noqa: E402
from app.ml.model import load_model  # noqa: E402


def locked_checksum() -> tuple[str, str | None]:
    metadata_path = METADATA_DIR / "locked_test_metadata.json"
    recorded = json.loads(metadata_path.read_text())["checksum_sha256"] if metadata_path.exists() else None
    return sha256_of_dir(LOCKED_TEST_DIR), recorded


def main() -> None:
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

    config = get_decision_config()
    print("\nDecision policy configuration (fixed BEFORE this evaluation; not tuned here):")
    print(f"  {config.model_dump()}")

    model = load_model()
    print(f"\nModel {model.model_version} / calibration: {model.calibration_method}")

    data = load_split("test")
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    y_true = extract_target(data.outcomes, features.index)

    calibrated = model.predict_calibrated(features)
    dispute_amount = data.disputes.set_index("dispute_id")["dispute_amount"].reindex(features.index).astype(float)
    missing_evidence = missing_high_relevance_flags(data.evidence, features.index)

    print(f"\n=== OFFICIAL LOCKED-TEST DECISION EVALUATION (n={len(features)}) ===")
    decisions = batch_decide(features.index, calibrated, dispute_amount, missing_evidence, config)
    report = summarize_buckets(decisions, y_true, config, policy_label="DisputeWise decision-v1 (LOCKED TEST -- final)")

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
        f"\n  contest_rate={p['contest_volume'] / report['n_total']:.2%}  "
        f"human_review_rate={p['review_volume'] / report['n_total']:.2%}  "
        f"do_not_contest_rate={p['do_not_contest_volume'] / report['n_total']:.2%}"
    )
    print(
        f"  CONTEST bucket: expected_net_value={p['contest_only_expected_net_value']:,.2f}  "
        f"realized_net_value={p['contest_only_realized_net_value']:,.2f}"
    )

    print("\n=== Locked test set: post-evaluation integrity check ===")
    actual_after, _ = locked_checksum()
    if actual_after != actual_before:
        raise SystemExit(
            f"FAIL: locked test set was modified during evaluation!\n"
            f"  before: {actual_before}\n  after:  {actual_after}"
        )
    print(f"  OK: checksum unchanged ({actual_after})")

    output = {
        "evaluation_type": "official_locked_test_decisions",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model.model_version,
        "decision_policy_version": "decision-v1",
        "decision_config": config.model_dump(),
        "locked_test_checksum_before": actual_before,
        "locked_test_checksum_after": actual_after,
        "locked_test_checksum_recorded": recorded,
        "report": report,
    }

    out_path = ml_schema.evaluation_dir() / "locked_test_decisions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {out_path}")
    print("\nThis is the FINAL, official held-out decision-policy evaluation.")


if __name__ == "__main__":
    main()
