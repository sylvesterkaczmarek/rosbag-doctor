from __future__ import annotations

import sqlite3

from conftest import make_sqlite_bag

from rosbag_doctor.compare import compare_bags


def test_comparison_retains_health_failures_from_each_recording(tmp_path):
    base = make_sqlite_bag(
        tmp_path / "base",
        {"/sensor": ("std_msgs/msg/Float64", [100, 200, 300])},
    )
    candidate = make_sqlite_bag(
        tmp_path / "candidate",
        {"/sensor": ("std_msgs/msg/Float64", [100, 200, 300])},
    )
    with sqlite3.connect(candidate / "bag_0.db3") as connection:
        # Preserve the same timestamp set but regress in recorded row order.
        connection.execute(
            "UPDATE messages SET timestamp = CASE id WHEN 2 THEN 300 WHEN 3 THEN 200 ELSE timestamp END"
        )

    comparison = compare_bags(base, candidate)
    assert comparison["base_health"] == {"status": "pass", "issues": []}
    assert comparison["candidate_health"]["status"] == "fail"
    regression = next(
        issue for issue in comparison["candidate_health"]["issues"]
        if issue["code"] == "timestamp-regression"
    )
    assert regression["topic"] == "/sensor"
    assert regression["severity"] == "error"
    assert regression["details"]["count"] == 1
    assert comparison["topics"][0]["rate_change_pct"] == 0.0

    reversed_comparison = compare_bags(candidate, base)
    assert reversed_comparison["base_health"] == comparison["candidate_health"]
    assert reversed_comparison["candidate_health"] == comparison["base_health"]


def test_comparison_retains_type_conflicts(tmp_path):
    bag = make_sqlite_bag(
        tmp_path / "conflict",
        {"/sensor": ("std_msgs/msg/Float64", [100, 200, 300])},
    )
    with sqlite3.connect(bag / "bag_0.db3") as connection:
        connection.execute(
            "INSERT INTO topics VALUES (2, '/sensor', 'std_msgs/msg/String', 'cdr', '')"
        )
        connection.execute("INSERT INTO messages(topic_id, timestamp, data) VALUES (2, 400, X'01')")

    comparison = compare_bags(bag, bag)
    for side in ["base_health", "candidate_health"]:
        assert comparison[side]["status"] == "fail"
        assert any(issue["code"] == "topic-type-conflict" for issue in comparison[side]["issues"])


def test_comparison_exposes_type_changes_and_preserves_topic_states(tmp_path):
    base = make_sqlite_bag(
        tmp_path / "base",
        {
            "/changed": ("std_msgs/msg/Float64", [100, 200, 300]),
            "/stable": ("std_msgs/msg/Float64", [100, 200, 300]),
            "/removed": ("std_msgs/msg/Float64", [100]),
            "/unknown": ("unknown", [100]),
        },
    )
    candidate = make_sqlite_bag(
        tmp_path / "candidate",
        {
            "/changed": ("std_msgs/msg/String", [100, 200, 300]),
            "/stable": ("std_msgs/msg/Float64", [100, 200, 300]),
            "/added": ("std_msgs/msg/Float64", [100]),
            "/unknown": ("std_msgs/msg/Float64", [100]),
        },
    )
    topics = {item["topic"]: item for item in compare_bags(base, candidate)["topics"]}

    assert topics["/changed"]["state"] == "present"
    assert topics["/changed"]["type_changed"] is True
    assert topics["/changed"]["base_message_type"] == "std_msgs/msg/Float64"
    assert topics["/changed"]["candidate_message_type"] == "std_msgs/msg/String"
    assert topics["/stable"]["type_changed"] is False
    assert topics["/unknown"]["type_changed"] is None
    assert topics["/added"]["state"] == "added"
    assert topics["/added"]["base_message_type"] is None
    assert topics["/removed"]["state"] == "removed"
    assert topics["/removed"]["candidate_message_type"] is None
