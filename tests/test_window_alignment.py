"""Window-alignment gate (2026-09-07, Austin: "align it properly").

The prediction card's chain selection must use the MODEL's own memory: the
last `window` (30) of the team's matches strictly before the slot,
cross-season, flat — the same filter + slice queries.average_matrix locks.
Needs engine state (CSV data); skips cleanly where absent (mirror).
"""
import glob
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Core.config import DATA_DIR  # noqa: E402
from Core.engine_data import DataIngestor  # noqa: E402
import Core.chains as chains  # noqa: E402
import Core.state_store as ss  # noqa: E402


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


SLOTS = [5, 12, 19, 24]


def _engine_window(ing, team, season, r):
    _, used = ing.get_team_average_matrix(
        team, up_to_season=season, up_to_round=r, return_history_info=True)
    return {(int(u.split('_')[1]), int(u.split('_')[0][1:]))
            for u in used}


@pytest.mark.parametrize('r', SLOTS)
def test_sql_window_equals_engine_window(ing, conn, r):
    eng = _engine_window(ing, 'CD_T100', 2026, r)
    mine = {(h[1], h[2]) for h in
            ss.team_match_history(conn, 'CD_T100', 2026, r)[:30]}
    assert mine == eng and len(mine) == len(eng), (
        'SQL window != engine memory at R%s: only-engine %s only-sql %s'
        % (r, sorted(eng - mine)[:4], sorted(mine - eng)[:4]))


def test_window_counter_uses_only_window_games(conn):
    # flat counts over the model window: never more games than the window
    hist = ss.team_match_history(conn, 'CD_T100', 2026, 24)[:30]
    c = chains.window_counter(conn, 2026, 23, 'CD_T100')
    assert c  # the model's window yields scoring paths for a seasoned team
    # spot-check: total weighted mass equals the chain count in-window
    mids = {m for (m, _s, _r) in hist}
    rows = ss.chains_for_matches(conn, mids, 'CD_T100')
    n_chains = len({(m, ci) for (m, ci, _g) in rows})
    assert abs(sum(c.values()) - n_chains) < 1e-6
