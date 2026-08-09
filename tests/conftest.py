from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml


def make_sqlite_bag(path: Path, topics: dict[str, tuple[str, list[int]]]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    db_path = path / "bag_0.db3"
    connection = sqlite3.connect(db_path)
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
        """
    )
    topic_ids: dict[str, int] = {}
    for index, (name, (message_type, _timestamps)) in enumerate(topics.items(), start=1):
        topic_ids[name] = index
        connection.execute(
            "INSERT INTO topics(id, name, type, serialization_format, offered_qos_profiles) VALUES (?, ?, ?, 'cdr', '')",
            (index, name, message_type),
        )
    rows: list[tuple[int, int, bytes]] = []
    for name, (_message_type, timestamps) in topics.items():
        for timestamp in timestamps:
            rows.append((topic_ids[name], int(timestamp), b"x"))
    rows.sort(key=lambda item: item[1])
    connection.executemany("INSERT INTO messages(topic_id, timestamp, data) VALUES (?, ?, ?)", rows)
    connection.commit()
    connection.close()
    metadata = {
        "rosbag2_bagfile_information": {
            "version": 9,
            "storage_identifier": "sqlite3",
            "relative_file_paths": [db_path.name],
        }
    }
    (path / "metadata.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def healthy_bag(tmp_path: Path) -> Path:
    start = 1_700_000_000_000_000_000
    imu = [start + i * 10_000_000 for i in range(500)]
    camera = [start + 3_000_000 + i * 33_333_333 for i in range(150)]
    return make_sqlite_bag(
        tmp_path / "healthy",
        {
            "/imu": ("sensor_msgs/msg/Imu", imu),
            "/camera": ("sensor_msgs/msg/Image", camera),
        },
    )
