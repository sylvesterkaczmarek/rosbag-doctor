from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml

from rosbag_doctor.doctor import inspect_bag


def test_timestamp_regression_uses_recorded_order(tmp_path: Path):
    bag = tmp_path / "regression"
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
        INSERT INTO topics VALUES (1, '/clocked', 'std_msgs/msg/Int32', 'cdr', '');
        """
    )
    start = 1_700_000_000_000_000_000
    for timestamp in [start, start + 10_000_000, start + 5_000_000, start + 20_000_000]:
        connection.execute("INSERT INTO messages(topic_id, timestamp, data) VALUES (1, ?, ?)", (timestamp, b"x"))
    connection.commit()
    connection.close()
    metadata = {
        "rosbag2_bagfile_information": {
            "version": 9,
            "storage_identifier": "sqlite3",
            "relative_file_paths": [db.name],
        }
    }
    (bag / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")

    report = inspect_bag(bag)
    assert report.status == "fail"
    assert any(issue.code == "timestamp-regression" for issue in report.issues)
