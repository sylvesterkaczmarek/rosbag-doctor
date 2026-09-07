from __future__ import annotations

import json
import os

import pytest
from conftest import make_sqlite_bag
from rich.console import Console

from rosbag_doctor.cli import main
from rosbag_doctor.doctor import inspect_bag
from rosbag_doctor.models import Issue
from rosbag_doctor.output import print_report, write_json


@pytest.mark.parametrize('command', ['inspect', 'baseline', 'compare'])
@pytest.mark.parametrize('target', ['bag_0.db3', 'metadata.yaml', 'bag_0.db3-wal'])
def test_commands_preserve_recording_inputs(healthy_bag, command, target, capsys):
    output = healthy_bag / target
    if target.endswith('-wal'):
        # This protected sidecar does not exist yet; the writer must not create it.
        before = None
    else:
        before = output.read_bytes()
    if command == 'baseline':
        args = ['baseline', str(healthy_bag), '-o', str(output)]
    elif command == 'compare':
        args = ['compare', str(healthy_bag), str(healthy_bag), '--json', str(output)]
    else:
        args = [str(healthy_bag), '--json', str(output)]
    assert main(args) == 2
    assert 'overwrite an input file' in capsys.readouterr().err
    assert (output.read_bytes() if output.exists() else None) == before


@pytest.mark.parametrize('alias_kind', ['symlink', 'hardlink'])
def test_output_cannot_alias_input(healthy_bag, tmp_path, alias_kind):
    db = healthy_bag / 'bag_0.db3'
    before = db.read_bytes()
    alias = tmp_path / 'report.json'
    try:
        if alias_kind == 'symlink':
            alias.symlink_to(db)
        else:
            os.link(db, alias)
    except OSError as exc:
        pytest.skip(f'Filesystem does not permit {alias_kind}: {exc}')
    assert main([str(db), '--json', str(alias)]) == 2
    assert db.read_bytes() == before


def test_output_cannot_replace_policy(healthy_bag, tmp_path):
    policy = tmp_path / 'doctor.yaml'
    policy.write_text('version: 1\n', encoding='utf-8')
    before = policy.read_bytes()
    assert main([str(healthy_bag), '--config', str(policy), '--json', str(policy)]) == 2
    assert policy.read_bytes() == before


def test_report_inside_bag_is_allowed(healthy_bag):
    report = healthy_bag / 'report.json'
    assert main([str(healthy_bag), '--json', str(report)]) == 0
    assert json.loads(report.read_text())['bag']['total_messages'] == 650


def test_failed_report_replacement_preserves_previous_report(tmp_path, monkeypatch):
    output = tmp_path / 'report.json'
    output.write_text('previous report', encoding='utf-8')

    def fail_replace(*args):
        raise OSError('disk failure')

    monkeypatch.setattr('rosbag_doctor.output.os.replace', fail_replace)
    with pytest.raises(OSError, match='disk failure'):
        write_json({'status': 'pass'}, output)
    assert output.read_text() == 'previous report'
    assert list(tmp_path.iterdir()) == [output]


def test_nonfinite_report_does_not_replace_previous_report(tmp_path):
    output = tmp_path / 'report.json'
    output.write_text('previous report', encoding='utf-8')
    with pytest.raises(ValueError):
        write_json({'measurement': float('nan')}, output)
    assert output.read_text() == 'previous report'


def test_user_text_is_printed_literally(tmp_path):
    bag = make_sqlite_bag(tmp_path / 'bag', {'/imu[red]': ('sensor_msgs/msg/Imu', [1, 2, 3])})
    report = inspect_bag(bag)
    report.issues.append(Issue('warning', 'probe', 'Literal [/closing] [bold] text', topic='/imu[red]'))
    console = Console(record=True, width=160)
    print_report(report, console)
    text = console.export_text()
    assert '/imu[red]' in text
    assert 'Literal [/closing] [bold] text' in text


def test_main_help_lists_inspection_options(capsys):
    assert main(['--help']) == 0
    output = capsys.readouterr().out
    for option in ['--config', '--strict', '--format', '--json']:
        assert option in output


def test_looping_output_symlink_returns_input_error(healthy_bag, tmp_path):
    output = tmp_path / 'loop.json'
    try:
        output.symlink_to(output)
    except OSError as exc:
        pytest.skip(f'Filesystem does not permit symlinks: {exc}')
    assert main([str(healthy_bag), '--json', str(output)]) == 2
