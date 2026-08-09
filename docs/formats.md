# Bag formats

## SQLite3

ROSBag Doctor opens `.db3` and `.sqlite3` files read-only and reads the standard rosbag2 `topics` and `messages` tables.

It uses:

- topic name
- message type
- `messages.timestamp`
- message row order

Payload blobs are not deserialized.

For split bags, files listed by `metadata.yaml` are processed in the listed order. Every referenced file must exist and remain inside the bag directory. ROSBag Doctor also verifies metadata message counts when they are available. If metadata is unavailable, matching files are discovered by filename.

## MCAP

MCAP files are read sequentially with the Python `mcap` library. ROSBag Doctor validates MCAP chunk and data-section CRCs when checksums are present, preserves declared channels even when they contain no messages, and uses channel topic names, schema names when present, and each message's `log_time`.

Payloads are not decoded. This means no ROS runtime or generated ROS message classes are required for timing checks.

## Timestamp scope

The tool currently measures the timestamp assigned to the recorded message by the storage format. It does not read a message's internal `header.stamp`.

That distinction matters when debugging sensor-driver latency, clock-domain conversion, or middleware delay. Those require payload-aware checks and are outside the current scope.
