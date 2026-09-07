# Limitations

ROSBag Doctor focuses on recording-container integrity and recording-timeline quality.

It currently does not validate:

- ROS message payload contents
- `header.stamp` values inside messages
- TF tree connectivity or transform semantics
- camera image decoding or corruption
- calibration files
- point-cloud structure
- physical plausibility of sensor values
- network packet loss before data reaches rosbag2
- DDS QoS compatibility during the original recording
- MCAP attachment CRCs and index consistency
- every possible SQLite or MCAP structural constraint
- file-compressed rosbag2 storage such as `.db3.zstd` or `.mcap.zstd` without prior decompression

The tool retains compact 64-bit timestamp arrays in memory for each topic. Timestamp memory grows in proportion to message count, with additional arrays for statistics and sync checks. SQLite queries omit payload blobs. MCAP traversal reads message bytes and decompresses one chunk at a time, so peak memory also depends on the largest chunk or record. Summary CRC verification reads the summary again in bounded blocks.

Automatic gap warnings are intentionally conservative. For production checks, a committed YAML policy is preferred because the expected rate and allowed gap are properties of the robot or experiment, not properties ROSBag Doctor can infer reliably from every bag.

Inspect completed recordings. SQLite uses a consistent read transaction within each file, but split files and metadata are not an atomic snapshot of a live recorder. MCAP files still being written may be incomplete.

Coverage describes the first-to-last time span and does not quantify data density inside it. Sync offsets use directional nearest recording timestamps, may reuse a target sample and cannot prove physical sensor synchronisation.
