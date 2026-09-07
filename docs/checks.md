# Checks

ROSBag Doctor separates unconditional recording checks from policy checks.

## Checks that do not need a policy

### `empty-bag`

The bag contains no messages.

### `empty-topic`

A discovered topic contains no messages.


### `metadata-message-count-mismatch`

The total message count recorded in `metadata.yaml` differs from the number of messages actually read from the bag files.

### `metadata-topic-count-mismatch`

A per-topic message count recorded in `metadata.yaml` differs from the number of messages actually read.

### `topic-type-conflict`

The same topic name is declared with more than one non-unknown message type across the recording.

### `timestamp-regression`

A later recorded message on a topic has a smaller timestamp than the preceding recorded message. The reader preserves recorded order for this check.

### `zero-timestamp`

One or more messages use timestamp `0`. This is a warning because simulated-time recordings can legitimately expose clock-start issues that need interpretation.

### `duplicate-timestamps`

At least 1% of consecutive message pairs on a topic use the same timestamp.

### `large-gap`

A conservative warning used only on streams with at least 20 messages whose p95 period is within 1.5× of the median period. The maximum gap must exceed both 100 ms and 5× the median period.

This heuristic avoids treating every event-driven topic as periodic.

## Policy checks

### `required-topic-missing`

A required exact topic or glob matches no recorded topic.

### `too-few-messages`

A topic contains fewer messages than configured.

### `rate-out-of-range`

Effective rate falls outside `rate_hz × (1 ± rate_tolerance)`.

Effective rate is:

```text
(message_count - 1) / ((maximum_timestamp_ns - minimum_timestamp_ns) / 1e9)
```

The report's `first_timestamp_ns` and `last_timestamp_ns` retain recorded order; duration, coverage, start delay and early stop use timestamp extrema. A regression still produces an error even if the effective rate looks plausible.

### Unavailable measurements

`rate-unavailable`, `gap-unavailable`, `jitter-unavailable`, `coverage-unavailable`, `start-delay-unavailable` and `end-early-unavailable` fail an explicit policy when the required measurement cannot be computed. A single message, for example, cannot establish a gap or jitter measurement. Empty topics produce `empty-topic`.

### `gap-too-large`

Maximum positive consecutive timestamp gap exceeds `max_gap_ms`.

### `jitter-too-high`

p95 absolute deviation from the median positive period exceeds `max_jitter_ms`.

### `coverage-too-low`

Topic time span divided by the overall bag time span is below `min_coverage`. This measures endpoint coverage, so a stream with a long internal dropout can still have full coverage. Use `max_gap_ms` as well. When the entire bag has zero time span, a non-empty topic has coverage `1.0` by convention; it still has no measurable rate or positive interval.

### `starts-too-late`

The topic's earliest timestamp is too far after bag start.

### `ends-too-early`

The topic's latest timestamp is too far before bag end.

### `sync-topic-missing`

A topic named in a sync group is absent.

### `sync-no-samples`

A topic exists in a configured sync group but contains no recorded samples, so an offset cannot be measured.

### `sync-p95-too-high`

For each target, calculate a nearest-timestamp offset for every reference sample, then its p95 using NumPy's linear percentile interpolation. The reported group p95 is the largest target p95. Each target must meet the limit independently; adding healthy targets cannot dilute a failing target. Failure details list the per-target p95 offsets.

### `sync-max-too-high`

The largest nearest-timestamp offset across all targets exceeds the configured limit. Failure details list each target's maximum. `samples` counts all reference-target comparisons, including reuse of a target message as the nearest neighbour of several reference samples. Matching is directional and does not establish one-to-one sensor correspondence or physical acquisition synchronisation.

### Bag-level checks

`bag-too-short`, `bag-too-long`, and `bag-too-few-messages` enforce optional bag-wide minimum or maximum values.
