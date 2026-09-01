"""Dataset loading for the Phase 2 ML pipeline.

Reads the Phase 1 CSV splits. Read-only by construction: nothing here writes
to `data/`, and the `test` split is always sourced from the frozen
`data/locked/test/` directory rather than `data/generated/test/`, mirroring
the rule already enforced by scripts/load_database.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TABLES = ("customers", "transactions", "disputes", "evidence", "outcomes")
SPLITS = ("train", "validation", "test")


def data_dir() -> Path:
    env = os.environ.get("DISPUTEWISE_DATA_DIR")
    if env:
        return Path(env)
    container_path = Path("/data")
    if container_path.is_dir():
        return container_path
    return Path(__file__).resolve().parents[3] / "data"


def split_dir(split: str) -> Path:
    if split not in SPLITS:
        raise ValueError(f"unknown split '{split}' (expected one of {SPLITS})")
    if split == "test":
        # The official held-out set always comes from the locked directory.
        return data_dir() / "locked" / "test"
    return data_dir() / "generated" / split


@dataclass(frozen=True)
class SplitData:
    """The five Phase 1 tables for one split."""

    split: str
    customers: pd.DataFrame
    transactions: pd.DataFrame
    disputes: pd.DataFrame
    evidence: pd.DataFrame
    outcomes: pd.DataFrame

    def __len__(self) -> int:
        return len(self.disputes)


def load_split(split: str) -> SplitData:
    directory = split_dir(split)
    frames = {}
    for table in TABLES:
        path = directory / f"{table}.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"missing {path}. Generate the dataset first "
                "(python scripts/generate_dataset.py --seed 42 --n-cases 50000)."
            )
        frames[table] = pd.read_csv(path)
    return SplitData(split=split, **frames)
