# Changelog

## Unreleased

- Protect bag files, metadata, SQLite sidecars and inspection policies from accidental report or baseline overwrites; write outputs atomically.
- Reject malformed SQLite message references and timestamps, and read each database in one consistent transaction.
- Validate MCAP schema/channel references, summary CRCs and chunk structure in addition to existing chunk/data CRCs.
- Prevent signed timestamp overflow from producing false regressions or incorrect nearest offsets.
- Enforce sync p95 limits for every target independently.
- Reject non-finite and ambiguous YAML policies and fail explicit limits when their measurements are unavailable.
- Preserve precision in generated baseline policies and validate generation options before reading a recording.
- Retain health diagnostics and message type changes in comparisons.
- Include documentation, examples, workflows and tests in source distributions and test them against the installed wheel.

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
