from __future__ import annotations

from pathlib import Path

from .checks import report_status, run_checks
from .config import load_config
from .models import Report
from .readers import read_bag
from .stats import bag_bounds, topic_stats


def inspect_bag(
    bag_path: str | Path,
    config_path: str | Path | None = None,
    *,
    strict: bool = False,
) -> Report:
    config = load_config(config_path)
    bag = read_bag(bag_path)
    stats = topic_stats(bag)
    issues, sync = run_checks(bag, stats, config)
    bag_start, bag_end = bag_bounds(bag)
    duration_s = (bag_end - bag_start) / 1e9 if bag_start is not None and bag_end is not None else 0.0
    status = report_status(issues, strict=strict)
    return Report(
        bag_path=str(bag.path),
        storage=bag.storage,
        files=[path.name for path in bag.files],
        total_messages=bag.total_messages,
        bag_start_ns=bag_start,
        bag_end_ns=bag_end,
        bag_duration_s=duration_s,
        status=status,
        topics=stats,
        issues=issues,
        sync=sync,
        config_path=str(Path(config_path).expanduser().resolve()) if config_path is not None else None,
    )
