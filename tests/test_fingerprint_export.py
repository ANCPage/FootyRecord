"""Gate test for Core/fingerprint_export (2026-09-07, Austin: 100% alignment).

The exporter's per-round matrices must reproduce the STORED prediction deltas
exactly (home frame AND the mirrored away-first identity). Needs engine state
= the CSV data dir; skips cleanly where it's absent (mirror has no CSV_DATA).
"""
import glob
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Core.config import DATA_DIR  # noqa: E402
from Core.engine_data import DataIngestor  # noqa: E402
from Core import fingerprint_export as fe  # noqa: E402
import Core.chains as chains  # noqa: E402


def _have_data():
    return bool(glob.glob(os.path.join(DATA_DIR, 'flattened_stats_202*.csv')))


pytestmark = pytest.mark.skipif(
    not _have_data(), reason='engine CSVs not present (mirror has no data)')


@pytest.fixture(scope='module')
def ing():
    i = DataIngestor(DATA_DIR)
    i.load_all_data(light=True)
    return i


@pytest.fixture(scope='module')
def conn():
    return chains.connect()


GAMES = [  # (season, round, team_a, team_b) — both orientations gate here
    (2026, 3, 'CD_T70', 'CD_T10'),
    (2026, 19, 'CD_T100', 'CD_T90'),
    (2026, 24, 'CD_T100', 'CD_T160'),
]


def test_export_frames_are_complete(ing):
    frames = fe.export_team_season(ing, 'CD_T100', 2026)
    assert len(frames) == 24
    assert all(isinstance(f['round'], int) for f in frames)
    assert all(isinstance(f['matrix'], dict) for f in frames)
    assert frames[23]['matrix']  # late-season matrix is non-empty


@pytest.mark.parametrize('season,rnd,a,b', GAMES)
def test_gate_stored_delta(ing, conn, season, rnd, a, b):
    st, n, diffs = fe.gate_game(ing, conn, season, rnd, a, b)
    assert st == 'MATCH', 'gate %s R%s %s v %s: %s %r' % (season, rnd, a, b,
                                                          st, diffs)
    assert n and n > 0
