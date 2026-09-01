#!/usr/bin/env python3
"""Load generated dataset CSVs into PostgreSQL.

By default loads only the train and validation splits from
data/generated/{split}/ -- this is the "safe to rerun any time" path, and
never touches rows belonging to the test split.

Loading the test split (--splits test, or --splits train validation test) is
a deliberate, separate action, and it is ALWAYS sourced from
data/locked/test/ rather than data/generated/test/, so an accidental
`generate_dataset.py` rerun can never silently change what ends up in the
database as the held-out evaluation set.

Each requested split is loaded idempotently: existing DB rows for that split
are deleted (in FK-safe order) before the CSVs are (re)inserted, so the
script can be rerun freely.

Usage:
    python scripts/load_database.py                      # train + validation
    python scripts/load_database.py --splits train validation test
    python scripts/load_database.py --splits test         # locked test only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset_common import GENERATED_DIR, LOCKED_TEST_DIR  # noqa: E402

sys.path.insert(0, "/app")  # backend container's app package
try:
    from app.config import get_settings  # type: ignore
except ImportError:
    get_settings = None  # allows --help / unit inspection without the app package on path


def split_source_dir(split: str) -> Path:
    if split == "test":
        return LOCKED_TEST_DIR
    return GENERATED_DIR / split


def delete_split(session: Session, split: str) -> None:
    session.execute(
        text(
            """
            DELETE FROM evidence WHERE dispute_id IN (
                SELECT id FROM disputes WHERE split = :split
            )
            """
        ),
        {"split": split},
    )
    session.execute(
        text(
            """
            DELETE FROM outcomes WHERE dispute_id IN (
                SELECT id FROM disputes WHERE split = :split
            )
            """
        ),
        {"split": split},
    )
    session.execute(
        text(
            """
            DELETE FROM transactions WHERE id IN (
                SELECT transaction_id FROM disputes WHERE split = :split
            )
            """
        ),
        {"split": split},
    )
    session.execute(
        text(
            """
            DELETE FROM customers WHERE id IN (
                SELECT t.customer_id FROM transactions t
                JOIN disputes d ON d.transaction_id = t.id
                WHERE d.split = :split
            )
            """
        ),
        {"split": split},
    )
    session.execute(text("DELETE FROM disputes WHERE split = :split"), {"split": split})
    session.commit()


def load_split(engine, split: str) -> dict[str, int]:
    src = split_source_dir(split)
    if not any(src.glob("*.csv")):
        raise RuntimeError(f"No CSVs found in {src} for split '{split}'. Generate/lock the dataset first.")

    customers = pd.read_csv(src / "customers.csv")
    transactions = pd.read_csv(src / "transactions.csv")
    disputes = pd.read_csv(src / "disputes.csv")
    evidence = pd.read_csv(src / "evidence.csv")
    outcomes = pd.read_csv(src / "outcomes.csv")

    with Session(engine) as session:
        delete_split(session, split)

        customers.to_sql("customers", engine, if_exists="append", index=False, chunksize=5000, method="multi")
        cust_map = pd.read_sql(
            text("SELECT id, customer_id FROM customers WHERE customer_id = ANY(:ids)"),
            engine,
            params={"ids": customers["customer_id"].tolist()},
        )
        cust_id_by_str = dict(zip(cust_map["customer_id"], cust_map["id"]))

        transactions = transactions.copy()
        transactions["customer_id"] = transactions["customer_id"].map(cust_id_by_str)
        transactions.to_sql("transactions", engine, if_exists="append", index=False, chunksize=5000, method="multi")
        txn_map = pd.read_sql(
            text("SELECT id, transaction_id FROM transactions WHERE transaction_id = ANY(:ids)"),
            engine,
            params={"ids": transactions["transaction_id"].tolist()},
        )
        txn_id_by_str = dict(zip(txn_map["transaction_id"], txn_map["id"]))

        disputes = disputes.copy()
        disputes["transaction_id"] = disputes["transaction_id"].map(txn_id_by_str)
        disputes["split"] = split
        disputes.to_sql("disputes", engine, if_exists="append", index=False, chunksize=5000, method="multi")
        dsp_map = pd.read_sql(
            text("SELECT id, dispute_id FROM disputes WHERE dispute_id = ANY(:ids)"),
            engine,
            params={"ids": disputes["dispute_id"].tolist()},
        )
        dsp_id_by_str = dict(zip(dsp_map["dispute_id"], dsp_map["id"]))

        evidence = evidence.copy()
        evidence["dispute_id"] = evidence["dispute_id"].map(dsp_id_by_str)
        evidence.to_sql("evidence", engine, if_exists="append", index=False, chunksize=5000, method="multi")

        outcomes = outcomes.copy()
        outcomes["dispute_id"] = outcomes["dispute_id"].map(dsp_id_by_str)
        outcomes.to_sql("outcomes", engine, if_exists="append", index=False, chunksize=5000, method="multi")

    return {
        "customers": len(customers),
        "transactions": len(transactions),
        "disputes": len(disputes),
        "evidence": len(evidence),
        "outcomes": len(outcomes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--splits", nargs="+", choices=["train", "validation", "test"], default=["train", "validation"])
    args = parser.parse_args()

    if get_settings is None:
        raise RuntimeError("app.config not importable -- run this inside the backend container/environment.")

    engine = create_engine(get_settings().database_url, future=True)

    for split in args.splits:
        print(f"Loading split '{split}' from {split_source_dir(split)} ...")
        counts = load_split(engine, split)
        print(f"  loaded: {counts}")

    print("Done.")


if __name__ == "__main__":
    main()
