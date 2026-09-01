"""Probability calibration for the winnability model.

A raw LightGBM score is a good *ranking* but not necessarily a trustworthy
*probability*. Because downstream phases will compare a probability against
monetary quantities (expected recovery vs. contest cost), the number has to
mean what it says: among cases scored 0.7, roughly 70% should actually be won.

Two calibrators are supported, both fitted on validation data only:
  - `sigmoid`  (Platt scaling): logistic regression on the model's logit
  - `isotonic` (isotonic regression): monotone, non-parametric

Both serialize to plain JSON rather than pickle, so an artifact stays
inspectable, diffable, and portable across library versions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_EPS = 1e-6


def _to_logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability, _EPS, 1.0 - _EPS)
    return np.log(clipped / (1.0 - clipped))


def brier_score(y_true: np.ndarray, probability: np.ndarray) -> float:
    return float(np.mean((probability - y_true) ** 2))


def expected_calibration_error(
    y_true: np.ndarray, probability: np.ndarray, n_bins: int = 10
) -> float:
    """Equal-width-bin ECE: mean |confidence - accuracy|, weighted by bin size."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_index = np.clip(np.digitize(probability, bin_edges[1:-1], right=False), 0, n_bins - 1)
    total = len(probability)
    error = 0.0
    for b in range(n_bins):
        mask = bin_index == b
        count = int(mask.sum())
        if count == 0:
            continue
        error += (count / total) * abs(probability[mask].mean() - y_true[mask].mean())
    return float(error)


def calibration_curve_points(
    y_true: np.ndarray, probability: np.ndarray, n_bins: int = 10
) -> list[dict[str, float]]:
    """Reliability-diagram points (as data, so callers can plot or report)."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_index = np.clip(np.digitize(probability, bin_edges[1:-1], right=False), 0, n_bins - 1)
    points: list[dict[str, float]] = []
    for b in range(n_bins):
        mask = bin_index == b
        count = int(mask.sum())
        if count == 0:
            continue
        points.append(
            {
                "bin_lower": float(bin_edges[b]),
                "bin_upper": float(bin_edges[b + 1]),
                "count": count,
                "mean_predicted": float(probability[mask].mean()),
                "observed_frequency": float(y_true[mask].mean()),
            }
        )
    return points


@dataclass
class Calibrator:
    """A fitted probability calibrator, serializable to/from JSON."""

    method: str
    # sigmoid parameters
    coefficient: float | None = None
    intercept: float | None = None
    # isotonic parameters (piecewise-constant/linear interpolation knots)
    x_thresholds: list[float] | None = None
    y_thresholds: list[float] | None = None

    def predict(self, raw_probability: np.ndarray) -> np.ndarray:
        raw_probability = np.asarray(raw_probability, dtype=float)
        if self.method == "sigmoid":
            if self.coefficient is None or self.intercept is None:
                raise ValueError("sigmoid calibrator is not fitted")
            z = self.coefficient * _to_logit(raw_probability) + self.intercept
            return 1.0 / (1.0 + np.exp(-z))
        if self.method == "isotonic":
            if not self.x_thresholds or not self.y_thresholds:
                raise ValueError("isotonic calibrator is not fitted")
            calibrated = np.interp(
                raw_probability,
                np.asarray(self.x_thresholds, dtype=float),
                np.asarray(self.y_thresholds, dtype=float),
            )
            return np.clip(calibrated, 0.0, 1.0)
        if self.method == "identity":
            return raw_probability
        raise ValueError(f"unknown calibration method '{self.method}'")

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "coefficient": self.coefficient,
            "intercept": self.intercept,
            "x_thresholds": self.x_thresholds,
            "y_thresholds": self.y_thresholds,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Calibrator":
        return cls(
            method=payload["method"],
            coefficient=payload.get("coefficient"),
            intercept=payload.get("intercept"),
            x_thresholds=payload.get("x_thresholds"),
            y_thresholds=payload.get("y_thresholds"),
        )


def fit_calibrator(method: str, raw_probability: np.ndarray, y_true: np.ndarray) -> Calibrator:
    """Fit a calibrator. `raw_probability`/`y_true` must come from validation data."""
    raw_probability = np.asarray(raw_probability, dtype=float)
    y_true = np.asarray(y_true, dtype=float)

    if method == "sigmoid":
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
        model.fit(_to_logit(raw_probability).reshape(-1, 1), y_true)
        return Calibrator(
            method="sigmoid",
            coefficient=float(model.coef_[0][0]),
            intercept=float(model.intercept_[0]),
        )

    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(raw_probability, y_true)
        return Calibrator(
            method="isotonic",
            x_thresholds=[float(v) for v in model.X_thresholds_],
            y_thresholds=[float(v) for v in model.y_thresholds_],
        )

    if method == "identity":
        return Calibrator(method="identity")

    raise ValueError(f"unknown calibration method '{method}'")
