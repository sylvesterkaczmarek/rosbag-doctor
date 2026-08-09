# Configuration

A policy is a YAML file with `version: 1`.

```yaml
version: 1

bag:
  min_duration_s: 30
  max_duration_s: 900
  min_messages: 1000

ignore:
  - /rosout
  - /parameter_events

topics:
  /imu:
    required: true
    rate_hz: 200
    rate_tolerance: 0.05
    max_gap_ms: 20
    max_jitter_ms: 2
    min_coverage: 0.98
    min_messages: 5000
    max_start_delay_ms: 500
    max_end_early_ms: 500

  /camera/*:
    required: true
    rate_hz: 30
    rate_tolerance: 0.10
    max_gap_ms: 100

sync:
  - name: camera-imu
    reference: /camera/image_raw
    topics:
      - /camera/image_raw
      - /imu
    max_p95_offset_ms: 8
    max_offset_ms: 20
```

## Bag fields

| Field | Meaning |
|---|---|
| `min_duration_s` | Minimum bag time span |
| `max_duration_s` | Maximum bag time span |
| `min_messages` | Minimum total message count |

## Topic fields

| Field | Meaning |
|---|---|
| `required` | Fail if the exact topic or glob matches nothing |
| `rate_hz` | Expected effective rate |
| `rate_tolerance` | Fractional tolerance around `rate_hz`, default `0.10` |
| `max_gap_ms` | Largest allowed positive gap between consecutive recorded timestamps |
| `max_jitter_ms` | Largest allowed p95 absolute period deviation |
| `min_coverage` | Minimum topic span divided by bag span, from `0` to `1` |
| `min_messages` | Minimum messages on the topic |
| `max_start_delay_ms` | Maximum delay between bag start and first topic timestamp |
| `max_end_early_ms` | Maximum time between last topic timestamp and bag end |

Topic keys may contain shell-style globs such as `/camera/*` or `/robot/?/imu`. An exact topic rule wins over a matching glob. If several globs match, the longest pattern wins.

## Ignored topics

`ignore` accepts exact names or globs. Ignored topics are still read and shown in the report, but topic health checks are not applied to them.

## Sync fields

Each sync check compares every listed topic against a reference topic using nearest recorded timestamps.

| Field | Meaning |
|---|---|
| `name` | Human-readable name for the check |
| `topics` | Two or more exact topic names |
| `reference` | Topic whose timestamps are used as query points; defaults to the first topic |
| `max_p95_offset_ms` | Maximum allowed p95 nearest-timestamp offset |
| `max_offset_ms` | Maximum allowed nearest-timestamp offset |

Sync checks use recorded timestamps, not timestamps inside message payloads.

## Baseline generation

```bash
rosbag-doctor baseline known-good-run -o doctor.yaml
```

By default, the generated policy:

- marks every observed topic as required
- sets the observed effective rate with 15% tolerance when at least three messages exist
- sets a gap limit with 1.5× headroom over the observed maximum gap
- sets minimum coverage below the observed coverage

Options:

```bash
rosbag-doctor baseline known-good-run \
  --rate-tolerance 0.10 \
  --gap-multiplier 2.0 \
  -o doctor.yaml
```

A baseline is a starting point, not proof that the source recording was healthy. Generate it from a run you have already accepted.
