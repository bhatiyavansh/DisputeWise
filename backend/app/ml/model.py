"""Trained-model loading and scoring.

Wraps the persisted artifacts (LightGBM booster + calibrator + feature
schema) behind one object so the API, the evaluation scripts, and the tests
all score cases through exactly the same code path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml import explain, schema
from app.ml.calibration import Calibrator


class ModelNotAvailableError(RuntimeError):
    """Raised when model artifacts are missing.

    Artifacts are reproducible rather than committed -- see README
    ("python scripts/train_model.py").
    """


@dataclass
class CaseScore:
    case_id: str
    raw_probability: float
    calibrated_probability: float
    risk_band: str
    top_positive_factors: list[dict]
    top_negative_factors: list[dict]


class RiskModel:
    def __init__(
        self,
        booster,
        calibrator: Calibrator,
        feature_schema: dict,
        model_config: dict,
    ) -> None:
        self._booster = booster
        self._calibrator = calibrator
        self._feature_schema = feature_schema
        self._model_config = model_config
        self._explainer: explain.ShapExplainer | None = None

    # -- metadata ------------------------------------------------------------
    @property
    def model_version(self) -> str:
        return self._feature_schema["model_version"]

    @property
    def feature_schema_version(self) -> str:
        return self._feature_schema["feature_schema_version"]

    @property
    def calibration_method(self) -> str:
        return self._calibrator.method

    @property
    def feature_names(self) -> list[str]:
        return list(self._feature_schema["feature_names"])

    @property
    def config(self) -> dict:
        return dict(self._model_config)

    # -- prediction ----------------------------------------------------------
    def _align(self, features: pd.DataFrame) -> pd.DataFrame:
        expected = self.feature_names
        missing = set(expected) - set(features.columns)
        if missing:
            raise ValueError(f"feature matrix is missing columns: {sorted(missing)}")
        return features[expected]

    def predict_raw(self, features: pd.DataFrame) -> np.ndarray:
        aligned = self._align(features)
        return np.asarray(self._booster.predict(aligned), dtype=float)

    def predict_calibrated(self, features: pd.DataFrame) -> np.ndarray:
        return self._calibrator.predict(self.predict_raw(features))

    def calibrate(self, raw_probability: np.ndarray) -> np.ndarray:
        return self._calibrator.predict(raw_probability)

    # -- explanation ---------------------------------------------------------
    def explainer(self) -> explain.ShapExplainer:
        if self._explainer is None:
            self._explainer = explain.ShapExplainer(self._booster)
        return self._explainer

    def explain(self, features: pd.DataFrame) -> np.ndarray:
        return self.explainer().contributions(self._align(features))

    def score_cases(self, features: pd.DataFrame, top_n: int = 5) -> list[CaseScore]:
        aligned = self._align(features)
        raw = self.predict_raw(aligned)
        calibrated = self._calibrator.predict(raw)
        contributions = self.explain(aligned)
        names = self.feature_names

        scores: list[CaseScore] = []
        for position, case_id in enumerate(aligned.index):
            positive, negative = explain.top_factors(
                aligned.iloc[position], contributions[position], names, top_n=top_n
            )
            scores.append(
                CaseScore(
                    case_id=str(case_id),
                    raw_probability=float(raw[position]),
                    calibrated_probability=float(calibrated[position]),
                    risk_band=schema.risk_band(float(calibrated[position])),
                    top_positive_factors=positive,
                    top_negative_factors=negative,
                )
            )
        return scores


def _require(path: Path) -> Path:
    if not path.exists():
        raise ModelNotAvailableError(
            f"model artifact not found: {path}. Train the model first: python scripts/train_model.py"
        )
    return path


def load_model(models_directory: Path | None = None) -> RiskModel:
    import lightgbm as lgb

    directory = models_directory or schema.models_dir()

    booster = lgb.Booster(model_file=str(_require(directory / schema.MODEL_FILENAME)))
    feature_schema = json.loads(_require(directory / schema.FEATURE_SCHEMA_FILENAME).read_text())
    model_config = json.loads(_require(directory / schema.MODEL_CONFIG_FILENAME).read_text())
    calibrator = Calibrator.from_dict(
        json.loads(_require(directory / schema.CALIBRATOR_FILENAME).read_text())
    )

    return RiskModel(
        booster=booster,
        calibrator=calibrator,
        feature_schema=feature_schema,
        model_config=model_config,
    )


@lru_cache(maxsize=1)
def get_model() -> RiskModel:
    """Process-wide cached model, for the API request path."""
    return load_model()


def reset_model_cache() -> None:
    get_model.cache_clear()
