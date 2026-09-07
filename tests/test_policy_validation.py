from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rosbag_doctor.config import ConfigError, load_config


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10**400])
@pytest.mark.parametrize(
    "section,field",
    [
        ("bag", "min_duration_s"),
        ("bag", "max_duration_s"),
        ("topics", "rate_hz"),
        ("topics", "rate_tolerance"),
        ("topics", "max_gap_ms"),
        ("topics", "max_jitter_ms"),
        ("topics", "min_coverage"),
        ("topics", "max_start_delay_ms"),
        ("topics", "max_end_early_ms"),
        ("sync", "max_p95_offset_ms"),
        ("sync", "max_offset_ms"),
    ],
)
def test_policy_limits_must_be_finite(tmp_path: Path, value, section, field):
    if section == "bag":
        policy = {"bag": {field: value}}
    elif section == "topics":
        policy = {"topics": {"/camera": {field: value}}}
    else:
        policy = {"sync": [{"topics": ["/camera", "/imu"], field: value}]}
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    with pytest.raises(ConfigError, match=rf"{field} must be finite"):
        load_config(path)


@pytest.mark.parametrize(
    "body,match",
    [
        ("false\n", "root must be a mapping"),
        ("[]\n", "root must be a mapping"),
        ("0\n", "root must be a mapping"),
        ("bag: []\n", "bag must be a mapping"),
        ("bag: false\n", "bag must be a mapping"),
        ("topics: []\n", "topics must be a mapping"),
        ("topics: false\n", "topics must be a mapping"),
        ("sync: {}\n", "sync must be a list"),
        ("sync: false\n", "sync must be a list"),
        ("ignore: {}\n", "ignore must be a list"),
        ("ignore: false\n", "ignore must be a list"),
        ("version: true\n", "Unsupported config version"),
        ("version: 1.0\n", "Unsupported config version"),
        ("version: '1'\n", "Unsupported config version"),
        ("version: 2\n", "Unsupported config version"),
        ("topics:\n  /camera:\n    rate_tolerance: null\n", "rate_tolerance must be a number"),
        ("1: 2\n", "mapping keys must be strings"),
        ("bag:\n  1: 2\n", "mapping keys must be strings"),
        ("topics:\n  /camera:\n    1: 2\n", "mapping keys must be strings"),
        ("bag:\n  max_duraton_s: 2\n", "Unknown bag fields: max_duraton_s"),
        ("sync:\n  - topics: [/a, /b]\n    name: false\n", "name must be a non-empty string"),
        ("sync:\n  - topics: [/a, /b]\n    name: ''\n", "name must be a non-empty string"),
    ],
)
def test_malformed_policy_is_not_silently_treated_as_defaults(tmp_path: Path, body, match):
    path = tmp_path / "policy.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError, match=match):
        load_config(path)


@pytest.mark.parametrize(
    "body,key",
    [
        ("bag:\n  min_messages: 20\n  min_messages: 0\n", "min_messages"),
        ("topics:\n  /camera: {required: true}\n  /camera: {}\n", "/camera"),
        ("topics: {/camera: {required: true}}\ntopics: {}\n", "topics"),
        ("sync:\n - topics: [/a, /b]\n   max_offset_ms: 1\n   max_offset_ms: 1000\n", "max_offset_ms"),
    ],
)
def test_duplicate_yaml_keys_cannot_overwrite_checks(tmp_path: Path, body, key):
    path = tmp_path / "policy.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError, match=f"Duplicate configuration key: {key}"):
        load_config(path)


def test_explicit_yaml_merge_overrides_remain_supported(tmp_path: Path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        "topics:\n  /a: &defaults\n    required: true\n    min_messages: 20\n"
        "  /b:\n    <<: *defaults\n    min_messages: 40\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.topics["/a"].min_messages == 20
    assert config.topics["/b"].min_messages == 40
    assert config.topics["/b"].required is True


def test_duplicate_sync_names_are_rejected(tmp_path: Path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        "sync:\n  - topics: [/a, /b]\n    name: sync-2\n  - topics: [/a, /c]\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Duplicate sync name: sync-2"):
        load_config(path)


def test_invalid_utf8_policy_has_a_configuration_error(tmp_path: Path):
    path = tmp_path / "policy.yaml"
    path.write_bytes(b"topics: \xff")
    with pytest.raises(ConfigError, match="Could not read config"):
        load_config(path)


def test_config_path_expands_the_user_directory(tmp_path: Path, monkeypatch):
    # expanduser uses the platform's user-directory expansion.
    monkeypatch.setattr("os.path.expanduser", lambda path: str(tmp_path))
    path = tmp_path / "policy.yaml"
    path.write_text("bag: {min_messages: 20}\n", encoding="utf-8")
    assert load_config("~/policy.yaml").bag.min_messages == 20


@pytest.mark.parametrize("body", ["", "{}\n", "bag: null\ntopics: null\nsync: null\nignore: null\n"])
def test_empty_optional_policy_is_valid(tmp_path: Path, body):
    path = tmp_path / "policy.yaml"
    path.write_text(body, encoding="utf-8")
    config = load_config(path)
    assert config.topics == {}
    assert config.sync == []
    assert config.ignore == []
