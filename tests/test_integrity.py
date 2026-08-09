from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from conftest import make_sqlite_bag
from rosbag_doctor.baseline import build_baseline
from rosbag_doctor.config import ConfigError, load_config
from rosbag_doctor.doctor import inspect_bag
from rosbag_doctor.readers import BagReadError, read_bag


def _write_metadata(path: Path, *, files: list[str], message_count: int | None = None, topics=None) -> None:
    info: dict = {
        "version": 9,
        "storage_identifier": "sqlite3",
        "relative_file_paths": files,
    }
    if message_count is not None:
        info["message_count"] = message_count
    if topics is not None:
        info["topics_with_message_count"] = topics
    (path / "metadata.yaml").write_text(
        yaml.safe_dump({"rosbag2_bagfile_information": info}, sort_keys=False),
        encoding="utf-8",
    )


def test_missing_file_listed_in_metadata_is_fatal(tmp_path: Path):
    bag = make_sqlite_bag(tmp_path / "split", {"/imu": ("sensor_msgs/msg/Imu", [1, 2, 3])})
    _write_metadata(bag, files=["bag_0.db3", "bag_1.db3"])
    with pytest.raises(BagReadError, match="missing bag file"):
        read_bag(bag)


def test_metadata_path_cannot_escape_bag_directory(tmp_path: Path):
    outside = make_sqlite_bag(tmp_path / "outside", {"/imu": ("sensor_msgs/msg/Imu", [1, 2, 3])})
    bag = tmp_path / "bag"
    bag.mkdir()
    relative = str((outside / "bag_0.db3").relative_to(tmp_path))
    _write_metadata(bag, files=[f"../{relative}"])
    with pytest.raises(BagReadError, match="escapes the bag directory"):
        read_bag(bag)


def test_empty_sqlite_topic_is_preserved_and_reported(tmp_path: Path):
    bag = make_sqlite_bag(
        tmp_path / "empty-topic",
        {
            "/imu": ("sensor_msgs/msg/Imu", [100, 200, 300]),
            "/camera": ("sensor_msgs/msg/Image", []),
        },
    )
    report = inspect_bag(bag)
    assert "/camera" in {topic.name for topic in report.topics}
    assert any(issue.code == "empty-topic" and issue.topic == "/camera" for issue in report.issues)
    assert report.status == "fail"


def test_metadata_message_counts_are_verified(tmp_path: Path):
    bag = make_sqlite_bag(tmp_path / "counts", {"/imu": ("sensor_msgs/msg/Imu", [100, 200, 300])})
    topic_entry = {
        "topic_metadata": {
            "name": "/imu",
            "type": "sensor_msgs/msg/Imu",
            "serialization_format": "cdr",
        },
        "message_count": 4,
    }
    _write_metadata(bag, files=["bag_0.db3"], message_count=4, topics=[topic_entry])
    report = inspect_bag(bag)
    codes = {issue.code for issue in report.issues}
    assert "metadata-message-count-mismatch" in codes
    assert "metadata-topic-count-mismatch" in codes
    assert report.status == "fail"


def test_topic_type_conflict_is_reported(tmp_path: Path):
    bag = tmp_path / "type-conflict"
    bag.mkdir()
    db = bag / "bag_0.db3"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE topics(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            serialization_format TEXT NOT NULL,
            offered_qos_profiles TEXT NOT NULL
        );
        CREATE TABLE messages(
            id INTEGER PRIMARY KEY,
            topic_id INTEGER NOT NULL,
            timestamp INTEGER NOT NULL,
            data BLOB NOT NULL
        );
        INSERT INTO topics VALUES (1, '/sensor', 'pkg/msg/TypeA', 'cdr', '');
        INSERT INTO topics VALUES (2, '/sensor', 'pkg/msg/TypeB', 'cdr', '');
        INSERT INTO messages(topic_id, timestamp, data) VALUES (1, 100, X'01');
        INSERT INTO messages(topic_id, timestamp, data) VALUES (2, 200, X'02');
        """
    )
    connection.commit()
    connection.close()
    _write_metadata(bag, files=[db.name])

    report = inspect_bag(bag)
    assert any(issue.code == "topic-type-conflict" for issue in report.issues)
    assert report.status == "fail"


def test_sqlite_uri_special_characters_are_supported(tmp_path: Path):
    source = make_sqlite_bag(tmp_path / "source", {"/imu": ("sensor_msgs/msg/Imu", [1, 2, 3])})
    special = tmp_path / "bag?capture#1.db3"
    special.write_bytes((source / "bag_0.db3").read_bytes())
    bag = read_bag(special)
    assert bag.total_messages == 3
    assert "/imu" in bag.topics


def test_baseline_does_not_infer_rate_for_irregular_event_topic(tmp_path: Path):
    start = 1_700_000_000_000_000_000
    increments_ms = [1, 1, 1, 1, 50] * 7
    timestamps = [start]
    for increment in increments_ms:
        timestamps.append(timestamps[-1] + increment * 1_000_000)
    bag = make_sqlite_bag(
        tmp_path / "events",
        {"/diagnostics": ("diagnostic_msgs/msg/DiagnosticArray", timestamps)},
    )
    rule = build_baseline(bag)["topics"]["/diagnostics"]
    assert rule["required"] is True
    assert "rate_hz" not in rule
    assert "max_gap_ms" not in rule


@pytest.mark.parametrize(
    "config_data,match",
    [
        ({"bag": {"min_duration_s": -1}}, "bag.min_duration_s"),
        ({"bag": {"min_messages": -1}}, "bag.min_messages"),
        ({"topics": {"/imu": {"max_gap_ms": -1}}}, "max_gap_ms"),
        ({"topics": {"/imu": {"max_jitter_ms": -1}}}, "max_jitter_ms"),
        ({"topics": {"/imu": {"min_messages": -1}}}, "min_messages"),
        ({"sync": [{"topics": ["/a", "/b"], "max_offset_ms": -1}]}, "max_offset_ms"),
    ],
)
def test_negative_policy_limits_are_rejected(tmp_path: Path, config_data: dict, match: str):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"version": 1, **config_data}), encoding="utf-8")
    with pytest.raises(ConfigError, match=match):
        load_config(path)


def test_metadata_storage_identifier_must_match_files(tmp_path: Path):
    bag = make_sqlite_bag(tmp_path / "storage-mismatch", {"/imu": ("sensor_msgs/msg/Imu", [1, 2, 3])})
    metadata = yaml.safe_load((bag / "metadata.yaml").read_text(encoding="utf-8"))
    metadata["rosbag2_bagfile_information"]["storage_identifier"] = "mcap"
    (bag / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    with pytest.raises(BagReadError, match="does not match"):
        read_bag(bag)


def test_sync_check_fails_when_declared_topic_has_no_samples(tmp_path: Path):
    bag = make_sqlite_bag(
        tmp_path / "empty-sync",
        {
            "/camera": ("sensor_msgs/msg/Image", [100, 200, 300]),
            "/imu": ("sensor_msgs/msg/Imu", []),
        },
    )
    config = tmp_path / "sync.yaml"
    config.write_text(
        """version: 1
sync:
  - name: camera-imu
    topics: [/camera, /imu]
    reference: /camera
    max_offset_ms: 10
""",
        encoding="utf-8",
    )
    report = inspect_bag(bag, config)
    assert any(issue.code == "sync-no-samples" for issue in report.issues)
    assert report.status == "fail"
