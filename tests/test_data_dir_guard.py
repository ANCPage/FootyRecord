"""An empty engine must fail loudly, not load and die later.

Before this guard, a run without FOOTYRECORD_DATA_DIR loaded 0 matches and then
died with "no profile for CD_T80 v CD_T20" — a message that names neither the
cause nor the fix (audit 2026-09-14, finding 3).
"""
import os

import pytest

from Core.engine_data import DataIngestor


def test_empty_data_dir_raises_with_the_path_and_the_fix(tmp_path):
    ing = DataIngestor(str(tmp_path))
    with pytest.raises(RuntimeError) as exc:
        ing.load_all_data()
    msg = str(exc.value)
    assert 'FOOTYRECORD_DATA_DIR' in msg          # tells you how to fix it
    assert str(tmp_path) in msg                   # tells you which dir was empty


def test_present_but_empty_csv_also_raises(tmp_path):
    """A placeholder file is the same trap as no file: files exist, data does not."""
    open(os.path.join(str(tmp_path), 'flattened_stats_2026.csv'), 'w').close()
    ing = DataIngestor(str(tmp_path))
    with pytest.raises(RuntimeError) as exc:
        ing.load_all_data()
    assert 'ZERO matches' in str(exc.value)
