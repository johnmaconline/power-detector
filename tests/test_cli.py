import os
import subprocess
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def test_cli_oneshot_mock_dry_run_exits_zero():
    cmd = [
        sys.executable,
        os.path.join(ROOT, 'power_detector.py'),
        '--config',
        os.path.join(ROOT, 'config.example.yaml'),
        '--oneshot',
        '--mock-sentinel',
        '--mock-wan',
        '--dry-run-notify',
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0


def test_cli_test_notify_dry_run_exits_zero():
    cmd = [
        sys.executable,
        os.path.join(ROOT, 'power_detector.py'),
        '--config',
        os.path.join(ROOT, 'config.example.yaml'),
        '--test-notify',
        '--dry-run-notify',
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
