from __future__ import annotations

from rosbag_doctor.baseline import build_baseline
from rosbag_doctor.config import DoctorConfig, load_config


def test_baseline_contains_observed_topics(healthy_bag, tmp_path):
    baseline = build_baseline(healthy_bag)
    assert baseline["version"] == 1
    assert baseline["topics"]["/imu"]["required"] is True
    assert abs(baseline["topics"]["/imu"]["rate_hz"] - 100) < 0.1


def test_generated_baseline_is_valid_yaml(healthy_bag, tmp_path):
    from rosbag_doctor.baseline import write_baseline

    path = write_baseline(healthy_bag, tmp_path / "generated.yaml")
    config = load_config(path)
    assert isinstance(config, DoctorConfig)
    assert "/camera" in config.topics
