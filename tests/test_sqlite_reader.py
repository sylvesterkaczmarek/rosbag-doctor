from __future__ import annotations

from rosbag_doctor.readers import read_bag
from rosbag_doctor.stats import topic_stats


def test_reads_rosbag2_sqlite_without_ros_installation(healthy_bag):
    bag = read_bag(healthy_bag)
    assert bag.storage == "sqlite3"
    assert bag.total_messages == 650
    assert set(bag.topics) == {"/imu", "/camera"}

    stats = {item.name: item for item in topic_stats(bag)}
    assert abs(stats["/imu"].effective_rate_hz - 100.0) < 0.01
    assert abs(stats["/camera"].effective_rate_hz - 30.0) < 0.01
    assert stats["/imu"].max_gap_ms == 10.0
