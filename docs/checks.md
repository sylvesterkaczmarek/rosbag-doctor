# Checks

ROSBag Doctor separates unconditional recording checks from policy checks.

## Checks that do not need a policy

### `empty-bag`

The bag contains no messages.

### `empty-topic`

A discovered topic contains no messages.

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

Effective rate falls outside `rate_hz ± rate_tolerance`.

Effective rate is:

```text
(message_count - 1) / (last_timestamp - first_timestamp)
```

### `gap-too-large`

Maximum positive consecutive timestamp gap exceeds `max_gap_ms`.

### `jitter-too-high`

p95 absolute deviation from the median positive period exceeds `max_jitter_ms`.

### `coverage-too-low`

Topic time span divided by the overall bag time span is below `min_coverage`.

### `starts-too-late`

The topic's first timestamp is too far after bag start.

### `ends-too-early`

The topic's final timestamp is too far before bag end.

### `sync-topic-missing`

A topic named in a sync group is absent.

### `sync-p95-too-high`

The p95 nearest-timestamp offset from the reference stream exceeds the configured limit.

### `sync-max-too-high`

The worst nearest-timestamp offset from the reference stream exceeds the configured limit.

### Bag-level checks

`bag-too-short`, `bag-too-long`, and `bag-too-few-messages` enforce optional bag-wide minimum or maximum values.
