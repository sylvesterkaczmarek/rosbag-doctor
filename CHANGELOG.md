# Changelog

## 0.1.1

- Fail when `metadata.yaml` references missing files or paths outside the bag directory.
- Preserve and report zero-message SQLite topics.
- Verify metadata message counts against the data actually read.
- Detect conflicting message types for the same topic.
- Validate non-negative policy limits and inconsistent duration ranges.
- Validate MCAP chunk and data-section CRCs while reading.
- Avoid inferring periodic rate and gap rules for irregular event-driven topics.
- Handle URI metacharacters safely in SQLite filenames.
- Expand CI to supported Python versions and add a wheel-install smoke check.

## 0.1.0

- Read ROS 2 SQLite3 bags and MCAP files without a ROS installation.
- Report topic rates, timing gaps, jitter, timestamp regressions, duplicates, zero timestamps, and recording coverage.
- Enforce YAML health policies with CI-friendly exit codes.
- Measure nearest-timestamp offsets for configured sensor-sync groups.
- Generate a starter health policy from a known-good recording.
- Compare timing statistics between two recordings.
- Export machine-readable JSON reports.
