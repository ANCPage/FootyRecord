"""Environment guards for data-dependent tests.

A missing dependency FAILS, it does not skip (Austin, 2026-09-14, audit finding
10). Reasoning: a silent skip let a permanently failing test hide for weeks, and
a transient DB lock made six tests vanish mid-suite even though they passed when
run alone. A skip that looks like a pass is worse than a red test.

Data-dependent tests carry the `needs_data` marker so they can be deselected
deliberately — `pytest -m "not needs_data"` — rather than disappearing quietly.
"""
import pytest

HINT = ('\n  needs the results DB and/or the CSV data dir. Set FOOTYRECORD_DATA_DIR '
        '(e.g. /mnt/projects/FootyRecord/CSV_DATA), or deselect on purpose with: '
        'pytest -m "not needs_data"')


def require(condition, why):
    """Fail — never skip — when a data dependency is missing."""
    if not condition:
        pytest.fail(why + HINT, pytrace=False)
