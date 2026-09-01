#!/usr/bin/env python3
"""Train the DisputeWise winnability model (LightGBM + probability calibration).

Data discipline
---------------
    train      -> model fitting only
    val_a      -> early stopping + hyperparameter selection   (half of validation)
    val_b      -> calibration + threshold + reported metrics   (half of validation)
    locked test-> NEVER touched here (final evaluation only, see evaluate_locked_test.py)

`val_a` / `val_b` are a deterministic, CUSTOMER-DISJOINT bisection of the
Phase 1 validation split, so the data used to choose hyperparameters is
disjoint from the data used to fit calibration and pick a threshold. Within
`val_b`, calibration is cross-fitted (2 customer-disjoint folds) so the
reported validation metrics are not optimistic about calibration quality;
the shipped calibrator is then refit on all of `val_b`.

Reproducibility: all seeds are fixed and LightGBM runs in deterministic mode,
so repeated runs on the same data produce identical artifacts and metrics.

Usage:
    python scripts/train_model.py
    python scripts/train_model.py --no-search      # skip the small param search
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")

from dataset_common import METADATA_DIR  # noqa: E402

from app.ml import schema  # noqa: E402
from app.ml.calibration import (  # noqa: E402
    Calibrator,
    brier_score,
    expected_calibration_error,
    fit_calibrator,
)
from app.ml.data import load_split  # noqa: E402
from app.ml.features import build_features, categorical_feature_names, extract_target, feature_names  # noqa: E402
from app.ml.metrics import classification_metrics  # noqa: E402

SEED = 42

BASE_PARAMS = {
    "objective": "binary",
    "metric": ["auc", "binary_logloss"],
    "verbosity": -1,
    "seed": SEED,
    "bagging_seed": SEED,
    "feature_fraction_seed": SEED,
    "data_random_seed": SEED,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 4,
}

# Deliberately small, regularization-oriented search. This is a buildathon
# risk engine, not a leaderboard entry -- credibility matters more than the
# third decimal place of AUC.
PARAM_GRID = [
    {"num_leaves": 31, "learning_rate": 0.05, "min_data_in_leaf": 50, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0},
    {"num_leaves": 63, "learning_rate": 0.05, "min_data_in_leaf": 100, "feature_fraction": 0.7, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 5.0},
    {"num_leaves": 15, "learning_rate": 0.05, "min_data_in_leaf": 100, "feature_fraction": 0.9, "bagging_fraction": 0.9, "bagging_freq": 1, "lambda_l2": 1.0},
    {"num_leaves": 31, "learning_rate": 0.03, "min_data_in_leaf": 200, "feature_fraction": 0.7, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 10.0},
]

CALIBRATION_METHODS = ("sigmoid", "isotonic")
MAX_BOOST_ROUNDS = 2000
EARLY_STOPPING_ROUNDS = 100


def set_global_seeds() -> None:
    random.seed(SEED)
    np.random.seed(SEED)


def stable_fold(customer_id: str, n_folds: int = 2) -> int:
    """Deterministic customer -> fold assignment (stable across runs/platforms)."""
    digest = hashlib.sha256(str(customer_id).encode()).hexdigest()
    return int(digest, 16) % n_folds


def customer_ids_for(disputes: pd.DataFrame, transactions: pd.DataFrame) -> pd.Series:
    """Map dispute_id -> customer_id (used only for grouping, never as a feature)."""
    mapping = disputes.merge(
        transactions[["transaction_id", "customer_id"]], on="transaction_id", how="left"
    ).set_index("dispute_id")["customer_id"]
    return mapping


def build_split(split_name: str):
    data = load_split(split_name)
    features = build_features(data.disputes, data.transactions, data.customers, data.evidence)
    target = extract_target(data.outcomes, features.index)
    customers = customer_ids_for(data.disputes, data.transactions).reindex(features.index)
    return features, target, customers


def select_threshold(y_true: np.ndarray, probability: np.ndarray) -> tuple[float, dict]:
    """Pick the F1-maximizing threshold on a candidate grid.

    Selected on validation data only; the locked test set never influences it.
    """
    from sklearn.metrics import f1_score

    candidates = np.round(np.arange(0.05, 0.96, 0.01), 2)
    scores = [(float(f1_score(y_true, (probability >= t).astype(int), zero_division=0)), float(t)) for t in candidates]
    best_f1, best_threshold = max(scores, key=lambda pair: (pair[0], -pair[1]))
    return best_threshold, {"grid_best_f1": best_f1, "n_candidates": len(candidates)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-search", action="store_true", help="use the first parameter set without searching")
    args = parser.parse_args()

    import lightgbm as lgb

    set_global_seeds()
    started_at = datetime.now(timezone.utc)

    print("Loading data and building features ...")
    X_train, y_train, _ = build_split("train")
    X_validation, y_validation, validation_customers = build_split("validation")

    names = feature_names()
    categoricals = categorical_feature_names()
    print(f"  train      : {X_train.shape}")
    print(f"  validation : {X_validation.shape}")
    print(f"  features   : {len(names)} ({len(categoricals)} categorical)")

    # --- customer-disjoint bisection of validation --------------------------
    validation_fold = validation_customers.map(stable_fold)
    mask_a = (validation_fold == 0).to_numpy()
    mask_b = ~mask_a
    X_val_a, y_val_a = X_validation[mask_a], y_validation[mask_a]
    X_val_b, y_val_b = X_validation[mask_b], y_validation[mask_b]
    customers_b = validation_customers[mask_b]
    print(f"  val_a (model selection)      : {X_val_a.shape[0]} rows")
    print(f"  val_b (calibration/metrics)  : {X_val_b.shape[0]} rows")

    overlap = set(validation_customers[mask_a]) & set(customers_b)
    if overlap:
        raise RuntimeError(f"val_a/val_b share {len(overlap)} customers -- bisection is not customer-disjoint")

    train_dataset = lgb.Dataset(
        X_train, label=y_train, categorical_feature=categoricals, free_raw_data=False
    )
    val_a_dataset = lgb.Dataset(
        X_val_a, label=y_val_a, categorical_feature=categoricals, reference=train_dataset, free_raw_data=False
    )

    # --- hyperparameter selection on val_a ----------------------------------
    grid = PARAM_GRID[:1] if args.no_search else PARAM_GRID
    print(f"\nSelecting hyperparameters on val_a ({len(grid)} configuration(s)) ...")
    search_results = []
    best = None
    for index, candidate in enumerate(grid):
        params = {**BASE_PARAMS, **candidate}
        booster = lgb.train(
            params,
            train_dataset,
            num_boost_round=MAX_BOOST_ROUNDS,
            valid_sets=[val_a_dataset],
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False), lgb.log_evaluation(0)],
        )
        auc = float(booster.best_score["valid_0"]["auc"])
        record = {"params": candidate, "val_a_auc": auc, "best_iteration": int(booster.best_iteration)}
        search_results.append(record)
        print(f"  [{index + 1}/{len(grid)}] val_a AUC={auc:.5f} iters={booster.best_iteration} {candidate}")
        if best is None or auc > best["val_a_auc"]:
            best = record

    best_params = {**BASE_PARAMS, **best["params"]}
    best_iteration = best["best_iteration"]
    print(f"  chosen: val_a AUC={best['val_a_auc']:.5f}, {best_iteration} iterations")

    # --- final fit on train only, at the selected iteration count -----------
    print("\nFitting final model on train ...")
    model = lgb.train(best_params, train_dataset, num_boost_round=best_iteration)

    raw_val_b = np.asarray(model.predict(X_val_b), dtype=float)
    y_val_b_array = y_val_b.to_numpy()

    # --- calibration: cross-fit within val_b to select the method ----------
    print("\nSelecting calibration method (cross-fitted within val_b) ...")
    fold_b = customers_b.map(lambda c: stable_fold(c, n_folds=2)).to_numpy()
    # re-hash with a salt so this bisection is independent of the a/b split
    fold_b = np.array([stable_fold(f"calib::{c}", 2) for c in customers_b], dtype=int)

    calibration_report: dict[str, dict] = {}
    out_of_fold: dict[str, np.ndarray] = {}
    for method in CALIBRATION_METHODS:
        oof = np.zeros_like(raw_val_b)
        for fold in (0, 1):
            fit_mask = fold_b != fold
            apply_mask = ~fit_mask
            if fit_mask.sum() == 0 or apply_mask.sum() == 0:
                continue
            calibrator = fit_calibrator(method, raw_val_b[fit_mask], y_val_b_array[fit_mask])
            oof[apply_mask] = calibrator.predict(raw_val_b[apply_mask])
        out_of_fold[method] = oof
        calibration_report[method] = {
            "oof_brier": brier_score(y_val_b_array, oof),
            "oof_ece": expected_calibration_error(y_val_b_array, oof),
        }
        print(
            f"  {method:9s} OOF Brier={calibration_report[method]['oof_brier']:.5f} "
            f"OOF ECE={calibration_report[method]['oof_ece']:.5f}"
        )

    uncalibrated_brier = brier_score(y_val_b_array, raw_val_b)
    calibration_report["uncalibrated"] = {
        "oof_brier": uncalibrated_brier,
        "oof_ece": expected_calibration_error(y_val_b_array, raw_val_b),
    }
    print(f"  {'raw':9s} Brier={uncalibrated_brier:.5f} ECE={calibration_report['uncalibrated']['oof_ece']:.5f}")

    chosen_method = min(CALIBRATION_METHODS, key=lambda m: calibration_report[m]["oof_brier"])
    print(f"  chosen calibration method: {chosen_method} (lowest out-of-fold Brier)")

    # Threshold from out-of-fold calibrated probabilities (no in-sample optimism).
    threshold, threshold_info = select_threshold(y_val_b_array, out_of_fold[chosen_method])
    print(f"  operating threshold (F1-max on val_b OOF): {threshold}")

    # Ship a calibrator refit on all of val_b.
    calibrator = fit_calibrator(chosen_method, raw_val_b, y_val_b_array)

    # --- validation metrics (honest: OOF calibrated) ------------------------
    validation_metrics = {
        "raw": classification_metrics(y_val_b_array, raw_val_b, threshold),
        "calibrated_out_of_fold": classification_metrics(
            y_val_b_array, out_of_fold[chosen_method], threshold
        ),
    }
    print(
        f"\nValidation (val_b, n={len(y_val_b_array)}): "
        f"ROC-AUC={validation_metrics['calibrated_out_of_fold']['roc_auc']:.4f} "
        f"PR-AUC={validation_metrics['calibrated_out_of_fold']['pr_auc']:.4f} "
        f"F1={validation_metrics['calibrated_out_of_fold']['f1']:.4f} "
        f"Brier={validation_metrics['calibrated_out_of_fold']['brier_score']:.4f}"
    )

    # --- persist artifacts --------------------------------------------------
    models_directory = schema.models_dir()
    models_directory.mkdir(parents=True, exist_ok=True)

    model.save_model(str(models_directory / schema.MODEL_FILENAME))

    importance_gain = model.feature_importance(importance_type="gain")
    importance_split = model.feature_importance(importance_type="split")

    (models_directory / schema.FEATURE_SCHEMA_FILENAME).write_text(
        json.dumps(
            {
                "feature_schema_version": schema.FEATURE_SCHEMA_VERSION,
                "model_version": schema.MODEL_VERSION,
                "dataset_version": schema.DATASET_VERSION,
                "feature_names": names,
                "categorical_features": {k: list(v) for k, v in schema.CATEGORICAL_FEATURES.items()},
                "n_features": len(names),
                "forbidden_columns": schema.FORBIDDEN_COLUMNS,
                "evidence_types": list(schema.ALL_EVIDENCE_TYPES),
            },
            indent=2,
        )
    )

    (models_directory / schema.CALIBRATOR_FILENAME).write_text(json.dumps(calibrator.to_dict(), indent=2))

    locked_metadata_path = METADATA_DIR / "locked_test_metadata.json"
    locked_checksum = (
        json.loads(locked_metadata_path.read_text())["checksum_sha256"] if locked_metadata_path.exists() else None
    )

    (models_directory / schema.MODEL_CONFIG_FILENAME).write_text(
        json.dumps(
            {
                "model_version": schema.MODEL_VERSION,
                "feature_schema_version": schema.FEATURE_SCHEMA_VERSION,
                "dataset_version": schema.DATASET_VERSION,
                "algorithm": "LightGBM binary classifier",
                "objective": "binary",
                "seed": SEED,
                "params": best_params,
                "num_boost_round": best_iteration,
                "calibration_method": chosen_method,
                "operating_threshold": threshold,
                "trained_at": started_at.isoformat(),
                "locked_test_checksum_at_training": locked_checksum,
                "split_usage": {
                    "train": "model fitting",
                    "val_a": "early stopping + hyperparameter selection",
                    "val_b": "calibration fitting/selection, threshold selection, reported validation metrics",
                    "locked_test": "never used during training",
                },
                "train_rows": int(len(X_train)),
                "val_a_rows": int(len(X_val_a)),
                "val_b_rows": int(len(X_val_b)),
            },
            indent=2,
        )
    )

    (models_directory / schema.TRAINING_METRICS_FILENAME).write_text(
        json.dumps(
            {
                "model_version": schema.MODEL_VERSION,
                "trained_at": started_at.isoformat(),
                "hyperparameter_search": search_results,
                "chosen_params": best["params"],
                "best_iteration": best_iteration,
                "calibration": calibration_report,
                "chosen_calibration_method": chosen_method,
                "operating_threshold": threshold,
                "threshold_selection": threshold_info,
                "validation_metrics": validation_metrics,
                "feature_importance_gain": {
                    name: float(value)
                    for name, value in sorted(
                        zip(names, importance_gain), key=lambda kv: -kv[1]
                    )
                },
                "feature_importance_split": {
                    name: int(value)
                    for name, value in sorted(zip(names, importance_split), key=lambda kv: -kv[1])
                },
            },
            indent=2,
        )
    )

    print(f"\nArtifacts written to {models_directory}:")
    for filename in (
        schema.MODEL_FILENAME,
        schema.FEATURE_SCHEMA_FILENAME,
        schema.MODEL_CONFIG_FILENAME,
        schema.CALIBRATOR_FILENAME,
        schema.TRAINING_METRICS_FILENAME,
    ):
        print(f"  {filename}")

    print("\nTop 10 features by gain:")
    for name, value in sorted(zip(names, importance_gain), key=lambda kv: -kv[1])[:10]:
        print(f"  {name:45s} {value:12.1f}")

    print("\nTraining complete. The locked test set was NOT used.")


if __name__ == "__main__":
    main()
