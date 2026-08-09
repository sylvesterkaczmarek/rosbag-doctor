from __future__ import annotations

from pathlib import Path

import pytest

from rosbag_doctor.readers import BagReadError, read_bag
from rosbag_doctor.stats import topic_stats

mcap_writer = pytest.importorskip("mcap.writer")
Writer = mcap_writer.Writer
CompressionType = mcap_writer.CompressionType


def _write_mcap(path: Path, *, enable_data_crcs: bool = False, payload: bytes = b"x") -> None:
    with path.open("wb") as stream:
        writer = Writer(
            stream,
            compression=CompressionType.NONE,
            enable_crcs=True,
            enable_data_crcs=enable_data_crcs,
        )
        writer.start()
        schema_id = writer.register_schema(name="sensor_msgs/msg/Imu", encoding="ros2msg", data=b"")
        channel_id = writer.register_channel(schema_id=schema_id, topic="/imu", message_encoding="cdr")
        start = 1_700_000_000_000_000_000
        for index in range(100):
            timestamp = start + index * 10_000_000
            writer.add_message(
                channel_id=channel_id,
                log_time=timestamp,
                publish_time=timestamp,
                data=payload,
            )
        writer.finish()


def test_reads_mcap_without_message_deserialization(tmp_path: Path):
    path = tmp_path / "sample.mcap"
    _write_mcap(path)

    bag = read_bag(path)
    assert bag.storage == "mcap"
    assert bag.total_messages == 100
    stat = topic_stats(bag)[0]
    assert stat.name == "/imu"
    assert abs(stat.effective_rate_hz - 100) < 0.01


def test_mcap_data_crc_corruption_is_rejected(tmp_path: Path):
    path = tmp_path / "crc.mcap"
    probe = b"ROSBagDoctorCRCProbe"
    _write_mcap(path, enable_data_crcs=True, payload=probe)

    data = bytearray(path.read_bytes())
    location = data.find(probe)
    assert location >= 0
    data[location] ^= 0x01
    path.write_bytes(data)

    with pytest.raises(BagReadError):
        read_bag(path)
