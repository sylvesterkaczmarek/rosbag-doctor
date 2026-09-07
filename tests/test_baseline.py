from __future__ import annotations

import pytest
from conftest import make_sqlite_bag

from rosbag_doctor.baseline import build_baseline, write_baseline
from rosbag_doctor.config import ConfigError, DoctorConfig, load_config
from rosbag_doctor.doctor import inspect_bag


def test_baseline_contains_observed_topics(healthy_bag, tmp_path):
    baseline = build_baseline(healthy_bag)
    assert baseline["version"] == 1
    assert baseline["topics"]["/imu"]["required"] is True
    assert abs(baseline["topics"]["/imu"]["rate_hz"] - 100) < 0.1


def test_generated_baseline_is_valid_yaml(healthy_bag, tmp_path):
    path = write_baseline(healthy_bag, tmp_path / "generated.yaml")
    config = load_config(path)
    assert isinstance(config, DoctorConfig)
    assert "/camera" in config.topics


@pytest.mark.parametrize("period_ns", [33_333_333, 4_000_000_000_000])
def test_baseline_preserves_rate_and_accepts_source_at_zero_tolerance(tmp_path, period_ns):
    bag = make_sqlite_bag(
        tmp_path / "periodic",
        {"/sensor": ("std_msgs/msg/Float64", [1_000_000_000 + i * period_ns for i in range(20)])},
    )
    output = write_baseline(bag, tmp_path / "policy.yaml", rate_tolerance=0)
    config = load_config(output)
    report = inspect_bag(bag, output)

    assert config.topics["/sensor"].rate_hz == report.topics[0].effective_rate_hz
    assert config.topics["/sensor"].rate_hz > 0
    assert report.status == "pass"


def test_baseline_does_not_round_tiny_coverage_above_source(tmp_path):
    bag = make_sqlite_bag(
        tmp_path / "short-coverage",
        {
            "/long": ("std_msgs/msg/Float64", [1, 1_000_000_001]),
            "/short": ("std_msgs/msg/Float64", [1, 260_000, 530_001]),
        },
    )
    output = write_baseline(bag, tmp_path / "policy.yaml")
    config = load_config(output)

    assert 0 < config.topics["/short"].min_coverage < 0.00053
    assert inspect_bag(bag, output).status == "pass"


@pytest.mark.parametrize(
    "option,value",
    [
        ("rate_tolerance", float("nan")),
        ("rate_tolerance", float("inf")),
        ("rate_tolerance", float("-inf")),
        ("rate_tolerance", -0.1),
        ("rate_tolerance", 1.1),
        ("rate_tolerance", True),
        ("rate_tolerance", "0.1"),
        ("rate_tolerance", None),
        ("rate_tolerance", 10**400),
        ("gap_multiplier", float("nan")),
        ("gap_multiplier", float("inf")),
        ("gap_multiplier", float("-inf")),
        ("gap_multiplier", 0.9),
        ("gap_multiplier", True),
        ("gap_multiplier", "1.5"),
        ("gap_multiplier", None),
        ("gap_multiplier", 10**400),
    ],
)
def test_invalid_options_are_rejected_before_bag_access(monkeypatch, option, value):
    def unexpected_read(_path):
        pytest.fail("Invalid baseline options must be rejected before reading a bag")

    monkeypatch.setattr("rosbag_doctor.baseline.read_bag", unexpected_read)
    with pytest.raises(ConfigError, match=option):
        build_baseline("nonexistent", **{option: value})


def test_overflowed_gap_limit_is_rejected_without_replacing_output(healthy_bag, tmp_path):
    output = tmp_path / "policy.yaml"
    output.write_text("previous valid policy", encoding="utf-8")

    with pytest.raises(ConfigError, match="non-finite gap limit"):
        write_baseline(healthy_bag, output, gap_multiplier=1e308)

    assert output.read_text(encoding="utf-8") == "previous valid policy"
