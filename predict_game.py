import argparse
import os
import sys
from collections import defaultdict

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))
import config
from engine_core import MatchupEngine
from engine_data import DataIngestor
from geometry import rotate_node
from mappings import TEAM_DATA


def predict_game(round_num, game_num):
    # Setup Engine
    csv_path = 'CSV_DATA'
    ingestor = DataIngestor(csv_path)
    ingestor.load_all_data()
    ingestor.profile_all_teams()

    # Authenticate
    auth_url = 'https://api.afl.com.au/cfs/afl/WMCTok'
    headers = {'User-Agent': 'Mozilla/5.0'}
    token = requests.post(auth_url, json={}, headers=headers, timeout=15).json().get('token')

    # Get Match Context
    mid = f'CD_M2026014{int(round_num):02d}{int(game_num):02d}'
    url = f'https://api.afl.com.au/cfs/afl/matchRoster/full/{mid}'

    resp = requests.get(url, headers={'x-media-mis-token': token})
    if resp.status_code != 200:
        print(f"Could not find match {mid}")
        return

    data = resp.json().get('match')
    roster_data = resp.json().get('matchRoster')

    h_id, a_id = data['homeTeamId'], data['awayTeamId']
    h_n = TEAM_DATA.get(h_id, {'name': h_id})['name']
    a_n = TEAM_DATA.get(a_id, {'name': a_id})['name']

    # Map Rosters
    player_names = {}
    player_teams = {}

    if roster_data:
        for team_type in ['homeTeam', 'awayTeam']:
            if team_type in roster_data:
                team_info = roster_data[team_type]
                tid = team_info['teamId']
                for pos in team_info.get('positions', []):
                    p = pos['player']
                    pid = p['playerId']
                    player_names[pid] = f"{p['playerName']['givenName']} {p['playerName']['surname']}"
                    player_teams[pid] = tid
    else:
        print("No active roster data available for this match yet.")
        # Fallback to team historical mapping if no roster available

    # Calculate Engine Prediction
    m_a = ingestor.get_team_average_matrix(h_id)
    m_b = ingestor.get_team_average_matrix(a_id)
    delta = MatchupEngine.calculate_delta(m_a, m_b)

    # Identify the TOP Edges that are driving this prediction
    print(f"\n{'='*50}")
    print(f" TACTICAL MATCHUP: {h_n} vs {a_n}")
    print(f"{'='*50}")

    sorted_edges = sorted(delta.items(), key=lambda x: abs(x[1]), reverse=True)
    top_edges_h = [(e, v) for e, v in sorted_edges if v > 0][:5]
    top_edges_a = [(e, v) for e, v in sorted_edges if v < 0][:5]

    # Evaluate players who historically contribute to these specific edges
    # We will build a player matrix
    # Player ID -> Dict of Edge -> Historical decay points added

    player_edge_value = defaultdict(lambda: defaultdict(float))

    # We only look at the historical chains for these two teams to establish who their "experts" are
    for tid in [h_id, a_id]:
        # Get the history for this team (25 games)
        # Note: the match_info chronological sorting in profile_all_teams means
        # we can just use the latest 25 matches from match_chains

        matches = [m for m in ingestor.match_info.keys() if ingestor.match_info[m].home == tid or ingestor.match_info[m].away == tid]
        matches = sorted(matches, key=lambda x: (ingestor.match_info[x].season, ingestor.match_info[x].round))[-25:]

        for m_id in matches:
            for chain in ingestor.match_chains[m_id]:
                if chain['team'] != tid: continue
                grids = chain['grids']
                players = chain['players']
                if not grids or not players: continue

                collapsed_grids = []
                collapsed_players = []

                # We need to map players to the collapsed edges.
                # Simplest way: if a player was involved anywhere in the raw sequence that formed the collapsed node, they get credit for the outgoing edge.

                for g, p in zip(grids, players):
                    if not collapsed_grids or collapsed_grids[-1] != g:
                        collapsed_grids.append(g)
                        collapsed_players.append(set([p]))
                    else:
                        collapsed_players[-1].add(p)

                if len(collapsed_grids) < 2: continue

                edges = []
                for i in range(len(collapsed_grids) - 1): edges.append((collapsed_grids[i], collapsed_grids[i+1]))
                if chain['outcome'] == 'SCORE': edges.append((collapsed_grids[-1], 'SCORE'))

                n = len(edges)
                has_score = (chain['outcome'] == 'SCORE')

                for i, edge in enumerate(edges):
                    # Decay from config (single source of truth — was hardcoded 0.9)
                    decay = (config.config.decay_factor ** (n - (i+1))) if has_score else 0.0
                    if decay > 0:
                        # Which players were involved in the start node of this edge?
                        if i < len(collapsed_players):
                            for pid in collapsed_players[i]:
                                player_edge_value[pid][edge] += decay
                                player_teams[pid] = tid # Ensure we know what team they play for

    # Find the key players for the top edges
    def print_key_players(tid, target_edges, is_home):
        print(f"\n>>> {TEAM_DATA.get(tid, {'name': tid})['name']} Win Conditions:")
        for edge, delta_val in target_edges:
            # We must account for the perspective rotation if this is the away team!
            actual_edge = (edge.source, edge.target)
            if not is_home:
                # Away team's matrix is rotated in the delta calculation relative to home team
                actual_edge = (rotate_node(edge.source), rotate_node(edge.target))

            print(f"  Vector: {actual_edge[0]} -> {actual_edge[1]} (Matchup Advantage: {abs(delta_val):.2f})")

            # Find the top 2 players on this team who generate value on this specific edge
            edge_contributors = []
            for pid, edges in player_edge_value.items():
                if player_teams.get(pid) == tid and actual_edge in edges:
                    edge_contributors.append((pid, edges[actual_edge]))

            edge_contributors.sort(key=lambda x: x[1], reverse=True)

            p_str = []
            for pid, val in edge_contributors[:2]:
                name = player_names.get(pid, pid)
                p_str.append(f"{name}")

            if p_str:
                print(f"    Key Drivers: {', '.join(p_str)}")
            else:
                print("    Key Drivers: (Systemic team effort)")

    print_key_players(h_id, top_edges_h, True)
    print_key_players(a_id, top_edges_a, False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('round', type=int)
    parser.add_argument('game', type=int)
    args = parser.parse_args()
    predict_game(args.round, args.game)
