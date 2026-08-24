"""Predict a live upcoming game (API fixture) with the SHARED engine path.

Unique value vs compute_round: fetches the fixture from the AFL API before
the CSVs know about it. Everything else is shared — `compute_matchup()` for
the prediction, the STORED player history for the "key drivers" panel (no
chain reprocessing), and the results DB for the record (pending prediction
that the walk-forward replaces once the round is played).

Usage:
    python predict_game.py <round> <game>
"""
import argparse
from collections import defaultdict
from datetime import datetime

import requests

import Core.results_db as results_db
from Core.engine_data import DataIngestor
from Core.geometry import rotate_node
from Core.mappings import TEAM_DATA
from Core.prediction import compute_matchup


def predict_game(round_num, game_num, season=None):
    if season is None:
        season = datetime.now().year  # no hardcoded year (re-audit 2026-08-12)
    ingestor = DataIngestor('CSV_DATA')
    ingestor.load_all_data()
    if not ingestor.team_positions:
        ingestor.profile_all_teams()

    # Authenticate + fetch the live fixture (the unique input)
    token = requests.post('https://api.afl.com.au/cfs/afl/WMCTok', json={},
                          headers={'User-Agent': 'Mozilla/5.0'}, timeout=15).json().get('token')
    mid = f'CD_M{season}014{int(round_num):02d}{int(game_num):02d}'
    resp = requests.get(f'https://api.afl.com.au/cfs/afl/matchRoster/full/{mid}',
                        headers={'x-media-mis-token': token}, timeout=15)
    if resp.status_code != 200:
        print(f"Could not find match {mid}")
        return
    data = resp.json().get('match')
    roster_data = resp.json().get('matchRoster')

    h_id, a_id = data['homeTeamId'], data['awayTeamId']
    h_n = TEAM_DATA.get(h_id, {'name': h_id})['name']
    a_n = TEAM_DATA.get(a_id, {'name': a_id})['name']

    player_names = {}
    player_teams = {}
    if roster_data:
        for team_type in ['homeTeam', 'awayTeam']:
            if team_type in roster_data:
                tid = roster_data[team_type]['teamId']
                for pos in roster_data[team_type].get('positions', []):
                    p = pos['player']
                    pid = p['playerId']
                    player_names[pid] = f"{p['playerName']['givenName']} {p['playerName']['surname']}"
                    player_teams[pid] = tid
    else:
        print("No active roster data available for this match yet.")

    # Shared prediction (delta, net, margin, winner)
    pred = compute_matchup(ingestor, h_id, a_id, season, round_num)
    if pred is None:
        print("Could not compute a prediction for this matchup.")
        return
    delta = pred.delta

    print(f"\n{'='*50}")
    print(f" TACTICAL MATCHUP: {h_n} vs {a_n}")
    print(f"{'='*50}")

    sorted_edges = sorted(delta.items(), key=lambda x: abs(x[1]), reverse=True)
    top_edges_h = [(e, v) for e, v in sorted_edges if v > 0][:5]
    top_edges_a = [(e, v) for e, v in sorted_edges if v < 0][:5]

    # Key drivers from the STORED player history (engine's decay-applied
    # credits — one source of truth, no chain reprocessing)
    player_edge_value = defaultdict(lambda: defaultdict(float))
    for tid in [h_id, a_id]:
        for _m_id, player_map in ingestor.team_player_history.get(tid, [])[-25:]:
            for pid, edges in player_map.items():
                player_teams[pid] = tid
                for edge, val in edges.items():
                    player_edge_value[pid][edge] += val

    def print_key_players(tid, target_edges, is_home):
        print(f"\n>>> {TEAM_DATA.get(tid, {'name': tid})['name']} Win Conditions:")
        for edge, delta_val in target_edges:
            actual_edge = (edge.source, edge.target)
            if not is_home:
                actual_edge = (rotate_node(edge.source), rotate_node(edge.target))
            print(f"  Vector: {actual_edge[0]} -> {actual_edge[1]} (Matchup Advantage: {abs(delta_val):.2f})")
            contributors = sorted(
                ((pid, edges[actual_edge]) for pid, edges in player_edge_value.items()
                 if player_teams.get(pid) == tid and actual_edge in edges),
                key=lambda x: x[1], reverse=True)[:2]
            names = [player_names.get(pid, pid) for pid, _ in contributors]
            print(f"    Key Drivers: {', '.join(names)}" if names
                  else "    Key Drivers: (Systemic team effort)")

    print_key_players(h_id, top_edges_h, True)
    print_key_players(a_id, top_edges_a, False)

    # Record the pending prediction in the results DB (walk-forward replaces
    # it once the round is played and the CSVs land)
    from types import SimpleNamespace

    import Core.calibration as cal
    game = results_db.game_row_from_prediction(
        pred, SimpleNamespace(home=h_id, away=a_id, home_score=0, away_score=0),
        season, round_num, cal.current, mid, played=False)
    conn = results_db.connect()
    results_db.upsert_prediction(conn, game)
    results_db.upsert_calibration(
        conn, season, round_num,
        results_db.build_calibration_snapshot(cal.current, 'live-api'))
    conn.commit()
    conn.close()
    print(f"\nPrediction recorded: {h_n} vs {a_n} -> {TEAM_DATA.get(pred.winner_id, {'name': pred.winner_id})['name']} by {pred.margin_pred:.0f} pts")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('round', type=int)
    parser.add_argument('game', type=int)
    parser.add_argument('--season', type=int, default=None,
                        help='season year (default: current year)')
    args = parser.parse_args()
    predict_game(args.round, args.game, args.season)
