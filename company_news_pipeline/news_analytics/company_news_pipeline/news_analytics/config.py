"""Configuration shared by company matching and analytics services."""

from __future__ import annotations

import json
import math
import os
from typing import Mapping


DEFAULT_PEER_WEIGHTS: dict[str, float] = {
    "okved": 0.35,
    "ownership_type": 0.20,
    "scale": 0.20,
    "region": 0.10,
    "age_stage": 0.05,
    "product_trade_network": 0.10,
}


def get_peer_weights(overrides: Mapping[str, float] | None = None) -> dict[str, float]:
    """Return nonnegative, normalized weights for the known peer dimensions."""

    weights = dict(DEFAULT_PEER_WEIGHTS)
    if overrides is None:
        raw = os.getenv("NEWS_ANALYTICS_PEER_WEIGHTS")
        if raw:
            try:
                overrides = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("NEWS_ANALYTICS_PEER_WEIGHTS must contain a JSON object") from exc
    if overrides:
        unknown = set(overrides) - set(weights)
        if unknown:
            raise ValueError(f"Unknown peer-weight dimensions: {sorted(unknown)}")
        weights.update({key: float(value) for key, value in overrides.items()})
    if any(not math.isfinite(value) or value < 0 for value in weights.values()):
        raise ValueError("Peer weights cannot be negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("At least one peer weight must be positive")
    return {key: value / total for key, value in weights.items()}
