from __future__ import annotations

import math

import numpy as np

from .models import BagData, TopicStats

NS_PER_S = 1_000_000_000.0
NS_PER_MS = 1_000_000.0


def _finite(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def bag_bounds(bag: BagData) -> tuple[int | None, int | None]:
    first_values: list[int] = []
    last_values: list[int] = []
    for topic in bag.topics.values():
        ts = topic.numpy()
        if ts.size:
            first_values.append(int(np.min(ts)))
            last_values.append(int(np.max(ts)))
    if not first_values:
        return None, None
    return min(first_values), max(last_values)


def topic_stats(bag: BagData) -> list[TopicStats]:
    bag_start, bag_end = bag_bounds(bag)
    bag_span_ns = (bag_end - bag_start) if bag_start is not None and bag_end is not None else 0
    results: list[TopicStats] = []

    for name in sorted(bag.topics):
        topic = bag.topics[name]
        ts = topic.numpy()
        count = int(ts.size)
        if count == 0:
            results.append(
                TopicStats(
                    name=name,
                    message_type=topic.message_type,
                    count=0,
                    first_timestamp_ns=None,
                    last_timestamp_ns=None,
                    duration_s=0.0,
                    effective_rate_hz=None,
                    median_rate_hz=None,
                    median_period_ms=None,
                    p95_period_ms=None,
                    max_gap_ms=None,
                    p95_jitter_ms=None,
                    monotonic_violations=0,
                    duplicate_timestamps=0,
                    zero_timestamps=0,
                    start_delay_ms=None,
                    end_early_ms=None,
                    coverage=None,
                    source_files=sorted(topic.source_files),
                )
            )
            continue

        first = int(ts[0])
        last = int(ts[-1])
        chronological_first = int(np.min(ts))
        chronological_last = int(np.max(ts))
        duration_ns = max(0, chronological_last - chronological_first)
        diffs = np.diff(ts) if count > 1 else np.empty(0, dtype=np.int64)
        positive = diffs[diffs > 0]
        monotonic_violations = int(np.count_nonzero(diffs < 0))
        duplicates = int(np.count_nonzero(diffs == 0))
        zero_timestamps = int(np.count_nonzero(ts == 0))

        if positive.size:
            median_period_ns = float(np.median(positive))
            p95_period_ns = float(np.percentile(positive, 95))
            max_gap_ns = float(np.max(positive))
            deviations = np.abs(positive - median_period_ns)
            p95_jitter_ns = float(np.percentile(deviations, 95))
            median_rate_hz = NS_PER_S / median_period_ns if median_period_ns > 0 else None
        else:
            median_period_ns = p95_period_ns = max_gap_ns = p95_jitter_ns = None
            median_rate_hz = None

        effective_rate_hz = (
            (count - 1) * NS_PER_S / duration_ns if count > 1 and duration_ns > 0 else None
        )
        start_delay_ms = (
            (chronological_first - bag_start) / NS_PER_MS if bag_start is not None else None
        )
        end_early_ms = (
            (bag_end - chronological_last) / NS_PER_MS if bag_end is not None else None
        )
        coverage = duration_ns / bag_span_ns if bag_span_ns > 0 else (1.0 if count else None)

        results.append(
            TopicStats(
                name=name,
                message_type=topic.message_type,
                count=count,
                first_timestamp_ns=first,
                last_timestamp_ns=last,
                duration_s=duration_ns / NS_PER_S,
                effective_rate_hz=_finite(effective_rate_hz),
                median_rate_hz=_finite(median_rate_hz),
                median_period_ms=_finite(median_period_ns / NS_PER_MS if median_period_ns is not None else None),
                p95_period_ms=_finite(p95_period_ns / NS_PER_MS if p95_period_ns is not None else None),
                max_gap_ms=_finite(max_gap_ns / NS_PER_MS if max_gap_ns is not None else None),
                p95_jitter_ms=_finite(p95_jitter_ns / NS_PER_MS if p95_jitter_ns is not None else None),
                monotonic_violations=monotonic_violations,
                duplicate_timestamps=duplicates,
                zero_timestamps=zero_timestamps,
                start_delay_ms=_finite(start_delay_ms),
                end_early_ms=_finite(end_early_ms),
                coverage=_finite(coverage),
                source_files=sorted(topic.source_files),
            )
        )
    return results


def nearest_offsets_ms(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    if reference.size == 0 or target.size == 0:
        return np.empty(0, dtype=np.float64)
    ref = np.sort(reference.astype(np.int64, copy=False))
    tgt = np.sort(target.astype(np.int64, copy=False))
    indices = np.searchsorted(tgt, ref)
    right_idx = np.clip(indices, 0, tgt.size - 1)
    left_idx = np.clip(indices - 1, 0, tgt.size - 1)
    right = np.abs(tgt[right_idx] - ref)
    left = np.abs(tgt[left_idx] - ref)
    return np.minimum(left, right).astype(np.float64) / NS_PER_MS
