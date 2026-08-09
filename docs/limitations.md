# Limitations

ROSBag Doctor focuses on recording-timeline quality.

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

The tool retains compact 64-bit timestamp arrays in memory for each topic. Very large recordings therefore use memory roughly in proportion to message count, even though message payloads are never loaded.

Automatic gap warnings are intentionally conservative. For production checks, a committed YAML policy is preferred because the expected rate and allowed gap are properties of the robot or experiment, not properties ROSBag Doctor can infer reliably from every bag.
