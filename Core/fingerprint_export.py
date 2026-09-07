"""Engine-side fingerprint export (2026-09-07, Austin: 100% model alignment).

get_team_average_matrix is THE function compute_matchup calls per team. For a
team + season, this exports that exact matrix as-of each round slot — the
model's own view, decayed per game over its window, attack-minus-concede,
E2-normalised. No reimplementation: liquid/cards consume the sidecar and never
re-derive engine maths.

Gate (tests/test_fingerprint_export.py): for played games, calculate_delta of
the exported matrices must equal the STORED prediction delta (home frame and
mirrored) — byte-exact, the same equality probe2 proved for compute_matchup.
"""
import json
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Core.config import DATA_DIR, RESULTS_DB  # noqa: E402
from Core.engine_data import DataIngestor      # noqa: E402
from Core.engine_core import MatchupEngine     # noqa: E402
import Core.state_store as state_store         # noqa: E402


def edge_key(e):
    if hasattr(e, 'source'):
        return '%s->%s' % (e.source, e.target)
    return '%s->%s' % (e[0], e[1])


def export_team_season(ing, team_id, season, rounds=24, window=None):
    """[{round, n_games, matrix: {'A2->B2': w, ...}}] — the model's matrix
    as-of each round slot (the exact profile used to predict that round)."""
    frames = []
    for r in range(1, rounds + 1):
        m, info = ing.get_team_average_matrix(
            team_id, window=window, up_to_season=season, up_to_round=r,
            return_history_info=True)
        matrix = None
        n_games = None
        if m:
            matrix = {edge_key(e): round(float(w), 6)
                      for e, w in sorted(m.items(),
                                         key=lambda kv: edge_key(kv[0]))}
            if isinstance(info, dict):
                n_games = info.get('n_games') or info.get('games')
        frames.append({'round': r, 'n_games': n_games,
                       'matrix': matrix or {}})
    return frames


def stored_delta(conn, season, round_num, home, away):
    """The shipped prediction delta (home frame) for a played game."""
    row = state_store.prediction_row(conn, season, round_num, home, away)
    if not row:
        return None
    delta_json = row[7]
    return json.loads(delta_json) if delta_json else {}


def gate_game(ing, conn, season, round_num, team_a, team_b):
    """Exported matrices must reproduce the STORED delta exactly.

    The stored row was shipped in the FIXTURE-HOME frame — so call
    calculate_delta with the actual stored home/away, and also verify the
    mirrored away-first identity probe2 proved (delta(away,home) ==
    mirror(stored)). Compare at 6dp on both sides (the export rounds).
    """
    row = state_store.prediction_row(conn, season, round_num, team_a, team_b)
    if not row or not row[7]:
        return ('NO-STORED', None, None)
    stored = json.loads(row[7])
    # the row stores its real home (row[6] = winner, row[1]..? — fetch via
    # match_row for the fixture home, then locate the prediction row)
    mrow = state_store.match_row(conn, season, round_num, team_a, team_b)
    if not mrow:
        return ('NO-MATCH', None, None)
    home = mrow[1]                       # match_row -> (m_id, home, ...)
    away = team_b if team_a == home else team_a
    m_h, _ = ing.get_team_average_matrix(
        home, up_to_season=season, up_to_round=round_num,
        return_history_info=True)
    m_a, _ = ing.get_team_average_matrix(
        away, up_to_season=season, up_to_round=round_num,
        return_history_info=True)
    if not m_h or not m_a:
        return ('NO-PROFILE', None, None)
    delta_h = {edge_key(e): round(float(v), 6)
               for e, v in MatchupEngine.calculate_delta(m_h, m_a).items()}
    # mirrored identity: away-first call must equal mirror(stored)
    d_away = {edge_key(e): round(float(v), 6)
              for e, v in MatchupEngine.calculate_delta(m_a, m_h).items()}
    stored_r = {k: round(float(v), 6) for k, v in stored.items()}
    from Core.cards import mirror_delta, _edge_tuple
    mirror = {edge_key((u, v)): round(x, 6)
              for (u, v), x in mirror_delta(
                  {_edge_tuple(k): v for k, v in stored.items()}).items()}
    same = delta_h == stored_r
    same_m = d_away == mirror
    if same and same_m:
        return ('MATCH', len(stored), None)
    diffs = [k for k in sorted(set(delta_h) | set(stored_r))
             if delta_h.get(k) != stored_r.get(k)][:4]
    diffs_m = [k for k in sorted(set(d_away) | set(mirror))
               if d_away.get(k) != mirror.get(k)][:4]
    return ('HOME:%s MIRROR:%s' % ('OK' if same else 'DIFF',
                                   'OK' if same_m else 'DIFF'),
            len(stored), {'home': diffs, 'mirror': diffs_m})


if __name__ == '__main__':
    import Core.chains as chains
    team = sys.argv[1] if len(sys.argv) > 1 else 'CD_T100'
    season = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    out = sys.argv[3] if len(sys.argv) > 3 else '/tmp/fp_export.json'
    conn = chains.connect()
    ing = DataIngestor(DATA_DIR)
    ing.load_all_data(light=True)
    frames = export_team_season(ing, team, season)
    json.dump({'team': team, 'season': season, 'frames': frames},
              open(out, 'w'))
    print('exported %d frames -> %s' % (len(frames), out))
    for r in (2, 6, 12, 20, 24):
        f = frames[r - 1]
        print('R%-2d n_games=%-3s edges=%d' % (r, f['n_games'], len(f['matrix'])))
    for (h, a, rnd) in [('CD_T100', 'CD_T90', 19), ('CD_T100', 'CD_T160', 24),
                        ('CD_T90', 'CD_T100', 19), ('CD_T160', 'CD_T100', 24),
                        ('CD_T70', 'CD_T10', 3), ('CD_T10', 'CD_T70', 3)]:
        st, n, diffs = gate_game(ing, conn, season, rnd, h, a)
        print('gate R%-2d %s v %s: %s (%s edges)%s' % (
            rnd, h, a, st, n, '  ' + repr(diffs) if diffs else ''))
