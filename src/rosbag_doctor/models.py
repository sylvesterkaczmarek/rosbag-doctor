from __future__ import annotations

from array import array
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class TopicSeries:
    name: str
    message_type: str = "unknown"
    timestamps_ns: array = field(default_factory=lambda: array("q"))
    source_files: set[str] = field(default_factory=set)
    observed_types: set[str] = field(default_factory=set)

    def register_type(self, message_type: str | None) -> None:
        normalized = str(message_type or "unknown")
        if normalized != "unknown":
            self.observed_types.add(normalized)
            if self.message_type == "unknown":
                self.message_type = normalized

    def add(self, timestamp_ns: int, source_file: str, message_type: str | None = None) -> None:
        self.timestamps_ns.append(int(timestamp_ns))
        self.source_files.add(source_file)
        self.register_type(message_type)

    def numpy(self) -> np.ndarray:
        if not self.timestamps_ns:
            return np.empty(0, dtype=np.int64)
        return np.frombuffer(self.timestamps_ns, dtype=np.int64)


@dataclass
class BagData:
    path: Path
    storage: str
    files: list[Path]
    topics: dict[str, TopicSeries] = field(default_factory=dict)
    reader_warnings: list[str] = field(default_factory=list)
    metadata_total_messages: int | None = None
    metadata_topic_counts: dict[str, int] = field(default_factory=dict)

    def get_or_create_topic(self, name: str, message_type: str = "unknown") -> TopicSeries:
        topic = self.topics.get(name)
        if topic is None:
            topic = TopicSeries(name=name, message_type="unknown")
            self.topics[name] = topic
        topic.register_type(message_type)
        return topic

    @property
    def total_messages(self) -> int:
        return sum(len(topic.timestamps_ns) for topic in self.topics.values())


@dataclass
class TopicStats:
    name: str
    message_type: str
    count: int
    first_timestamp_ns: int | None
    last_timestamp_ns: int | None
    duration_s: float
    effective_rate_hz: float | None
    median_rate_hz: float | None
    median_period_ms: float | None
    p95_period_ms: float | None
    max_gap_ms: float | None
    p95_jitter_ms: float | None
    monotonic_violations: int
    duplicate_timestamps: int
    zero_timestamps: int
    start_delay_ms: float | None
    end_early_ms: float | None
    coverage: float | None
    source_files: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    topic: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyncStats:
    name: str
    reference: str
    topics: list[str]
    samples: int
    p95_offset_ms: float | None
    max_offset_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    bag_path: str
    storage: str
    files: list[str]
    total_messages: int
    bag_start_ns: int | None
    bag_end_ns: int | None
    bag_duration_s: float
    status: str
    topics: list[TopicStats]
    issues: list[Issue]
    sync: list[SyncStats]
    config_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bag": {
                "path": self.bag_path,
                "storage": self.storage,
                "files": self.files,
                "total_messages": self.total_messages,
                "start_ns": self.bag_start_ns,
                "end_ns": self.bag_end_ns,
                "duration_s": self.bag_duration_s,
            },
            "status": self.status,
            "config": self.config_path,
            "topics": [topic.to_dict() for topic in self.topics],
            "sync": [item.to_dict() for item in self.sync],
            "issues": [issue.to_dict() for issue in self.issues],
        }
