"""One-store migration (Phase 1): pickle cache -> extended results DB.

Imports every table of the engine's working state into the single SQLite
store, then runs a parity check comparing the imported rows against the
source ingestor's in-memory structures.

Usage: python migrate_one_store.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))

import Core.results_db as results_db
from Core.engine_data import DataIngestor


def edge_str(k) -> str:
    """TransitionEdge or plain (start, end) tuple -> 'start->end'."""
    if hasattr(k, 'source'):
        return f'{k.source}->{k.target}'
    return f'{k[0]}->{k[1]}'


def edge_dict_to_json(d) -> str:
    return json.dumps({edge_str(k): float(v) for k, v in d.items()}) if d else None


def edge_dict_from_json(s) -> dict:
    if not s:
        return {}
    from engine_core import TransitionEdge
    return {TransitionEdge(*k.split('->')): v for k, v in json.loads(s).items()}


def main():
    ing = DataIngestor('CSV_DATA')
    ing.load_all_data()

    conn = results_db.connect()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS matches (
            m_id TEXT PRIMARY KEY, season INTEGER, round INTEGER,
            home TEXT, away TEXT, home_score INTEGER, away_score INTEGER);
        CREATE TABLE IF NOT EXISTS chains (
            m_id TEXT, chain_idx INTEGER, seq INTEGER,
            team TEXT, outcome TEXT, grid TEXT, player TEXT,
            PRIMARY KEY (m_id, chain_idx, seq));
        CREATE TABLE IF NOT EXISTS match_positions (
            m_id TEXT, team TEXT, pos TEXT,
            PRIMARY KEY (m_id, team));
        CREATE TABLE IF NOT EXISTS match_performance (
            m_id TEXT PRIMARY KEY, expected REAL, expected_delta TEXT, actual REAL);
        CREATE TABLE IF NOT EXISTS actual_matrices (
            m_id TEXT, team TEXT, mat TEXT,
            PRIMARY KEY (m_id, team));
        CREATE TABLE IF NOT EXISTS elo_history (
            team TEXT, m_id TEXT, elo REAL,
            PRIMARY KEY (team, m_id));
        CREATE TABLE IF NOT EXISTS player_history (
            team TEXT, m_id TEXT, player TEXT, edges TEXT,
            PRIMARY KEY (team, m_id, player));
        CREATE TABLE IF NOT EXISTS calibration (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            decay REAL, margin_b1 REAL, margin_b2 REAL, total_mean REAL,
            divisor REAL, window TEXT, n_matches INTEGER, tier_cutoffs TEXT,
            fitted_at TEXT);
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT);
    """)

    # matches
    rows = [(m, i.season, i.round, i.home, i.away, i.home_score, i.away_score)
            for m, i in ing.match_info.items()]
    c.executemany("INSERT OR REPLACE INTO matches VALUES (?,?,?,?,?,?,?)", rows)
    print(f'matches: {len(rows)}')

    # chains (raw events)
    chain_rows = []
    for m_id, chains in ing.match_chains.items():
        for ci, ch in enumerate(chains):
            grids = ch.get('grids') or []
            players = ch.get('players') or []
            for seq, (g, p) in enumerate(zip(grids, players)):
                chain_rows.append((m_id, ci, seq, ch.get('team', ''),
                                   ch.get('outcome', ''), g, p))
    c.executemany("INSERT OR REPLACE INTO chains VALUES (?,?,?,?,?,?,?)", chain_rows)
    print(f'chain events: {len(chain_rows)}')

    # match_positions (per team: JSON list of distance buckets 0..11)
    def pos_buckets_json(buckets) -> str:
        return json.dumps([{edge_str(k): float(v) for k, v in b.items()} for b in buckets])

    n_pos = 0
    for m_id, (h_pos, a_pos) in ing.match_positions.items():
        c.execute("INSERT OR REPLACE INTO match_positions VALUES (?,?,?)",
                  (m_id, 'H', pos_buckets_json(h_pos)))
        c.execute("INSERT OR REPLACE INTO match_positions VALUES (?,?,?)",
                  (m_id, 'A', pos_buckets_json(a_pos)))
        n_pos += 2
    print(f'match_positions: {n_pos}')

    # match_performance
    perf_rows = [(m, p.get('expected'), edge_dict_to_json(p.get('expected_delta')),
                  p.get('actual')) for m, p in ing.match_performance.items()]
    c.executemany("INSERT OR REPLACE INTO match_performance VALUES (?,?,?,?)", perf_rows)
    print(f'match_performance: {len(perf_rows)}')

    # actual matrices
    n_act = 0
    for m_id, (h_mat, a_mat) in ing.actual_match_matrices.items():
        c.execute("INSERT OR REPLACE INTO actual_matrices VALUES (?,?,?)",
                  (m_id, 'H', edge_dict_to_json(h_mat)))
        c.execute("INSERT OR REPLACE INTO actual_matrices VALUES (?,?,?)",
                  (m_id, 'A', edge_dict_to_json(a_mat)))
        n_act += 2
    print(f'actual_matrices: {n_act}')

    # elo history
    elo_rows = [(team, m_id, elo) for team, hist in ing.team_elo_history.items()
                for m_id, elo in hist]
    c.executemany("INSERT OR REPLACE INTO elo_history VALUES (?,?,?)", elo_rows)
    print(f'elo_history: {len(elo_rows)}')

    # player history
    n_pl = 0
    for team, hist in ing.team_player_history.items():
        for m_id, players in hist:
            for player, edges in players.items():
                c.execute("INSERT OR REPLACE INTO player_history VALUES (?,?,?,?)",
                          (team, m_id, player, edge_dict_to_json(edges)))
                n_pl += 1
    print(f'player_history: {n_pl}')

    # calibration (current)
    cal = ing.calibration
    c.execute("INSERT OR REPLACE INTO calibration (id, decay, margin_b1, margin_b2,"
              " total_mean, divisor, window, n_matches, tier_cutoffs, fitted_at)"
              " VALUES (1,?,?,?,?,?,?,?,?,?)",
              (cal.decay_factor, cal.margin_b1, cal.margin_b2, cal.total_mean,
               cal.margin_divisor, cal.window, cal.n_matches,
               json.dumps(list(cal.tier_cutoffs)), 'migrated'))
    print(f'calibration: {cal.window} decay={cal.decay_factor}')

    # meta
    c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', '1')")
    c.execute("INSERT OR REPLACE INTO meta VALUES ('migrated_from', 'pickle-v7')")
    conn.commit()
    print('commit OK')

    # ---- parity check ----
    print('parity check:')
    ok = True
    n = c.execute("SELECT COUNT(*) FROM match_performance").fetchone()[0]
    ok &= (n == len(ing.match_performance))
    print(f'  match_performance rows {n} vs {len(ing.match_performance)} -> {"OK" if ok else "MISMATCH"}')
    # sample: expected values equal for 50 random matches
    import random
    random.seed(0)
    sample = random.sample(list(ing.match_performance.items()), 50)
    bad = 0
    for m_id, p in sample:
        row = c.execute("SELECT expected, actual FROM match_performance WHERE m_id=?",
                        (m_id,)).fetchone()
        if row is None or abs(row[0] - p.get('expected', 0)) > 1e-9 or \
           abs(row[1] - p.get('actual', 0)) > 1e-9:
            bad += 1
    print(f'  sample expected/actual match: {50 - bad}/50 -> {"OK" if bad == 0 else "MISMATCH"}')
    n_elo = c.execute("SELECT COUNT(*) FROM elo_history").fetchone()[0]
    n_elo_src = sum(len(h) for h in ing.team_elo_history.values())
    print(f'  elo rows {n_elo} vs {n_elo_src} -> {"OK" if n_elo == n_elo_src else "MISMATCH"}')
    conn.close()
    print('PARITY:', 'PASS' if ok and bad == 0 and n_elo == n_elo_src else 'FAIL')


if __name__ == '__main__':
    main()
