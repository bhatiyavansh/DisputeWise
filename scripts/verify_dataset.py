#!/usr/bin/env python3
"""Verify the locked held-out test set has not drifted from its recorded metadata.

Checks:
  - data/metadata/locked_test_metadata.json exists
  - recomputed checksum matches the recorded one
  - row counts match the recorded ones
  - expected columns are present in each table
  - no duplicate dispute_id / customer_id / transaction_id / evidence_id
  - favorable_outcome rate is within a sane [0, 1] probabilistic range (not 0 or 1)

Exits non-zero on any failure, so it can be used as a CI/pre-flight gate.

Usage:
    python scripts/verify_dataset.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset_common import LOCKED_TEST_DIR, METADATA_DIR  # noqa: E402
from generate_dataset import sha256_of_dir  # noqa: E402

EXPECTED_COLUMNS = {
    "customers": {
        "customer_id",
        "account_created_at",
        "country",
        "account_age_days",
        "previous_order_count",
        "previous_successful_order_count",
        "previous_dispute_count",
        "previous_refund_count",
    },
    "transactions": {
        "transaction_id",
        "customer_id",
        "merchant_id",
        "amount",
        "currency",
        "payment_method",
        "created_at",
        "captured_at",
        "status",
        "device_id",
        "ip_address",
        "billing_address_id",
        "shipping_address_id",
        "avs_result",
        "cvv_result",
        "three_ds_authenticated",
    },
    "disputes": {
        "dispute_id",
        "transaction_id",
        "reason_code",
        "dispute_amount",
        "created_at",
        "response_deadline",
        "status",
        "scenario_archetype",
    },
    "evidence": {
        "evidence_id",
        "dispute_id",
        "evidence_type",
        "available",
        "value",
        "relevance",
        "strength",
        "created_at",
    },
    "outcomes": {"dispute_id", "favorable_outcome", "outcome_at", "outcome_source", "recovery_amount"},
}

UNIQUE_KEY = {
    "customers": "customer_id",
    "transactions": "transaction_id",
    "disputes": "dispute_id",
    "evidence": "evidence_id",
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main() -> None:
    metadata_path = METADATA_DIR / "locked_test_metadata.json"
    if not metadata_path.exists():
        fail(f"{metadata_path} does not exist -- has the test set been locked (generate_dataset.py --lock)?")

    metadata = json.loads(metadata_path.read_text())
    print(f"Loaded lock metadata: seed={metadata['generation_seed']}, created_at={metadata['created_at']}")

    actual_checksum = sha256_of_dir(LOCKED_TEST_DIR)
    if actual_checksum != metadata["checksum_sha256"]:
        fail(
            "Checksum mismatch! Locked test set has drifted from its recorded metadata.\n"
            f"  recorded: {metadata['checksum_sha256']}\n"
            f"  actual:   {actual_checksum}"
        )
    print("OK: checksum matches recorded metadata")

    tables: dict[str, pd.DataFrame] = {}
    for name in EXPECTED_COLUMNS:
        path = LOCKED_TEST_DIR / f"{name}.csv"
        if not path.exists():
            fail(f"missing {path}")
        tables[name] = pd.read_csv(path)

    for name, expected_cols in EXPECTED_COLUMNS.items():
        missing = expected_cols - set(tables[name].columns)
        if missing:
            fail(f"{name}.csv is missing expected columns: {missing}")
    print("OK: schema columns present for all tables")

    for name, key in UNIQUE_KEY.items():
        dupes = tables[name][key].duplicated().sum()
        if dupes:
            fail(f"{name}.csv has {dupes} duplicate {key} values")
    print("OK: no duplicate IDs")

    for name, expected_count in metadata["row_counts"].items():
        actual_count = len(tables[name])
        if actual_count != expected_count:
            fail(f"{name}.csv row count mismatch: expected {expected_count}, got {actual_count}")
    print("OK: row counts match recorded metadata")

    rate = tables["outcomes"]["favorable_outcome"].mean()
    if not (0.05 < rate < 0.95):
        fail(f"favorable_outcome rate ({rate:.4f}) looks degenerate for a probabilistic dataset")
    print(f"OK: favorable_outcome rate is probabilistic ({rate:.4f})")

    # relational integrity: every FK should resolve
    if not tables["transactions"]["customer_id"].isin(tables["customers"]["customer_id"]).all():
        fail("transactions.customer_id references a customer_id not present in customers.csv")
    if not tables["disputes"]["transaction_id"].isin(tables["transactions"]["transaction_id"]).all():
        fail("disputes.transaction_id references a transaction_id not present in transactions.csv")
    if not tables["evidence"]["dispute_id"].isin(tables["disputes"]["dispute_id"]).all():
        fail("evidence.dispute_id references a dispute_id not present in disputes.csv")
    if not tables["outcomes"]["dispute_id"].isin(tables["disputes"]["dispute_id"]).all():
        fail("outcomes.dispute_id references a dispute_id not present in disputes.csv")
    print("OK: relational integrity (FK references resolve)")

    print("\nLocked test set verification PASSED.")


if __name__ == "__main__":
    main()
