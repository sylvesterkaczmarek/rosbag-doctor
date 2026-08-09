from __future__ import annotations

import fnmatch

import numpy as np

from .config import DoctorConfig, TopicRule
from .models import BagData, Issue, SyncStats, TopicStats
from .stats import bag_bounds, nearest_offsets_ms


def _ignored(topic: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(topic, pattern) for pattern in patterns)


def _matching_rule(topic: str, rules: dict[str, TopicRule]) -> TopicRule | None:
    exact = rules.get(topic)
    if exact is not None:
        return exact
    matches = [
        (pattern, rule)
        for pattern, rule in rules.items()
        if any(ch in pattern for ch in "*?[") and fnmatch.fnmatchcase(topic, pattern)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches[0][1]


def _severity_issues_for_topic(stat: TopicStats, rule: TopicRule | None) -> list[Issue]:
    issues: list[Issue] = []
    topic = stat.name

    if stat.count == 0:
        return [Issue("error", "empty-topic", "Topic contains no messages", topic=topic)]
    if stat.monotonic_violations:
        issues.append(
            Issue(
                "error",
                "timestamp-regression",
                f"{stat.monotonic_violations} recorded timestamp regression(s)",
                topic=topic,
                details={"count": stat.monotonic_violations},
            )
        )
    if stat.zero_timestamps:
        issues.append(
            Issue(
                "warning",
                "zero-timestamp",
                f"{stat.zero_timestamps} message(s) have timestamp 0",
                topic=topic,
                details={"count": stat.zero_timestamps},
            )
        )
    if (
        stat.duplicate_timestamps
        and stat.count > 1
        and stat.duplicate_timestamps / (stat.count - 1) >= 0.01
    ):
        issues.append(
            Issue(
                "warning",
                "duplicate-timestamps",
                f"{stat.duplicate_timestamps} consecutive message timestamp(s) are duplicated",
                topic=topic,
                details={"count": stat.duplicate_timestamps},
            )
        )

    if rule is None:
        # Conservative heuristic: flag only a large outlier gap on a stream that otherwise looks periodic.
        if (
            stat.count >= 20
            and stat.median_period_ms is not None
            and stat.p95_period_ms is not None
            and stat.max_gap_ms is not None
            and stat.p95_period_ms <= stat.median_period_ms * 1.5
            and stat.max_gap_ms > max(100.0, stat.median_period_ms * 5.0)
        ):
            issues.append(
                Issue(
                    "warning",
                    "large-gap",
                    f"Large timing gap detected: {stat.max_gap_ms:.1f} ms",
                    topic=topic,
                    details={"max_gap_ms": stat.max_gap_ms, "median_period_ms": stat.median_period_ms},
                )
            )
        return issues

    if rule.min_messages is not None and stat.count < rule.min_messages:
        issues.append(
            Issue(
                "error",
                "too-few-messages",
                f"Expected at least {rule.min_messages} messages, found {stat.count}",
                topic=topic,
            )
        )
    if rule.rate_hz is not None:
        measured = stat.effective_rate_hz
        if measured is None:
            issues.append(Issue("error", "rate-unavailable", "Could not measure topic rate", topic=topic))
        else:
            lower = rule.rate_hz * (1.0 - rule.rate_tolerance)
            upper = rule.rate_hz * (1.0 + rule.rate_tolerance)
            if not lower <= measured <= upper:
                issues.append(
                    Issue(
                        "error",
                        "rate-out-of-range",
                        f"Rate {measured:.2f} Hz is outside {lower:.2f}–{upper:.2f} Hz",
                        topic=topic,
                        details={
                            "measured_hz": measured,
                            "expected_hz": rule.rate_hz,
                            "tolerance": rule.rate_tolerance,
                        },
                    )
                )
    if rule.max_gap_ms is not None and stat.max_gap_ms is not None and stat.max_gap_ms > rule.max_gap_ms:
        issues.append(
            Issue(
                "error",
                "gap-too-large",
                f"Maximum gap {stat.max_gap_ms:.1f} ms exceeds {rule.max_gap_ms:.1f} ms",
                topic=topic,
            )
        )
    if (
        rule.max_jitter_ms is not None
        and stat.p95_jitter_ms is not None
        and stat.p95_jitter_ms > rule.max_jitter_ms
    ):
        issues.append(
            Issue(
                "error",
                "jitter-too-high",
                f"p95 jitter {stat.p95_jitter_ms:.2f} ms exceeds {rule.max_jitter_ms:.2f} ms",
                topic=topic,
            )
        )
    if rule.min_coverage is not None and stat.coverage is not None and stat.coverage < rule.min_coverage:
        issues.append(
            Issue(
                "error",
                "coverage-too-low",
                f"Coverage {stat.coverage:.1%} is below {rule.min_coverage:.1%}",
                topic=topic,
            )
        )
    if (
        rule.max_start_delay_ms is not None
        and stat.start_delay_ms is not None
        and stat.start_delay_ms > rule.max_start_delay_ms
    ):
        issues.append(
            Issue(
                "error",
                "starts-too-late",
                f"Topic starts {stat.start_delay_ms:.1f} ms after bag start",
                topic=topic,
            )
        )
    if (
        rule.max_end_early_ms is not None
        and stat.end_early_ms is not None
        and stat.end_early_ms > rule.max_end_early_ms
    ):
        issues.append(
            Issue(
                "error",
                "ends-too-early",
                f"Topic ends {stat.end_early_ms:.1f} ms before bag end",
                topic=topic,
            )
        )
    return issues


def run_checks(
    bag: BagData,
    stats: list[TopicStats],
    config: DoctorConfig,
) -> tuple[list[Issue], list[SyncStats]]:
    issues: list[Issue] = []
    sync_stats: list[SyncStats] = []

    bag_start, bag_end = bag_bounds(bag)
    duration_s = (bag_end - bag_start) / 1e9 if bag_start is not None and bag_end is not None else 0.0
    if bag.total_messages == 0:
        issues.append(Issue("error", "empty-bag", "Bag contains no messages"))
    if config.bag.min_duration_s is not None and duration_s < config.bag.min_duration_s:
        issues.append(
            Issue(
                "error",
                "bag-too-short",
                f"Bag duration {duration_s:.2f} s is below {config.bag.min_duration_s:.2f} s",
            )
        )
    if config.bag.max_duration_s is not None and duration_s > config.bag.max_duration_s:
        issues.append(
            Issue(
                "error",
                "bag-too-long",
                f"Bag duration {duration_s:.2f} s exceeds {config.bag.max_duration_s:.2f} s",
            )
        )
    if config.bag.min_messages is not None and bag.total_messages < config.bag.min_messages:
        issues.append(
            Issue(
                "error",
                "bag-too-few-messages",
                f"Bag contains {bag.total_messages} messages; expected at least {config.bag.min_messages}",
            )
        )

    if bag.metadata_total_messages is not None and bag.total_messages != bag.metadata_total_messages:
        issues.append(
            Issue(
                "error",
                "metadata-message-count-mismatch",
                f"metadata.yaml reports {bag.metadata_total_messages} messages but {bag.total_messages} were read",
                details={
                    "metadata_count": bag.metadata_total_messages,
                    "observed_count": bag.total_messages,
                },
            )
        )

    for topic_name, expected_count in sorted(bag.metadata_topic_counts.items()):
        observed_count = len(bag.topics[topic_name].timestamps_ns) if topic_name in bag.topics else 0
        if observed_count != expected_count:
            issues.append(
                Issue(
                    "error",
                    "metadata-topic-count-mismatch",
                    f"metadata.yaml reports {expected_count} messages but {observed_count} were read",
                    topic=topic_name,
                    details={"metadata_count": expected_count, "observed_count": observed_count},
                )
            )

    for topic_name, topic in sorted(bag.topics.items()):
        if len(topic.observed_types) > 1:
            observed = sorted(topic.observed_types)
            issues.append(
                Issue(
                    "error",
                    "topic-type-conflict",
                    f"Topic is declared with multiple message types: {', '.join(observed)}",
                    topic=topic_name,
                    details={"types": observed},
                )
            )

    stat_map = {stat.name: stat for stat in stats}
    for pattern, rule in config.topics.items():
        if not rule.required:
            continue
        if any(ch in pattern for ch in "*?["):
            matched = any(fnmatch.fnmatchcase(name, pattern) for name in stat_map)
        else:
            matched = pattern in stat_map
        if not matched:
            issues.append(
                Issue(
                    "error",
                    "required-topic-missing",
                    f"Required topic or pattern is missing: {pattern}",
                    topic=pattern,
                )
            )

    for stat in stats:
        if _ignored(stat.name, config.ignore):
            continue
        rule = _matching_rule(stat.name, config.topics)
        issues.extend(_severity_issues_for_topic(stat, rule))

    for rule in config.sync:
        missing = [name for name in rule.topics if name not in bag.topics]
        if missing:
            issues.append(
                Issue(
                    "error",
                    "sync-topic-missing",
                    f"Sync check '{rule.name}' is missing: {', '.join(missing)}",
                    details={"sync": rule.name, "missing": missing},
                )
            )
            sync_stats.append(SyncStats(rule.name, rule.reference, rule.topics, 0, None, None))
            continue

        reference = bag.topics[rule.reference].numpy()
        empty_topics = [name for name in rule.topics if bag.topics[name].numpy().size == 0]
        if empty_topics:
            issues.append(
                Issue(
                    "error",
                    "sync-no-samples",
                    f"Sync check '{rule.name}' has no samples for: {', '.join(empty_topics)}",
                    details={"sync": rule.name, "empty": empty_topics},
                )
            )
            sync_stats.append(SyncStats(rule.name, rule.reference, rule.topics, 0, None, None))
            continue

        all_offsets: list[np.ndarray] = []
        for topic_name in rule.topics:
            if topic_name == rule.reference:
                continue
            offsets = nearest_offsets_ms(reference, bag.topics[topic_name].numpy())
            if offsets.size:
                all_offsets.append(offsets)
        combined = np.concatenate(all_offsets)
        p95 = float(np.percentile(combined, 95))
        max_offset = float(np.max(combined))
        samples = int(combined.size)
        sync_stats.append(SyncStats(rule.name, rule.reference, rule.topics, samples, p95, max_offset))
        if rule.max_p95_offset_ms is not None and p95 > rule.max_p95_offset_ms:
            issues.append(
                Issue(
                    "error",
                    "sync-p95-too-high",
                    f"Sync '{rule.name}' p95 offset {p95:.2f} ms exceeds {rule.max_p95_offset_ms:.2f} ms",
                    details={"sync": rule.name, "p95_offset_ms": p95},
                )
            )
        if rule.max_offset_ms is not None and max_offset > rule.max_offset_ms:
            issues.append(
                Issue(
                    "error",
                    "sync-max-too-high",
                    f"Sync '{rule.name}' max offset {max_offset:.2f} ms exceeds {rule.max_offset_ms:.2f} ms",
                    details={"sync": rule.name, "max_offset_ms": max_offset},
                )
            )

    return issues, sync_stats


def report_status(issues: list[Issue], strict: bool = False) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "fail"
    if any(issue.severity == "warning" for issue in issues):
        return "fail" if strict else "warn"
    return "pass"
