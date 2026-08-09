from __future__ import annotations

from pathlib import Path

import yaml

from conftest import make_sqlite_bag
from rosbag_doctor.doctor import inspect_bag


def test_large_gap_is_flagged_by_explicit_policy(tmp_path: Path):
    start = 1_700_000_000_000_000_000
    timestamps = [start + i * 20_000_000 for i in range(100)]
    del timestamps[50:56]
    bag = make_sqlite_bag(tmp_path / "gap", {"/camera": ("sensor_msgs/msg/Image", timestamps)})
    config = tmp_path / "doctor.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "topics": {
                    "/camera": {
                        "required": True,
                        "rate_hz": 50,
                        "rate_tolerance": 0.1,
                        "max_gap_ms": 80,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    report = inspect_bag(bag, config)
    assert report.status == "fail"
    assert any(issue.code == "gap-too-large" for issue in report.issues)


def test_missing_required_topic_fails(healthy_bag, tmp_path: Path):
    config = tmp_path / "doctor.yaml"
    config.write_text("version: 1\ntopics:\n  /lidar:\n    required: true\n", encoding="utf-8")
    report = inspect_bag(healthy_bag, config)
    assert report.status == "fail"
    assert any(issue.code == "required-topic-missing" for issue in report.issues)


def test_sensor_sync_passes_for_nearby_streams(healthy_bag, tmp_path: Path):
    config = tmp_path / "doctor.yaml"
    config.write_text(
        """version: 1
sync:
  - name: camera-imu
    reference: /camera
    topics: [/camera, /imu]
    max_p95_offset_ms: 6
    max_offset_ms: 6
""",
        encoding="utf-8",
    )
    report = inspect_bag(healthy_bag, config)
    assert report.status == "pass"
    assert report.sync[0].p95_offset_ms is not None
    assert report.sync[0].p95_offset_ms <= 6


def test_glob_rule_applies_to_matching_topic(healthy_bag, tmp_path: Path):
    config = tmp_path / "doctor-glob.yaml"
    config.write_text(
        """version: 1
topics:
  /cam*:
    required: true
    rate_hz: 30
    rate_tolerance: 0.05
""",
        encoding="utf-8",
    )
    report = inspect_bag(healthy_bag, config)
    assert report.status == "pass"


def test_strict_turns_warning_into_failure(tmp_path: Path):
    start = 1_700_000_000_000_000_000
    timestamps = [start + i * 20_000_000 for i in range(100)]
    del timestamps[50:56]
    bag = make_sqlite_bag(tmp_path / "strict-gap", {"/camera": ("sensor_msgs/msg/Image", timestamps)})
    report = inspect_bag(bag, strict=True)
    assert report.status == "fail"
    assert any(issue.code == "large-gap" for issue in report.issues)
