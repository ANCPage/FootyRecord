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


def test_row_cache_fingerprint_tracks_the_code_and_the_constants():
    """A cached row file must not outlive the code that made it (audit finding 11)."""
    from Core.tools import props_backtest as pb
    base = pb.code_fingerprint()
    assert base == pb.code_fingerprint()                       # stable
    original = pb.PPG
    try:
        pb.PPG = original + 1.0
        assert pb.code_fingerprint() != base                   # constants count
    finally:
        pb.PPG = original
    assert pb.code_fingerprint() == base


def test_stale_row_cache_warns_loudly(tmp_path):
    import json
    import os
    from Core.tools import props_backtest as pb
    rows = tmp_path / 'rows.json'
    rows.write_text(json.dumps([{'season': 2025, 'round': 1, 'team': 'T',
                                 'players': {}, 'vol_actual': 60, 'vol_prior': 70,
                                 'vol_model': 84, 'm_id': 'M'}]))
    (tmp_path / 'rows.json.meta.json').write_text(json.dumps({'fingerprint': 'deadbeef'}))
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, '-m', 'Core.tools.props_backtest', '--from-rows',
         '--out', str(rows), '--gate'],
        cwd=pb.os.path.dirname(pb.os.path.dirname(pb.os.path.dirname(pb.__file__))),
        capture_output=True, text=True, timeout=300)
    assert 'WARNING' in out.stdout and 'regenerate' in out.stdout
