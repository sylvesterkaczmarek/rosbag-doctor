from __future__ import annotations

from pathlib import Path

import yaml

from .readers import read_bag
from .stats import topic_stats


def _round_rate(value: float) -> float:
    if value >= 100:
        return round(value, 1)
    if value >= 10:
        return round(value, 2)
    return round(value, 3)


def build_baseline(path: str | Path, *, rate_tolerance: float = 0.15, gap_multiplier: float = 1.5) -> dict:
    bag = read_bag(path)
    stats = topic_stats(bag)
    topics: dict[str, dict] = {}
    for stat in stats:
        rule: dict[str, object] = {"required": True}
        if stat.count >= 3 and stat.effective_rate_hz is not None:
            rule["rate_hz"] = _round_rate(stat.effective_rate_hz)
            rule["rate_tolerance"] = rate_tolerance
        if stat.max_gap_ms is not None:
            rule["max_gap_ms"] = round(max(stat.max_gap_ms * gap_multiplier, stat.max_gap_ms + 1.0), 2)
        if stat.coverage is not None and stat.count >= 3:
            rule["min_coverage"] = round(max(0.0, min(0.99, stat.coverage * 0.95)), 3)
        topics[stat.name] = rule
    return {"version": 1, "topics": topics, "sync": []}


def write_baseline(path: str | Path, output: str | Path, *, rate_tolerance: float = 0.15, gap_multiplier: float = 1.5) -> Path:
    content = build_baseline(path, rate_tolerance=rate_tolerance, gap_multiplier=gap_multiplier)
    output_path = Path(output)
    output_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return output_path
