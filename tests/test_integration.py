"""Integration tests: DataIngestor end-to-end on synthetic CSVs (audit #21).

No real data required — the fixture is two teams, two matches, scoring
chains only, in the same team-relative frame the engine expects.
"""
import csv
import os

from Core.engine_core import MatchupEngine
from Core.engine_data import DataIngestor

COLUMNS = ['matchId', 'round', 'season', 'homeTeamId', 'awayTeamId',
           'venueLength', 'venueWidth', 'chain_period', 'stat_periodSeconds',
           'x', 'y', 'stat_playerId', 'stat_description', 'stat_teamId',
           'chain_index', 'chain_teamId', 'chain_finalState_class', 'stat_class']


def write_fixture(csv_dir):
    os.makedirs(csv_dir, exist_ok=True)
    path = os.path.join(csv_dir, 'flattened_stats_2026.csv')
    rows = []
    # m1: H (home) vs A — each team kicks one goal from their forward pocket
    for cid, team in [(0, 'H'), (1, 'A')]:
        rows.append(['CD_M2026001', 1, 2026, 'H', 'A', 170, 130, 1, 10,
                     70, 0, f'P{cid}', 'Goal', team, cid, team, 'SCORE', 'SCORE'])
    # m2: A (home) vs H — same pattern
    for cid, team in [(0, 'A'), (1, 'H')]:
        rows.append(['CD_M2026002', 2, 2026, 'A', 'H', 170, 130, 1, 10,
                     70, 0, f'P{cid}', 'Goal', team, cid, team, 'SCORE', 'SCORE'])
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    return path


def test_ingestor_end_to_end(tmp_path):
    write_fixture(str(tmp_path))
    ing = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing.load_all_data()
    ing.profile_all_teams()

    # match info + scores (1 goal each = draw, exercises the DRAW path)
    assert len(ing.match_info) == 2
    assert all(w == 'DRAW' for w in ing.actual_winners.values())
    m1 = ing.match_info['CD_M2026001']
    assert m1.home == 'H' and m1.away == 'A'
    assert m1.home_score == 6 and m1.away_score == 6

    # normalized matrices: each team's avg matrix has unit-ish total weight
    for team in ('H', 'A'):
        mat = ing.get_team_average_matrix(team)
        assert mat, f'{team} has no profile'
        total = sum(abs(v) for v in mat.values())
        assert 0.5 <= total <= 1.5, f'{team} abs-total {total}'

    # Elo history exists and is queryable
    assert ing.team_elo_history['H']
    assert ing.get_team_elo('H', 2026, 1) == 1500.0  # before round 1
    elo_after = ing.get_team_elo('H', 2026, 3)
    assert 1500.0 - 100 < elo_after < 1500.0 + 100

    # delta between the two (identical) profiles is near-zero
    d = MatchupEngine.calculate_delta(ing.get_team_average_matrix('H'),
                                      ing.get_team_average_matrix('A'))
    assert abs(sum(d.values())) < 1e-6


def test_cache_round_trip(tmp_path):
    write_fixture(str(tmp_path))
    ing = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing.load_all_data()
    ing.profile_all_teams()
    m_before = ing.get_team_average_matrix('H')

    ing2 = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing2.load_all_data()  # should hit the versioned cache
    assert getattr(ing2, '_skip_profiling', False), 'cache was not used'
    assert ing2.get_team_average_matrix('H') == m_before


def test_light_load_skips_chains(tmp_path):
    """Perf 2026-08-12: render/compute loads pass light=True — the chains
    table (only needed for profiling) is skipped, everything else identical."""
    write_fixture(str(tmp_path))
    ing = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing.load_all_data()
    ing.profile_all_teams()

    ing_light = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing_light.load_all_data(light=True)
    assert getattr(ing_light, '_skip_profiling', False), 'cache was not used'
    assert ing_light.match_chains == {} or len(ing_light.match_chains) == 0
    assert len(ing_light.match_info) == len(ing.match_info)
    assert ing_light.get_team_average_matrix('H') == ing.get_team_average_matrix('H')
    assert len(ing_light.team_elo_history) == len(ing.team_elo_history)


def test_elo_index_rebuilt_after_load(tmp_path):
    """Regression (2026-08-25): load_all_data replaces elo_engine with a fresh
    instance whose per-round index is empty — get_team_elo returned 1500 for
    every team after any load (ladder tiers all MID-TABLE, journeys Rating
    1500). The load path must rebuild the index from the stored history."""
    write_fixture(str(tmp_path))
    ing = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing.load_all_data()
    ing.profile_all_teams()
    live = {t: [ing.get_team_elo(t, 2026, r) for r in (1, 2, 3)] for t in ('H', 'A')}

    ing2 = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing2.load_all_data()
    rebuilt = {t: [ing2.get_team_elo(t, 2026, r) for r in (1, 2, 3)] for t in ('H', 'A')}
    assert rebuilt == live, f'index drifted after load: {live} vs {rebuilt}'
    assert live['H'][0] == 1500.0  # baseline before round 1
    # the index itself is populated (the fixture is draws, so ratings stay
    # 1500 — the regression is about the index existing after load, not drift)
    assert ing2.elo_engine.team_elo_by_round and ing2.elo_engine.season_start_elos
    # every team's history ends with its own POST_ tail (v8)
    for team in ('H', 'A'):
        assert ing2.team_elo_history[team][-1][0].startswith('POST_')


def test_cache_invalidated_on_version_change(tmp_path, monkeypatch):
    write_fixture(str(tmp_path))
    ing = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing.load_all_data()
    ing.profile_all_teams()
    # sanity: a second ingestor DOES hit the cache before the bump
    ing_warm = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing_warm.load_all_data()
    assert getattr(ing_warm, '_skip_profiling', False), 'cache was not used'

    # bump CACHE_VERSION -> the old pickle must be rejected
    monkeypatch.setattr('Core.engine_data.CACHE_VERSION', 999)
    ing2 = DataIngestor(str(tmp_path), db_path=str(tmp_path / 'test.db'))
    ing2.load_all_data()
    assert not getattr(ing2, '_skip_profiling', False), 'stale cache accepted!'
