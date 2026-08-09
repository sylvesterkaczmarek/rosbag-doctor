from __future__ import annotations

from pathlib import Path

import pytest

from rosbag_doctor.readers import read_bag
from rosbag_doctor.stats import topic_stats

mcap_writer = pytest.importorskip("mcap.writer")
Writer = mcap_writer.Writer


def test_reads_mcap_without_message_deserialization(tmp_path: Path):
    path = tmp_path / "sample.mcap"
    with path.open("wb") as stream:
        writer = Writer(stream)
        writer.start()
        schema_id = writer.register_schema(name="sensor_msgs/msg/Imu", encoding="ros2msg", data=b"")
        channel_id = writer.register_channel(schema_id=schema_id, topic="/imu", message_encoding="cdr")
        start = 1_700_000_000_000_000_000
        for index in range(100):
            timestamp = start + index * 10_000_000
            writer.add_message(channel_id=channel_id, log_time=timestamp, publish_time=timestamp, data=b"x")
        writer.finish()

    bag = read_bag(path)
    assert bag.storage == "mcap"
    assert bag.total_messages == 100
    stat = topic_stats(bag)[0]
    assert stat.name == "/imu"
    assert abs(stat.effective_rate_hz - 100) < 0.01
