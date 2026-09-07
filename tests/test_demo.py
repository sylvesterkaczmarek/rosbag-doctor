from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rosbag_doctor import inspect_bag

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def test_demo_detects_dropout_and_preserves_existing_output(tmp_path):
    bag = tmp_path / 'demo'
    command = [sys.executable, str(EXAMPLES / 'make_demo_bag.py'), str(bag)]
    subprocess.run(command, check=True, capture_output=True)
    report = inspect_bag(bag, EXAMPLES / 'doctor.yaml')
    assert report.status == 'fail'
    assert report.total_messages == 773
    assert [(issue.code, issue.topic) for issue in report.issues] == [
        ('gap-too-large', '/camera/image_raw'),
    ]
    before = {path.name: path.read_bytes() for path in bag.iterdir()}
    repeated = subprocess.run(command, check=False, capture_output=True, text=True)
    assert repeated.returncode == 2
    assert 'Refusing to overwrite' in repeated.stderr
    assert {path.name: path.read_bytes() for path in bag.iterdir()} == before
