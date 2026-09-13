"""Pure, deterministic sensor feature and anomaly calculations.

This module deliberately contains no safety policy or actuator integration.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

MODEL_VERSION = "deterministic-baseline-1.0.0"


def extract_features(sensors: Mapping[str, Sequence[float]]) -> dict[str, float]:
    """Return stable statistical features for each sensor and the complete reading."""
    features: dict[str, float] = {}
    all_values: list[float] = []
    for name in sorted(sensors):
        values = [float(value) for value in sensors[name]]
        if not values:
            continue
        all_values.extend(values)
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        prefix = f"{name}."
        features[prefix + "count"] = float(len(values))
        features[prefix + "min"] = min(values)
        features[prefix + "max"] = max(values)
        features[prefix + "mean"] = mean
        features[prefix + "stddev"] = math.sqrt(variance)
        features[prefix + "range"] = max(values) - min(values)
        features[prefix + "last"] = values[-1]
        features[prefix + "delta"] = values[-1] - values[0]
    if all_values:
        features["reading.mean"] = sum(all_values) / len(all_values)
        features["reading.count"] = float(len(all_values))
    return {key: round(value, 10) for key, value in sorted(features.items())}


def score_anomaly(features: Mapping[str, float]) -> float:
    """Score unusual magnitude and variability on a deterministic 0..1 scale."""
    signals: list[float] = []
    for key, value in features.items():
        if key.endswith((".mean", ".last")) and not key.startswith("reading."):
            signals.append(min(abs(value) / 100.0, 1.0))
        elif key.endswith(".stddev"):
            signals.append(min(value / 25.0, 1.0))
    return round(max(signals, default=0.0), 10)
