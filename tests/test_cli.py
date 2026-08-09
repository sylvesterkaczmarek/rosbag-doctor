from __future__ import annotations

import json

from rosbag_doctor.cli import main


def test_cli_writes_json_report(healthy_bag, tmp_path):
    output = tmp_path / "report.json"
    code = main([str(healthy_bag), "--json", str(output), "--format", "json"])
    assert code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["bag"]["total_messages"] == 650
    assert data["status"] == "pass"


def test_compare_command(healthy_bag, capsys):
    code = main(["compare", str(healthy_bag), str(healthy_bag), "--format", "json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert all(row["state"] == "present" for row in data["topics"])
