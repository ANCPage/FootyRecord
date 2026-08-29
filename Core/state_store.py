"""Engine-state persistence for the one-store design (2026-08-11).

DataIngestor's working state lives in SQLite (same DB as the results) instead
of the pickle cache. `save_state` writes the state tables; `load_state`
hydrates them back into the in-memory structures. The `meta` table replaces
the CACHE_VERSION fingerprint check.

State tables (owned here): matches, chains, match_positions,
match_performance, actual_matrices, elo_history, player_history, calibration.
Results tables (predictions, calibration_log) are owned by results_db.
"""
import json
import os
import sqlite3

import Core.results_db  # noqa: F401  (DB_PATH lives here — one constant for both stores)
from Core.models import MatchInfo, TransitionEdge
from Core.results_db import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    m_id TEXT PRIMARY KEY, season INTEGER, round INTEGER,
    home TEXT, away TEXT, home_score INTEGER, away_score INTEGER);
CREATE TABLE IF NOT EXISTS chains (
    m_id TEXT, chain_idx INTEGER, seq INTEGER,
    team TEXT, outcome TEXT, grid TEXT, player TEXT,
    PRIMARY KEY (m_id, chain_idx, seq));
CREATE INDEX IF NOT EXISTS idx_chains_mid ON chains(m_id);
CREATE INDEX IF NOT EXISTS idx_chains_outcome ON chains(outcome);
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
"""


def connect(db_path: str = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def edge_str(k) -> str:
    """TransitionEdge or plain (start, end) tuple -> 'start->end'."""
    if hasattr(k, 'source'):
        return f'{k.source}->{k.target}'
    return f'{k[0]}->{k[1]}'


def edge_dict_from_json(s) -> dict:
    """'start->end': weight JSON -> {TransitionEdge: weight}."""
    if not s:
        return {}
    return {TransitionEdge(*k.split('->')): v for k, v in json.loads(s).items()}


def edge_dict_to_json(d) -> str:
    return json.dumps({edge_str(k): float(v) for k, v in d.items()}) if d else None


def scoring_chains(conn) -> dict:
    """All SCORE-outcome chains grouped as {(m_id, chain_idx): [(seq, team, grid)]}.

    Uses idx_chains_outcome. Phase 2 (2026-08-26): scoring_graph.py used to
    inline this SQL with its own sqlite3 connection.
    """
    from collections import defaultdict
    rows = conn.execute(
        "SELECT m_id, chain_idx, seq, team, grid FROM chains WHERE outcome='SCORE'"
    ).fetchall()
    chains = defaultdict(list)
    for m_id, cidx, seq, team, grid in rows:
        chains[(m_id, cidx)].append((seq, team, grid))
    return chains


def save_state(conn, ing) -> None:
    """Write the ingestor's working state to SQLite (one transaction)."""
    c = conn.cursor()
    c.executemany("INSERT OR REPLACE INTO matches VALUES (?,?,?,?,?,?,?)",
                  [(m, i.season, i.round, i.home, i.away, i.home_score, i.away_score)
                   for m, i in ing.match_info.items()])
    chain_rows = []
    for m_id, chains in ing.match_chains.items():
        for ci, ch in enumerate(chains):
            grids = ch.get('grids') or []
            players = ch.get('players') or []
            for seq, (g, p) in enumerate(zip(grids, players)):
                chain_rows.append((m_id, ci, seq, ch.get('team', ''),
                                   ch.get('outcome', ''), g, p))
    c.executemany("INSERT OR REPLACE INTO chains VALUES (?,?,?,?,?,?,?)", chain_rows)
    for m_id, (h_pos, a_pos) in ing.match_positions.items():
        c.execute("INSERT OR REPLACE INTO match_positions VALUES (?,?,?)",
                  (m_id, 'H', json.dumps([{edge_str(k): float(v) for k, v in b.items()}
                                          for b in h_pos])))
        c.execute("INSERT OR REPLACE INTO match_positions VALUES (?,?,?)",
                  (m_id, 'A', json.dumps([{edge_str(k): float(v) for k, v in b.items()}
                                          for b in a_pos])))
    c.executemany("INSERT OR REPLACE INTO match_performance VALUES (?,?,?,?)",
                  [(m, p.get('expected'), edge_dict_to_json(p.get('expected_delta')),
                    p.get('actual')) for m, p in ing.match_performance.items()])
    for m_id, (h_mat, a_mat) in ing.actual_match_matrices.items():
        c.execute("INSERT OR REPLACE INTO actual_matrices VALUES (?,?,?)",
                  (m_id, 'H', edge_dict_to_json(h_mat)))
        c.execute("INSERT OR REPLACE INTO actual_matrices VALUES (?,?,?)",
                  (m_id, 'A', edge_dict_to_json(a_mat)))
    # Purge stale POST_ tails (2026-08-25): the POST_ id encodes the team's
    # last match AT THE TIME OF THAT REBUILD — old-era rows (different ids)
    # survive INSERT OR REPLACE and corrupt rebuild_index's pairing on load
    # (Sydney/Port showed one-match-stale ratings after the v8 rebuild).
    # elo_history is derived data: the in-memory state owns every row.
    c.execute("DELETE FROM elo_history WHERE m_id LIKE 'POST_%'")
    c.executemany("INSERT OR REPLACE INTO elo_history VALUES (?,?,?)",
                  [(team, m_id, elo) for team, hist in ing.team_elo_history.items()
                   for m_id, elo in hist])
    for team, hist in ing.team_player_history.items():
        for m_id, players in hist:
            for player, edges in players.items():
                c.execute("INSERT OR REPLACE INTO player_history VALUES (?,?,?,?)",
                          (team, m_id, player, edge_dict_to_json(edges)))
    cal = ing.calibration
    c.execute("INSERT OR REPLACE INTO calibration (id, decay, margin_b1, margin_b2,"
              " total_mean, divisor, window, n_matches, tier_cutoffs, fitted_at)"
              " VALUES (1,?,?,?,?,?,?,?,?,?)",
              (cal.decay_factor, cal.margin_b1, cal.margin_b2, cal.total_mean,
               cal.margin_divisor, cal.window, cal.n_matches,
               json.dumps(list(cal.tier_cutoffs)), 'state-save'))
    conn.commit()


