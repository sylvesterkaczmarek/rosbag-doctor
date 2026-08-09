from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


@dataclass
class TopicRule:
    required: bool = False
    rate_hz: float | None = None
    rate_tolerance: float = 0.10
    max_gap_ms: float | None = None
    max_jitter_ms: float | None = None
    min_coverage: float | None = None
    min_messages: int | None = None
    max_start_delay_ms: float | None = None
    max_end_early_ms: float | None = None


@dataclass
class SyncRule:
    name: str
    topics: list[str]
    reference: str
    max_p95_offset_ms: float | None = None
    max_offset_ms: float | None = None


@dataclass
class BagRule:
    min_duration_s: float | None = None
    max_duration_s: float | None = None
    min_messages: int | None = None


@dataclass
class DoctorConfig:
    version: int = 1
    bag: BagRule = field(default_factory=BagRule)
    topics: dict[str, TopicRule] = field(default_factory=dict)
    sync: list[SyncRule] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)


def _number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field_name} must be a number")
    return float(value)


def _integer(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{field_name} must be an integer")
    return value


def _topic_rule(raw: dict[str, Any], name: str) -> TopicRule:
    allowed = {
        "required", "rate_hz", "rate_tolerance", "max_gap_ms", "max_jitter_ms",
        "min_coverage", "min_messages", "max_start_delay_ms", "max_end_early_ms",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigError(f"Unknown fields for topic {name}: {', '.join(sorted(unknown))}")
    required = raw.get("required", False)
    if not isinstance(required, bool):
        raise ConfigError(f"topics.{name}.required must be true or false")
    rule = TopicRule(
        required=required,
        rate_hz=_number(raw.get("rate_hz"), f"topics.{name}.rate_hz"),
        rate_tolerance=float(_number(raw.get("rate_tolerance", 0.10), f"topics.{name}.rate_tolerance") or 0.0),
        max_gap_ms=_number(raw.get("max_gap_ms"), f"topics.{name}.max_gap_ms"),
        max_jitter_ms=_number(raw.get("max_jitter_ms"), f"topics.{name}.max_jitter_ms"),
        min_coverage=_number(raw.get("min_coverage"), f"topics.{name}.min_coverage"),
        min_messages=_integer(raw.get("min_messages"), f"topics.{name}.min_messages"),
        max_start_delay_ms=_number(raw.get("max_start_delay_ms"), f"topics.{name}.max_start_delay_ms"),
        max_end_early_ms=_number(raw.get("max_end_early_ms"), f"topics.{name}.max_end_early_ms"),
    )
    if rule.rate_hz is not None and rule.rate_hz <= 0:
        raise ConfigError(f"topics.{name}.rate_hz must be > 0")
    if not 0 <= rule.rate_tolerance <= 1:
        raise ConfigError(f"topics.{name}.rate_tolerance must be between 0 and 1")
    if rule.min_coverage is not None and not 0 <= rule.min_coverage <= 1:
        raise ConfigError(f"topics.{name}.min_coverage must be between 0 and 1")
    return rule


def load_config(path: str | Path | None) -> DoctorConfig:
    if path is None:
        return DoctorConfig()
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not read config {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Configuration root must be a mapping")
    version = raw.get("version", 1)
    if version != 1:
        raise ConfigError(f"Unsupported config version: {version}")
    allowed_root = {"version", "bag", "topics", "sync", "ignore"}
    unknown = set(raw) - allowed_root
    if unknown:
        raise ConfigError(f"Unknown configuration fields: {', '.join(sorted(unknown))}")

    bag_raw = raw.get("bag") or {}
    if not isinstance(bag_raw, dict):
        raise ConfigError("bag must be a mapping")
    bag_unknown = set(bag_raw) - {"min_duration_s", "max_duration_s", "min_messages"}
    if bag_unknown:
        raise ConfigError(f"Unknown bag fields: {', '.join(sorted(bag_unknown))}")
    bag = BagRule(
        min_duration_s=_number(bag_raw.get("min_duration_s"), "bag.min_duration_s"),
        max_duration_s=_number(bag_raw.get("max_duration_s"), "bag.max_duration_s"),
        min_messages=_integer(bag_raw.get("min_messages"), "bag.min_messages"),
    )

    topics_raw = raw.get("topics") or {}
    if not isinstance(topics_raw, dict):
        raise ConfigError,"topics must be a mapping")
    topics: dict[str, TopicRule] = {}
    for name, topic_raw in topics_raw.items():
        if not isinstance(name, str) or not isinstance(topic_raw, dict):
            raise ConfigError,"Each topics entry must map a topic name or glob to a mapping")
        topics[name] = _topic_rule(topic_raw, name)

    sync_raw = raw.get("sync") or []
    if not isinstance(sync_raw, list):
        raise ConfigError,"sync must be a list")
    sync: list[SyncRule] = []
    for index, item in enumerate(sync_raw):
        if not isinstance(item, dict):
            raise ConfigError(f"sync[{index}] must be a mapping")
        unknown_sync = set(item) - {"name", "topics", "reference", "max_p95_offset_ms", "max_offset_ms"}
        if unknown_sync:
            raise ConfigError(f"Unknown sync[{index}] fields: {', '.join(sorted(unknown_sync))}")
        topics_list = item.get("topics")
        if not isinstance(topics_list, list) or len(topics_list) < 2 or not all(isinstance(x, str) for x in topics_list):
            raise ConfigError(f"sync[{index}].topics must contain at least two topic names")
        reference = item.get("reference", topics_list[0])
        if reference not in topics_list:
            raise ConfigError(f"sync[{index}].reference must be listed in sync[{index}].topics")
        name = item.get("name") or f"sync-{index + 1}"
        if not isinstance(name, str):
            raise ConfigError(f"sync[{index}].name must be a string")
        sync.append(
            SyncRule(
                name=name,
                topics=topics_list,
                reference=reference,
                max_p95_offset_ms=_number(item.get("max_p95_offset_ms"), f"sync[{index}].max_p95_offset_ms"),
                max_offset_ms=_number(item.get("max_offset_ms"), f"sync[{index}].max_offset_ms"),
            )
        )

    ignore = raw.get("ignore") or []
    if not isinstance(ignore, list) or not all(isinstance(x, str) for x in ignore):
        raise ConfigError("ignore must be a list of topic names or glob patterns")

    return DoctorConfig(version=1, bag=bag, topics=topics, sync=sync, ignore=ignore)
