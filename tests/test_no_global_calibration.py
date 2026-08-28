"""Phase 1 guard: no module-level mutable calibration state (2026-08-26).

`Core.calibration.current` was a module-level global assigned during load and
read by five scripts. That hidden state is the bug class behind the
`config.config.window_size` family of errors: two places disagree about which
calibration is active and nothing complains.

These tests assert the global is gone and that no caller reads it.
"""
import glob
import os

import Core.calibration as cal

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CALLERS = [
    'compute_round.py',
    'predict_game.py',
    'evaluate.py',
    'refit_hyperparams.py',
]


def test_calibration_module_has_no_mutable_global():
    """`cal.current` must not exist — calibration travels with the ingestor."""
    assert not hasattr(cal, 'current'), (
        "Core.calibration.current reintroduced: module-level mutable state. "
        "Pass ing.calibration explicitly instead."
    )


def _code_lines(path: str):
    """Source lines with comments and docstring bodies stripped out.

    The guard must match real attribute access, not the Phase 1 comments that
    explain what was removed.
    """
    out = []
    in_doc = False
    delim = None
    for raw in open(path):
        line = raw
        stripped = line.strip()
        if in_doc:
            if delim in stripped:
                in_doc = False
            continue
        if stripped.startswith(('"""', "'''")):
            delim = stripped[:3]
            # single-line docstring?
            if stripped.count(delim) < 2:
                in_doc = True
            continue
        code = line.split('#', 1)[0]
        if code.strip():
            out.append(code)
    return out


def _reads_global(path: str) -> bool:
    return any(
        ('cal.current' in ln) or ('calibration.current' in ln)
        for ln in _code_lines(path)
    )


def test_no_caller_reads_cal_current():
    offenders = [
        name for name in CALLERS
        if os.path.exists(os.path.join(REPO, name))
        and _reads_global(os.path.join(REPO, name))
    ]
    assert offenders == [], f"still reading the calibration global: {offenders}"


def test_no_module_reads_cal_current_anywhere():
    """Repo-wide sweep — catches new scripts that reach for the old global."""
    offenders = []
    for pattern in ('*.py', 'Core/*.py'):
        for path in glob.glob(os.path.join(REPO, pattern)):
            if os.path.basename(path).startswith('test_'):
                continue
            if _reads_global(path):
                offenders.append(os.path.relpath(path, REPO))
    assert offenders == [], f"calibration global referenced in: {offenders}"


def test_ingestor_exposes_calibration_attribute():
    """The replacement contract: every ingestor carries its own calibration."""
    from Core.engine_data import DataIngestor
    assert hasattr(DataIngestor, '__init__')
    src = open(os.path.join(REPO, 'Core', 'engine_data.py')).read()
    assert 'self.calibration' in src, "ingestor must own its calibration"