def load_state(conn, skip_chains: bool = False) -> dict:
    """Hydrate the ingestor's working state from SQLite.

    skip_chains=True (perf 2026-08-12): render/compute paths never touch
    match_chains (it exists only for profiling) — skipping the ~1.9M-row
    chains table cuts load time roughly 3x. The key is still present
    (empty) so __dict__.update() consumers behave.
    """
    from collections import defaultdict

    state = {}
    c = conn.cursor()

    # matches + derived: match_info, actual_winners
    match_info = {}
    actual_winners = {}
    for m, season, rnd, home, away, hs, as_ in c.execute(
            "SELECT m_id, season, round, home, away, home_score, away_score FROM matches"):
        match_info[m] = MatchInfo(season=season, round=rnd, home=home, away=away,
                                  home_score=hs or 0, away_score=as_ or 0)
        if hs and as_:
            actual_winners[m] = home if hs > as_ else (away if as_ > hs else 'DRAW')
    state['match_info'] = match_info
    state['actual_winners'] = actual_winners

    # chains
    if skip_chains:
        state['match_chains'] = defaultdict(list)
    else:
        match_chains = defaultdict(lambda: defaultdict(lambda: {
            'team': '', 'outcome': '', 'grids': [], 'players': [], 'matchId': ''}))
        for m_id, ci, seq, team, outcome, grid, player in c.execute(
                "SELECT m_id, chain_idx, seq, team, outcome, grid, player FROM chains ORDER BY m_id, chain_idx, seq"):
            ch = match_chains[m_id][ci]
            ch['team'] = team
            ch['outcome'] = outcome
            ch['grids'].append(grid)
            ch['players'].append(player)
            ch['matchId'] = m_id
        state['match_chains'] = {m: list(d.values()) for m, d in match_chains.items()}

    # match_positions
    match_positions = {}
    for m_id, team, pos_json in c.execute(
            "SELECT m_id, team, pos FROM match_positions"):
        buckets = [{TransitionEdge(*k.split('->')): v for k, v in b.items()}
                   for b in json.loads(pos_json)]
        h, a = match_positions.get(m_id, (None, None))
        if team == 'H':
            match_positions[m_id] = (buckets, a)
        else:
            match_positions[m_id] = (h, buckets)
    state['match_positions'] = match_positions

    # team_positions (derived: team -> [(m_id, pos)], chronological — the DB
    # SELECT has no ORDER BY, so sort explicitly; dict insertion order is not
    # a contract (re-audit 2026-08-12).
    team_positions = defaultdict(list)
    for m_id in sorted(match_positions,
                       key=lambda m: (match_info[m].season, match_info[m].round)):
        h_pos, a_pos = match_positions[m_id]
        team_positions[match_info[m_id].home].append((m_id, h_pos))
        team_positions[match_info[m_id].away].append((m_id, a_pos))
    state['team_positions'] = team_positions

    # match_performance
    perf = {}
    for m, exp, exp_delta, act in c.execute(
            "SELECT m_id, expected, expected_delta, actual FROM match_performance"):
        perf[m] = {'expected': exp, 'expected_delta': edge_dict_from_json(exp_delta),
                   'actual': act}
    state['match_performance'] = perf

    # actual matrices
    actual = {}
    for m_id, team, mat_json in c.execute(
            "SELECT m_id, team, mat FROM actual_matrices"):
        mat = edge_dict_from_json(mat_json)
        h, a = actual.get(m_id, (None, None))
        if team == 'H':
            actual[m_id] = (mat, a)
        else:
            actual[m_id] = (h, mat)
    state['actual_match_matrices'] = actual

    # elo history
    elo_hist = defaultdict(list)
    for team, m_id, elo in c.execute(
            "SELECT team, m_id, elo FROM elo_history ORDER BY team, m_id"):
        elo_hist[team].append((m_id, elo))
    state['team_elo_history'] = elo_hist

    # player history
    pl_hist = defaultdict(list)
    cur = c.execute("SELECT team, m_id, player, edges FROM player_history ORDER BY team, m_id")
    rows = cur.fetchall()
    by_team_match = {}
    for team, m_id, player, edges in rows:
        by_team_match.setdefault((team, m_id), {})[player] = edge_dict_from_json(edges)
    for (team, m_id), players in sorted(by_team_match.items()):
        pl_hist[team].append((m_id, players))
    state['team_player_history'] = pl_hist

    # calibration
    row = c.execute("SELECT decay, margin_b1, margin_b2, total_mean, divisor,"
                    " window, n_matches, tier_cutoffs FROM calibration WHERE id=1").fetchone()
    if row:
        from Core.calibration import Calibration
        state['calibration'] = Calibration(
            margin_b1=row[1], margin_b2=row[2], total_mean=row[3],
            margin_divisor=row[4], window=row[5], n_matches=row[6],
            tier_cutoffs=tuple(json.loads(row[7])) if row[7] else (),
            decay_factor=row[0])
    return state


def meta_get(conn, key: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
    conn.commit()
