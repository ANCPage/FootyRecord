"""The backtest must produce identical numbers on every run.

Python randomises str hashing per process, so any metric that lets set/dict
iteration order reach a tie-break moves between runs. That is not acceptable for
a number we make decisions on, so the tool is tested under two hash seeds.
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def _run(seed):
    env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONPATH=REPO)
    out = subprocess.run([PY, '-m', 'Core.tools.props_backtest', '--selftest'],
                         cwd=REPO, env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_selftest_is_deterministic_across_hash_seeds():
    a = _run(0)
    b = _run(1)
    assert a == b
    assert 'model allocation' in a and 'head-to-head' in a


def test_selftest_reports_both_allocations():
    out = _run(0)
    assert 'history allocation' in out and 'equal shares' in out
