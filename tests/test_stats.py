from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

from rosbag_doctor.checks import run_checks
from rosbag_doctor.config import DoctorConfig, SyncRule
from rosbag_doctor.models import BagData
from rosbag_doctor.stats import bag_bounds, nearest_offsets_ms, topic_stats

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


def _bag(topics: dict[str, list[int]]) -> BagData:
    bag = BagData(Path("synthetic"), "sqlite3", [])
    for name, timestamps in topics.items():
        series = bag.get_or_create_topic(name)
        for timestamp in timestamps:
            series.add(timestamp, "synthetic")
    return bag


@pytest.mark.parametrize(
    ("timestamps", "regressions", "duplicates", "max_gap_ns"),
    [
        ([INT64_MIN, INT64_MAX], 0, 0, 2**64 - 1),
        ([INT64_MAX, INT64_MIN], 1, 0, None),
        ([INT64_MIN, 0], 0, 0, 2**63),
        ([0, INT64_MIN], 1, 0, None),
        ([INT64_MIN, INT64_MIN, INT64_MAX], 0, 1, 2**64 - 1),
    ],
)
def test_signed_boundary_differences_remain_correct(
    timestamps: list[int], regressions: int, duplicates: int, max_gap_ns: int | None
):
    stat = topic_stats(_bag({"/clock": timestamps}))[0]
    assert stat.monotonic_violations == regressions
    assert stat.duplicate_timestamps == duplicates
    assert stat.first_timestamp_ns == timestamps[0]
    assert stat.last_timestamp_ns == timestamps[-1]
    assert stat.duration_s == pytest.approx((max(timestamps) - min(timestamps)) / 1e9)
    if max_gap_ns is None:
        assert stat.max_gap_ms is None
        assert stat.median_period_ms is None
    else:
        assert stat.max_gap_ms == pytest.approx(max_gap_ns / 1e6)
        assert stat.median_period_ms == pytest.approx(max_gap_ns / 1e6)


def test_period_and_jitter_keep_nanosecond_differences_at_large_epoch():
    start = 1_700_000_000_000_000_000
    stat = topic_stats(_bag({"/clock": [start, start + 1, start + 3, start + 6]}))[0]
    assert stat.median_period_ms == pytest.approx(2e-6)
    assert stat.p95_period_ms == pytest.approx(2.9e-6)
    assert stat.max_gap_ms == pytest.approx(3e-6)
    assert stat.p95_jitter_ms == pytest.approx(1e-6)
    assert stat.effective_rate_hz == pytest.approx(500_000_000)
    assert stat.median_rate_hz == pytest.approx(500_000_000)


def test_coverage_uses_time_extrema_but_regressions_use_recorded_order():
    bag = _bag({"/full": [-100, 100], "/middle": [50, -50, 0]})
    assert bag_bounds(bag) == (-100, 100)
    middle = next(stat for stat in topic_stats(bag) if stat.name == "/middle")
    assert middle.monotonic_violations == 1
    assert middle.first_timestamp_ns == 50
    assert middle.last_timestamp_ns == 0
    assert middle.coverage == 0.5
    assert middle.start_delay_ms == 50e-6
    assert middle.end_early_ms == 50e-6


@pytest.mark.parametrize(
    ("reference", "target"),
    [
        ([INT64_MIN], [INT64_MAX]),
        ([INT64_MIN], [0]),
        ([INT64_MAX], [INT64_MIN]),
        ([0], [INT64_MIN]),
        ([INT64_MIN, -1, 0, INT64_MAX], [INT64_MIN + 1, 1, INT64_MAX - 1]),
        ([1_700_000_000_000_000_003], [1_700_000_000_000_000_000]),
        ([13, -11, 10, 13], [12, -10, -10]),
    ],
)
def test_nearest_offsets_match_exact_integer_distances(reference: list[int], target: list[int]):
    ref = np.array(reference, dtype=np.int64)
    tgt = np.array(target, dtype=np.int64)
    expected = [min(abs(value - other) for other in target) / 1e6 for value in reference]
    result = nearest_offsets_ms(ref, tgt)
    np.testing.assert_allclose(result, expected, rtol=1e-15, atol=0)
    assert np.all(result >= 0)
    assert ref.tolist() == reference
    assert tgt.tolist() == target


def test_nearest_offsets_match_brute_force_across_signed_range():
    random_source = random.Random(417)
    reference = [random_source.randint(INT64_MIN, INT64_MAX) for _ in range(200)]
    target = [random_source.randint(INT64_MIN, INT64_MAX) for _ in range(53)]
    expected = [min(abs(value - other) for other in target) / 1e6 for value in reference]
    result = nearest_offsets_ms(np.array(reference, dtype=np.int64), np.array(target, dtype=np.int64))
    np.testing.assert_allclose(result, expected, rtol=1e-15, atol=0)


@pytest.mark.parametrize(("reference", "target"), [([], []), ([1], []), ([], [1])])
def test_nearest_offsets_have_no_samples_for_empty_streams(reference: list[int], target: list[int]):
    result = nearest_offsets_ms(np.array(reference, dtype=np.int64), np.array(target, dtype=np.int64))
    assert result.size == 0
    assert result.dtype == np.float64


def test_adding_healthy_sync_topic_does_not_hide_an_unhealthy_target():
    reference = [1_700_000_000_000_000_000 + i * 1_000_000_000 for i in range(100)]
    # Eight per cent of one target's samples are 100 ms late. Pooling these
    # with one healthy target reduces failures to four per cent and reports
    # a zero p95, even though the original pair fails the same 10 ms limit.
    late = [timestamp + (100_000_000 if i < 8 else 0) for i, timestamp in enumerate(reference)]
    bag = _bag({"/reference": reference, "/late": late, "/healthy": reference})
    results = []
    for names in (["/reference", "/late"], ["/reference", "/late", "/healthy"]):
        config = DoctorConfig(sync=[SyncRule("sensors", names, "/reference", max_p95_offset_ms=10)])
        issues, sync = run_checks(bag, topic_stats(bag), config)
        assert any(issue.code == "sync-p95-too-high" for issue in issues)
        assert sync[0].p95_offset_ms == pytest.approx(100)
        assert sync[0].max_offset_ms == pytest.approx(100)
        assert sync[0].samples == len(reference) * (len(names) - 1)
        results.append(sync[0].p95_offset_ms)
    assert results[0] == results[1]


def test_single_target_sync_keeps_nearest_pair_percentile_definition():
    reference = [1_700_000_000_000_000_000 + i * 1_000_000_000 for i in range(20)]
    target = [timestamp + i * 1_000_000 for i, timestamp in enumerate(reference)]
    bag = _bag({"/reference": reference, "/target": target})
    config = DoctorConfig(sync=[SyncRule("pair", ["/reference", "/target"], "/reference")])
    _, sync = run_checks(bag, topic_stats(bag), config)
    assert sync[0].p95_offset_ms == pytest.approx(18.05)
    assert sync[0].max_offset_ms == 19
    assert sync[0].samples == 20
