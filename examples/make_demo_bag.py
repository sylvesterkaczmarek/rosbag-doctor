from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import yaml


def add_topic(connection: sqlite3.Connection, topic_id: int, name: str, message_type: str) -> None:
    connection.execute(
        "INSERT INTO topics(id, name, type, serialization_format, offered_qos_profiles) VALUES (?, ?, ?, 'cdr', '')",
        (topic_id, name, message_type),
    )


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "demo-bag")
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "demo_0.db3"
    if db_path.exists():
        db_path.unlink()

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
    add_topic(connection, 1, "/imu", "sensor_msgs/msg/Imu")
    add_topic(connection, 2, "/camera/image_raw", "sensor_msgs/msg/Image")

    start = 1_800_000_000_000_000_000
    messages: list[tuple[int, int, bytes]] = []
    for i in range(600):
        messages.append((1, start + i * 10_000_000, b"imu"))
    for i in range(180):
        if 88 <= i <= 94:  # deliberate camera dropout
            continue
        timestamp = start + 3_000_000 + i * 33_333_333
        messages.append((2, timestamp, b"camera"))

    messages.sort(key=lambda row: row[1])
    connection.executemany("INSERT INTO messages(topic_id, timestamp, data) VALUES (?, ?, ?)", messages)
    connection.commit()
    connection.close()

    metadata = {
        "rosbag2_bagfile_information": {
            "version": 9,
            "storage_identifier": "sqlite3",
            "relative_file_paths": [db_path.name],
        }
    }
    (output / "metadata.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
