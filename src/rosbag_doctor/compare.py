from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .doctor import inspect_bag


@dataclass
class TopicDelta:
    topic: str
    state: str
    base_rate_hz: float | None = None
    candidate_rate_hz: float | None = None
    rate_change_pct: float | None = None
    base_max_gap_ms: float | None = None
    candidate_max_gap_ms: float | None = None
    gap_change_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pct(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before == 0:
        return None
    return (after - before) / before * 100.0


def compare_bags(base: str | Path, candidate: str | Path) -> dict[str, Any]:
    base_report = inspect_bag(base)
    candidate_report = inspect_bag(candidate)
    base_topics = {x.name: x for x in base_report.topics}
    candidate_topics = {x.name: x for x in candidate_report.topics}
    deltas: list[TopicDelta] = []
    for name in sorted(set(base_topics) | set(candidate_topics)):
        before = base_topics.get(name)
        after = candidate_topics.get(name)
        if before is None:
            deltas.append(TopicDelta(topic=name, state="added", candidate_rate_hz=after.effective_rate_hz if after else None, candidate_max_gap_ms=after.max_gap_ms if after else None))
        elif after is None:
            deltas.append(TopicDelta(topic=name, state="removed", base_rate_hz=before.effective_rate_hz, base_max_gap_ms=before.max_gap_ms))
        else:
            deltas.append(
                TopicDelta(
                    topic=name,
                    state="present",
                    base_rate_hz=before.effective_rate_hz,
                    candidate_rate_hz=after.effective_rate_hz,
                    rate_change_pct=_pct(before.effective_rate_hz, after.effective_rate_hz),
                    base_max_gap_ms=before.max_gap_ms,
                    candidate_max_gap_ms=after.max_gap_ms,
                    gap_change_pct=_pct(before.max_gap_ms, after.max_gap_ms),
                )
            )
    return {
        "base": base_report.bag_path,
        "candidate": candidate_report.bag_path,
        "topics": [item.to_dict() for item in deltas],
    }
