from __future__ import annotations

import math
from pathlib import Path

import yaml

from .config import ConfigError
from .models import TopicStats
from .output import write_text_safely
from .readers import read_bag
from .stats import topic_stats


def _finite_option(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a finite number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ConfigError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ConfigError(f"{name} must be a finite number")
    return result


def _looks_periodic(stat: TopicStats) -> bool:
    if (
        stat.count < 20
        or stat.median_period_ms is None
        or stat.p95_period_ms is None
        or stat.effective_rate_hz is None
        or stat.monotonic_violations
    ):
        return False
    if stat.median_period_ms <= 0:
        return False
    if stat.p95_period_ms > stat.median_period_ms * 1.5:
        return False
    if stat.count > 1 and stat.duplicate_timestamps / (stat.count - 1) >= 0.01:
        return False
    return True


def build_baseline(
    path: str | Path,
    *,
    rate_tolerance: float = 0.15,
    gap_multiplier: float = 1.5,
) -> dict:
    rate_tolerance = _finite_option(rate_tolerance, "rate_tolerance")
    gap_multiplier = _finite_option(gap_multiplier, "gap_multiplier")
    if not 0 <= rate_tolerance <= 1:
        raise ConfigError("rate_tolerance must be between 0 and 1")
    if gap_multiplier < 1:
        raise ConfigError("gap_multiplier must be >= 1")

    bag = read_bag(path)
    stats = topic_stats(bag)
    topics: dict[str, dict] = {}
    for stat in stats:
        rule: dict[str, object] = {"required": True}
        if _looks_periodic(stat):
            assert stat.effective_rate_hz is not None
            assert stat.max_gap_ms is not None
            # Preserve the measured value so a zero-tolerance policy accepts
            # its source recording, including rates below 0.001 Hz.
            rule["rate_hz"] = stat.effective_rate_hz
            rule["rate_tolerance"] = rate_tolerance
            max_gap_ms = max(stat.max_gap_ms * gap_multiplier, stat.max_gap_ms + 1.0)
            if not math.isfinite(max_gap_ms):
                raise ConfigError(f"gap_multiplier produces a non-finite gap limit for {stat.name}")
            rule["max_gap_ms"] = max_gap_ms
        if stat.coverage is not None and stat.count >= 3:
            rule["min_coverage"] = max(0.0, min(0.99, stat.coverage * 0.95))
        topics[stat.name] = rule
    return {"version": 1, "topics": topics, "sync": []}


def write_baseline(
    path: str | Path,
    output: str | Path,
    *,
    rate_tolerance: float = 0.15,
    gap_multiplier: float = 1.5,
) -> Path:
    content = build_baseline(path, rate_tolerance=rate_tolerance, gap_multiplier=gap_multiplier)
    return write_text_safely(yaml.safe_dump(content, sort_keys=False), output, bag_paths=[path])
