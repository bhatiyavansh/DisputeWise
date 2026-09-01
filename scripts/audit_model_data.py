#!/usr/bin/env python3
"""Audit the Phase 1 dataset before it is used for Phase 2 modeling.

Reports structure and distributions, and FAILS LOUDLY (non-zero exit) on any
condition that would invalidate modeling:

  - the locked test set has changed (checksum mismatch)
  - dispute / transaction / customer IDs overlap across splits
  - the target is missing for any dispute
  - a source column perfectly separates the target (leakage)
  - a forbidden column has crept into the built feature matrix

It never repairs data. If something is wrong, it says so and stops.

Usage:
    python scripts/audit_model_data.py
    python scripts/audit_model_data.py --json-out artifacts/evaluation/data_audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")

from dataset_common import LOCKED_TEST_DIR, METADATA_DIR  # noqa: E402
from generate_dataset import sha256_of_dir  # noqa: E402

try:
    from app.ml import schema
    from app.ml.data import load_split
    from app.ml.features import build_features, extract_target
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        f"cannot import app.ml ({exc}). Run inside the backend container: "
        "docker compose run --rm backend python /scripts/audit_model_data.py"
    )

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"  FAIL: {message}")


def ok(message: str) -> None:
    print(f"  OK: {message}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def audit_locked_test_unchanged() -> dict:
    section("Locked test set integrity")
    metadata_path = METADATA_DIR / "locked_test_metadata.json"
    if not metadata_path.exists():
        fail(f"{metadata_path} not found -- the locked test set has no recorded lock metadata")
        return {}

    metadata = json.loads(metadata_path.read_text())
    actual = sha256_of_dir(LOCKED_TEST_DIR)
    if actual != metadata["checksum_sha256"]:
        fail(
            "locked test set checksum MISMATCH -- the frozen evaluation set has changed.\n"
            f"    recorded: {metadata['checksum_sha256']}\n"
            f"    actual:   {actual}"
        )
    else:
        ok(f"locked test checksum unchanged ({actual[:16]}...)")
    return {"recorded_checksum": metadata.get("checksum_sha256"), "actual_checksum": actual}


def audit_structure(splits: dict[str, object]) -> dict:
    section("Structure and row counts")
    report: dict = {}
    for name, data in splits.items():
        counts = {
            "customers": len(data.customers),
            "transactions": len(data.transactions),
            "disputes": len(data.disputes),
            "evidence": len(data.evidence),
            "outcomes": len(data.outcomes),
        }
        report[name] = {"row_counts": counts}
        print(f"  {name:11s} {counts}")

        if counts["disputes"] != counts["outcomes"]:
            fail(f"{name}: disputes ({counts['disputes']}) != outcomes ({counts['outcomes']})")

        for table_name, frame, key in [
            ("disputes", data.disputes, "dispute_id"),
            ("transactions", data.transactions, "transaction_id"),
            ("customers", data.customers, "customer_id"),
            ("evidence", data.evidence, "evidence_id"),
        ]:
            duplicates = int(frame[key].duplicated().sum())
            if duplicates:
                fail(f"{name}.{table_name} has {duplicates} duplicate {key} values")

    return report


def audit_columns_and_types(data) -> dict:
    section("Columns, dtypes, missingness (train split)")
    report: dict = {}
    for table_name, frame in [
        ("customers", data.customers),
        ("transactions", data.transactions),
        ("disputes", data.disputes),
        ("evidence", data.evidence),
        ("outcomes", data.outcomes),
    ]:
        columns = {}
        for column in frame.columns:
            columns[column] = {
                "dtype": str(frame[column].dtype),
                "null_count": int(frame[column].isna().sum()),
                "null_fraction": round(float(frame[column].isna().mean()), 6),
            }
        report[table_name] = columns
        nulls = {c: v["null_count"] for c, v in columns.items() if v["null_count"]}
        print(f"  {table_name:13s} cols={len(frame.columns):2d}  nulls={nulls if nulls else 'none'}")
    return report


def audit_cardinalities_and_ranges(data) -> dict:
    section("Categorical cardinalities and numeric ranges (train split)")
    report: dict = {"categorical": {}, "numeric": {}}

    categorical_targets = [
        ("transactions", "merchant_id"),
        ("transactions", "payment_method"),
        ("transactions", "status"),
        ("transactions", "currency"),
        ("transactions", "avs_result"),
        ("transactions", "cvv_result"),
        ("customers", "country"),
        ("disputes", "reason_code"),
        ("disputes", "status"),
        ("disputes", "scenario_archetype"),
        ("evidence", "evidence_type"),
        ("evidence", "relevance"),
    ]
    for table_name, column in categorical_targets:
        frame = getattr(data, table_name)
        if column not in frame.columns:
            continue
        counts = frame[column].value_counts()
        report["categorical"][f"{table_name}.{column}"] = {
            "cardinality": int(counts.size),
            "top": {str(k): int(v) for k, v in counts.head(6).items()},
        }
        print(f"  {table_name}.{column:20s} cardinality={counts.size}")

    numeric_targets = [
        ("transactions", "amount"),
        ("disputes", "dispute_amount"),
        ("customers", "account_age_days"),
        ("customers", "previous_order_count"),
        ("customers", "previous_dispute_count"),
        ("evidence", "strength"),
    ]
    for table_name, column in numeric_targets:
        frame = getattr(data, table_name)
        if column not in frame.columns:
            continue
        series = pd.to_numeric(frame[column], errors="coerce")
        stats = {
            "min": float(series.min()),
            "p50": float(series.quantile(0.5)),
            "p99": float(series.quantile(0.99)),
            "max": float(series.max()),
            "mean": float(series.mean()),
        }
        report["numeric"][f"{table_name}.{column}"] = {k: round(v, 4) for k, v in stats.items()}
        print(f"  {table_name}.{column:20s} min={stats['min']:.2f} p50={stats['p50']:.2f} max={stats['max']:.2f}")

    return report


def audit_target(splits: dict[str, object]) -> dict:
    section("Target distribution")
    report: dict = {}
    for name, data in splits.items():
        if "favorable_outcome" not in data.outcomes.columns:
            fail(f"{name}: outcomes table has no favorable_outcome column -- target is missing")
            continue
        target = data.outcomes["favorable_outcome"]
        if target.isna().any():
            fail(f"{name}: favorable_outcome has {int(target.isna().sum())} null values")
        rate = float(target.astype(str).map({"True": 1.0, "False": 0.0}).fillna(target).astype(float).mean())
        report[name] = {"count": len(target), "positive_rate": round(rate, 6)}
        print(f"  {name:11s} n={len(target):6d}  positive_rate={rate:.4f}")

        missing_labels = set(data.disputes["dispute_id"]) - set(data.outcomes["dispute_id"])
        if missing_labels:
            fail(f"{name}: {len(missing_labels)} disputes have no outcome row")
    return report


def audit_split_disjointness(splits: dict[str, object]) -> dict:
    section("Split disjointness (customer-level split integrity)")
    report: dict = {}
    ids = {
        name: {
            "customers": set(data.customers["customer_id"]),
            "transactions": set(data.transactions["transaction_id"]),
            "disputes": set(data.disputes["dispute_id"]),
        }
        for name, data in splits.items()
    }
    names = list(splits.keys())
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            for entity in ("customers", "transactions", "disputes"):
                overlap = ids[left][entity] & ids[right][entity]
                key = f"{left}__{right}__{entity}"
                report[key] = len(overlap)
                if overlap:
                    fail(
                        f"{entity} overlap between {left} and {right}: {len(overlap)} shared IDs "
                        f"(e.g. {sorted(overlap)[:3]}) -- this breaks split integrity"
                    )
                else:
                    ok(f"{entity}: {left} ∩ {right} = ∅")
    return report


def audit_evidence(splits: dict[str, object]) -> dict:
    section("Evidence structure")
    report: dict = {}
    for name, data in splits.items():
        per_dispute = data.evidence.groupby("dispute_id").size()
        type_counts = data.evidence["evidence_type"].value_counts()
        unknown_types = set(type_counts.index) - set(schema.ALL_EVIDENCE_TYPES)
        report[name] = {
            "evidence_per_dispute": {str(k): int(v) for k, v in per_dispute.value_counts().items()},
            "distinct_evidence_types": int(type_counts.size),
            "available_rate": round(
                float(data.evidence["available"].astype(str).map({"True": 1.0, "False": 0.0}).mean()), 6
            ),
        }
        print(
            f"  {name:11s} evidence/dispute={dict(per_dispute.value_counts())} "
            f"types={type_counts.size} available_rate={report[name]['available_rate']:.3f}"
        )
        if unknown_types:
            fail(f"{name}: evidence contains types outside the declared taxonomy: {sorted(unknown_types)}")

        disputes_without_evidence = set(data.disputes["dispute_id"]) - set(data.evidence["dispute_id"])
        if disputes_without_evidence:
            print(f"    note: {len(disputes_without_evidence)} disputes have no evidence rows")
    return report


def audit_reason_codes(splits: dict[str, object]) -> dict:
    section("Reason-code distribution")
    report: dict = {}
    for name, data in splits.items():
        counts = data.disputes["reason_code"].value_counts(normalize=True)
        report[name] = {str(k): round(float(v), 4) for k, v in counts.items()}
        print(f"  {name:11s} {report[name]}")
    return report


def audit_leakage(data) -> dict:
    """Detect columns that perfectly (or near-perfectly) separate the target."""
    section("Leakage scan")
    report: dict = {"perfect_separators": [], "checked_columns": []}

    outcomes = data.outcomes.copy()
    target = outcomes["favorable_outcome"].astype(str).map({"True": 1, "False": 0}).astype(int)
    outcomes = outcomes.assign(_target=target)

    # Any non-key column in the outcomes table that perfectly separates the
    # target is expected (that table IS the label) -- the real risk is such a
    # column being joined into features, which is checked separately below.
    for column in outcomes.columns:
        if column in ("dispute_id", "_target", "favorable_outcome"):
            continue
        series = outcomes[column]
        indicator = series.notna().astype(int)
        report["checked_columns"].append(f"outcomes.{column}")
        if indicator.nunique() > 1 and (indicator == outcomes["_target"]).mean() in (0.0, 1.0):
            report["perfect_separators"].append(f"outcomes.{column}")
            print(
                f"  note: outcomes.{column} perfectly encodes the target "
                "(expected -- it lives in the label table and is never passed to build_features)"
            )

    # The real check: build features and confirm nothing forbidden is present
    # and nothing perfectly separates the target.
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    aligned_target = extract_target(data.outcomes, features.index)

    forbidden_present = sorted(set(features.columns) & set(schema.FORBIDDEN_COLUMNS))
    if forbidden_present:
        fail(f"forbidden columns present in the feature matrix: {forbidden_present}")
    else:
        ok(f"no forbidden columns in the {features.shape[1]}-column feature matrix")

    suspicious = []
    for column in features.columns:
        series = features[column]
        if series.nunique(dropna=True) <= 1:
            continue
        valid = series.notna()
        if valid.sum() < 100:
            continue
        correlation = np.corrcoef(series[valid].astype(float), aligned_target[valid].astype(float))[0, 1]
        if np.isfinite(correlation) and abs(correlation) >= 0.95:
            suspicious.append({"feature": column, "abs_correlation": round(float(abs(correlation)), 4)})

    report["suspicious_features"] = suspicious
    if suspicious:
        fail(f"features almost perfectly correlated with the target (possible leakage): {suspicious}")
    else:
        ok("no feature correlates with the target at |r| >= 0.95")

    correlations = {}
    for column in features.columns:
        series = features[column]
        valid = series.notna()
        if series.nunique(dropna=True) <= 1 or valid.sum() < 100:
            continue
        correlation = np.corrcoef(series[valid].astype(float), aligned_target[valid].astype(float))[0, 1]
        if np.isfinite(correlation):
            correlations[column] = round(float(correlation), 4)
    top = sorted(correlations.items(), key=lambda kv: -abs(kv[1]))[:10]
    report["top_target_correlations"] = dict(top)
    print("  strongest (legitimate) target correlations:")
    for name, value in top:
        print(f"    {name:45s} r={value:+.4f}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json-out", type=str, default=None)
    args = parser.parse_args()

    print("DisputeWise -- Phase 2 model-data audit")

    splits = {name: load_split(name) for name in ("train", "validation", "test")}

    report = {
        "locked_test": audit_locked_test_unchanged(),
        "structure": audit_structure(splits),
        "columns": audit_columns_and_types(splits["train"]),
        "cardinalities": audit_cardinalities_and_ranges(splits["train"]),
        "target": audit_target(splits),
        "split_disjointness": audit_split_disjointness(splits),
        "evidence": audit_evidence(splits),
        "reason_codes": audit_reason_codes(splits),
        "leakage": audit_leakage(splits["train"]),
    }
    report["failures"] = FAILURES

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2))
        print(f"\nWrote {out_path}")

    print()
    if FAILURES:
        print(f"AUDIT FAILED with {len(FAILURES)} problem(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        raise SystemExit(1)

    print("AUDIT PASSED -- dataset is safe for Phase 2 modeling.")


if __name__ == "__main__":
    main()
