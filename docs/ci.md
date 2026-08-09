# CI

ROSBag Doctor returns predictable exit codes and can write a JSON report, so it can gate recorded tests.

## GitHub Actions

```yaml
name: recorded-data-check

on:
  workflow_dispatch:

jobs:
  check-bag:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install ROSBag Doctor
        run: python -m pip install .

      - name: Check recording
        run: |
          rosbag-doctor test-data/run-042 \
            --config config/doctor.yaml \
            --json rosbag-doctor-report.json

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: rosbag-doctor-report
          path: rosbag-doctor-report.json
```

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | no errors; warnings are allowed unless `--strict` is set |
| `1` | health check failure |
| `2` | input, file, or configuration error |

## JSON report

The JSON document includes:

- bag path, format, files, duration, and message count
- per-topic rate, periods, gap, jitter, coverage, and timestamp anomalies
- sync statistics
- structured issue codes and severities
- overall `pass`, `warn`, or `fail` status

This makes the same check usable from shell scripts, CI systems, notebooks, or fleet-data pipelines.
