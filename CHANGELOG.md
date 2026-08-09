# Changelog

## 0.1.0

- Read ROS 2 SQLite3 bags and MCAP files without a ROS installation.
- Report topic rates, timing gaps, jitter, timestamp regressions, duplicates, zero timestamps, and recording coverage.
- Enforce YAML health policies with CI-friendly exit codes.
- Measure nearest-timestamp offsets for configured sensor-sync groups.
- Generate a starter health policy from a known-good recording.
- Compare timing statistics between two recordings.
- Export machine-readable JSON reports.
