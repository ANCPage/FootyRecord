# ruff: noqa: E402  (imports follow the path bootstrap below)
import base64
import json
import os
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bootstrap  # shared sys.path bootstrap (recycle #9)

root_dir = bootstrap.ROOT

import config
from elo_engine import EloEngine
from engine_core import MatchupEngine
from engine_data import DataIngestor
from mappings import TEAM_DATA
from visualize_matchup import MatchupVisualizer

# Global Ingestor State
print("Initializing FootyRecord Data Ingestor...")
ingestor = DataIngestor(config.DATA_DIR)
ingestor.load_all_data()

# Self-healing cache check: if match_info objects lack scores, delete cache and reload
has_scores = False
if ingestor.match_info:
    first_match = next(iter(ingestor.match_info.values()))
    if hasattr(first_match, 'home_score') and (first_match.home_score > 0 or first_match.away_score > 0):
        has_scores = True

if not has_scores:
    print("Cache does not contain scores. Invalidating and reloading...")
    cache_path = os.path.join(config.DATA_DIR, '.cache', 'ingestor_state.pkl')
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
            print("Deleted old cache file.")
        except Exception as e:
            print(f"Warning: Could not delete cache file: {e}")
    ingestor = DataIngestor(config.DATA_DIR)
    ingestor.load_all_data()

ingestor.profile_all_teams()
print("Data Ingestor initialized and historical profiles loaded.")

def calculate_standings(season, round_num, simulated_results=None):
    if simulated_results is None:
        simulated_results = {}

    stats = {tid: {
        'team_id': tid,
        'team_name': TEAM_DATA[tid]['name'],
        'played': 0,
        'wins': 0,
        'losses': 0,
        'draws': 0,
        'points': 0,
        'points_for': 0,
        'points_against': 0,
        'elo': 1500.0,
        'elo_change': 0.0,
        'tier': 'MID-TABLE'
    } for tid in TEAM_DATA.keys()}

    # Compile match results up to round_num
    season_matches = []
    for m_id, info in ingestor.match_info.items():
        if info.season == season and info.round <= round_num:
            season_matches.append((info.round, m_id, info))

    # Sort matches chronologically
    season_matches.sort()

    # Track ELO rating changes. ELO before the round.
    team_elos = {tid: ingestor.get_team_elo(tid, season, round_num) for tid in TEAM_DATA.keys()}
    team_elo_changes = {tid: 0.0 for tid in TEAM_DATA.keys()}

    # Process matches up to round_num - 1 (actual results)
    for r, m_id, info in season_matches:
        if r < round_num:
            is_played = (info.home_score > 0 or info.away_score > 0)
            if is_played:
                h, a = info.home, info.away
                stats[h]['played'] += 1
                stats[h]['points_for'] += info.home_score
                stats[h]['points_against'] += info.away_score
                stats[a]['played'] += 1
                stats[a]['points_for'] += info.away_score
                stats[a]['points_against'] += info.home_score

                if info.home_score > info.away_score:
                    stats[h]['wins'] += 1
                    stats[h]['points'] += 4
                    stats[a]['losses'] += 1
                elif info.away_score > info.home_score:
                    stats[a]['wins'] += 1
                    stats[a]['points'] += 4
                    stats[h]['losses'] += 1
                else:
                    stats[h]['draws'] += 1
                    stats[h]['points'] += 2
                    stats[a]['draws'] += 1
                    stats[a]['points'] += 2

    # Process matches in current round (can be simulated or actual)
    current_round_matches = [x for x in season_matches if x[0] == round_num]
    for r, m_id, info in current_round_matches:
        h, a = info.home, info.away

        # Check if overridden by simulation
        if m_id in simulated_results:
            sim = simulated_results[m_id]
            h_score = int(sim['home_score'])
            a_score = int(sim['away_score'])

            stats[h]['played'] += 1
            stats[h]['points_for'] += h_score
            stats[h]['points_against'] += a_score
            stats[a]['played'] += 1
            stats[a]['points_for'] += a_score
            stats[a]['points_against'] += h_score

            if h_score > a_score:
                stats[h]['wins'] += 1
                stats[h]['points'] += 4
                stats[a]['losses'] += 1
            elif a_score > h_score:
                stats[a]['wins'] += 1
                stats[a]['points'] += 4
                stats[h]['losses'] += 1
            else:
                stats[h]['draws'] += 1
                stats[h]['points'] += 2
                stats[a]['draws'] += 1
                stats[a]['points'] += 2

            # Compute ELO change for simulated game — single delta-based
            # formula from EloEngine (audit #2 consolidation). The simulated
            # scores drive the ladder (points/percentage) but NOT the Elo,
            # which follows the tactical delta per the delta-Elo design.
            elo_h = team_elos[h]
            elo_a = team_elos[a]

            actual_delta = 0.0
            mm = ingestor.actual_match_matrices.get(m_id)
            if mm:
                actual_delta = sum(MatchupEngine.calculate_delta(mm[0], mm[1]).values())
            else:
                m_a = ingestor.get_team_average_matrix(h, up_to_season=season,
                                                       up_to_round=round_num)
                m_b = ingestor.get_team_average_matrix(a, up_to_season=season,
                                                       up_to_round=round_num)
                if m_a and m_b:
                    actual_delta = sum(MatchupEngine.calculate_delta(m_a, m_b).values())

            d_h, d_a, _ = EloEngine.elo_update(elo_h, elo_a, actual_delta)
            team_elos[h] += d_h
            team_elos[a] += d_a

            team_elo_changes[h] = d_h
            team_elo_changes[a] = d_a

        else:
            # Not simulated: check if played in reality
            is_played = (info.home_score > 0 or info.away_score > 0)
            if is_played:
                h_score = info.home_score
                a_score = info.away_score

                stats[h]['played'] += 1
                stats[h]['points_for'] += h_score
                stats[h]['points_against'] += a_score
                stats[a]['played'] += 1
                stats[a]['points_for'] += a_score
                stats[a]['points_against'] += h_score

                if h_score > a_score:
                    stats[h]['wins'] += 1
                    stats[h]['points'] += 4
                    stats[a]['losses'] += 1
                elif a_score > h_score:
                    stats[a]['wins'] += 1
                    stats[a]['points'] += 4
                    stats[h]['losses'] += 1
                else:
                    stats[h]['draws'] += 1
                    stats[h]['points'] += 2
                    stats[a]['draws'] += 1
                    stats[a]['points'] += 2

                # Fetch actual ELO ratings before and after
                elo_before_h = ingestor.get_team_elo(h, season, round_num)
                elo_after_h = ingestor.get_team_elo(h, season, round_num + 1)
                team_elos[h] = elo_after_h
                team_elo_changes[h] = elo_after_h - elo_before_h

                elo_before_a = ingestor.get_team_elo(a, season, round_num)
                elo_after_a = ingestor.get_team_elo(a, season, round_num + 1)
                team_elos[a] = elo_after_a
                team_elo_changes[a] = elo_after_a - elo_before_a

    # For teams that did not play in the current round (e.g. had a bye):
    for tid in TEAM_DATA.keys():
        played_in_current_round = any((info.home == tid or info.away == tid) for _, _, info in current_round_matches)
        if not played_in_current_round:
            team_elos[tid] = ingestor.get_team_elo(tid, season, round_num + 1)
            team_elo_changes[tid] = team_elos[tid] - ingestor.get_team_elo(tid, season, round_num)

    # Finalize ladder
    ladder = []
    for tid, team_stats in stats.items():
        percentage = 0.0
        if team_stats['points_against'] > 0:
            percentage = (team_stats['points_for'] / team_stats['points_against']) * 100.0
        elif team_stats['points_for'] > 0:
            percentage = 999.9

        team_stats['percentage'] = percentage
        team_stats['elo'] = team_elos[tid]
        team_stats['elo_change'] = team_elo_changes[tid]
        team_stats['tier'] = ingestor.get_team_tier(team_elos[tid])
        ladder.append(team_stats)

    ladder.sort(key=lambda x: (x['points'], x['percentage'], x['elo']), reverse=True)

    for rank, entry in enumerate(ladder, 1):
        entry['rank'] = rank

    return ladder

class SimulationHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress request spam logs in terminal
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(os.path.join(root_dir, 'index.html'), 'rb') as f:
                self.wfile.write(f.read())
        elif parsed.path == '/api/teams':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            # Fetch latest ELO ratings and tiers for all teams
            teams = []
            rankings = ingestor.get_league_rankings(2026, 3)
            for tid, tinfo in TEAM_DATA.items():
                elo = ingestor.get_team_elo(tid, 2026, 3)
                tier = ingestor.get_team_tier(elo)
                rank = rankings.get(tid, 99)
                teams.append({
                    'id': tid,
                    'name': tinfo['name'],
                    'primary': tinfo['primary'],
                    'secondary': tinfo['secondary'],
                    'elo': elo,
                    'tier': tier,
                    'rank': rank
                })
            # Sort by league rank
            teams.sort(key=lambda x: x['rank'])
            self.wfile.write(json.dumps(teams).encode('utf-8'))
        elif parsed.path == '/api/seasons':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            seasons = sorted(list(set(info.season for info in ingestor.match_info.values())))
            self.wfile.write(json.dumps(seasons).encode('utf-8'))
        elif parsed.path == '/api/rounds':
            query = urllib.parse.parse_qs(parsed.query)
            season = int(query.get('season', [2026])[0])
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            rounds = sorted(list(set(info.round for info in ingestor.match_info.values() if info.season == season)))
            self.wfile.write(json.dumps(rounds).encode('utf-8'))
        elif parsed.path == '/api/fixtures':
            query = urllib.parse.parse_qs(parsed.query)
            season = int(query.get('season', [2026])[0])
            round_num = int(query.get('round', [3])[0])

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            fixtures_list = []
            for m_id, info in ingestor.match_info.items():
                if info.season == season and info.round == round_num:
                    home_team = TEAM_DATA.get(info.home, {'name': info.home, 'primary': '#333333', 'secondary': '#666666'})
                    away_team = TEAM_DATA.get(info.away, {'name': info.away, 'primary': '#333333', 'secondary': '#666666'})

                    is_played = (info.home_score > 0 or info.away_score > 0)
                    winner_id = ""
                    if is_played:
                        if info.home_score > info.away_score:
                            winner_id = info.home
                        elif info.away_score > info.home_score:
                            winner_id = info.away
                        else:
                            winner_id = "DRAW"

                    fixtures_list.append({
                        "match_id": m_id,
                        "home_id": info.home,
                        "home_name": home_team['name'],
                        "home_primary": home_team['primary'],
                        "home_secondary": home_team['secondary'],
                        "away_id": info.away,
                        "away_name": away_team['name'],
                        "away_primary": away_team['primary'],
                        "away_secondary": away_team['secondary'],
                        "home_score": info.home_score,
                        "away_score": info.away_score,
                        "is_played": is_played,
                        "winner_id": winner_id
                    })
            fixtures_list.sort(key=lambda x: x['match_id'])
            self.wfile.write(json.dumps(fixtures_list).encode('utf-8'))
        else:
            self.send_error(404, 'Not Found')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        print(f"POST request received. Path: {parsed.path}")
        if parsed.path == '/api/simulate':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))

            team_a = req['team_a']
            team_b = req['team_b']
            window_size = int(req.get('window_size', 25))
            decay_factor = float(req.get('decay_factor', 0.9))
            custom_elo_a = req.get('custom_elo_a')
            custom_elo_b = req.get('custom_elo_b')

            print(f"Simulating Match: {team_a} vs {team_b} (Window={window_size}, Decay={decay_factor})")

            # Re-profile teams if decay factor changed
            if abs(config.config.decay_factor - decay_factor) > 1e-4:
                print(f"Decay factor changed to {decay_factor}. Re-profiling graphs...")
                config.config.decay_factor = decay_factor
                ingestor._skip_profiling = False
                ingestor.profile_all_teams()

            config.config.window_size = window_size

            # Shared matchup computation (reuse pass #7)
            from prediction import compute_matchup
            overrides = {}
            if custom_elo_a is not None:
                overrides[team_a] = float(custom_elo_a)
            if custom_elo_b is not None:
                overrides[team_b] = float(custom_elo_b)
            pred = compute_matchup(ingestor, team_a, team_b, 2026, 3,
                                   window=window_size,
                                   elo_overrides=overrides or None)
            if pred is None:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Insufficient profile data for selected teams'}).encode('utf-8'))
                return

            m_a, m_b = pred.m_home, pred.m_away
            delta = pred.delta
            net_delta = pred.net_delta
            elo_diff = pred.elo_diff
            h_elo, a_elo = pred.h_elo, pred.a_elo
            h_tier, a_tier = pred.h_tier, pred.a_tier
            h_rank, a_rank = pred.h_rank, pred.a_rank

            # Make sure .cache exists for temp files
            cache_dir = os.path.join(root_dir, 'Core', '.cache')
            os.makedirs(cache_dir, exist_ok=True)
            temp_prefix = os.path.join(cache_dir, f'temp_sim_{uuid.uuid4().hex}')

            # Render tactical plot
            viz = MatchupVisualizer()
            viz.draw_full_matchup(
                team_a, team_b, m_a, m_b, delta,
                save_prefix=temp_prefix, is_mobile=False,
                elo_a=h_elo, elo_b=a_elo,
                rank_a=h_rank, rank_b=a_rank,
                tier_a=h_tier, tier_b=a_tier
            )

            # Read image and encode to Base64
            png_path = f"{temp_prefix}.png"
            img_base64 = ""
            if os.path.exists(png_path):
                with open(png_path, 'rb') as f:
                    img_base64 = base64.b64encode(f.read()).decode('utf-8')
                try:
                    os.remove(png_path)
                except Exception as e:
                    print(f"Warning: Could not remove temp simulation image file: {e}")

            # Prepare API response
            response = {
                'team_a': team_a,
                'team_b': team_b,
                'home_name': TEAM_DATA[team_a]['name'],
                'away_name': TEAM_DATA[team_b]['name'],
                'winner_name': TEAM_DATA[pred.winner_id]['name'],
                'winner_id': pred.winner_id,
                'net_delta': net_delta,
                'elo_diff': elo_diff,
                'home_elo': h_elo,
                'away_elo': a_elo,
                'home_tier': h_tier,
                'away_tier': a_tier,
                'home_rank': h_rank,
                'away_rank': a_rank,
                'image': img_base64
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        elif parsed.path == '/api/predict-round':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))

            season = int(req.get('season', 2026))
            round_num = int(req.get('round', 3))
            window_size = int(req.get('window_size', 25))
            decay_factor = float(req.get('decay_factor', 0.9))

            # Re-profile teams if decay factor changed
            if abs(config.config.decay_factor - decay_factor) > 1e-4:
                print(f"Decay factor changed to {decay_factor}. Re-profiling graphs...")
                config.config.decay_factor = decay_factor
                ingestor._skip_profiling = False
                ingestor.profile_all_teams()

            config.config.window_size = window_size

            predictions = {}
            for m_id, info in ingestor.match_info.items():
                if info.season == season and info.round == round_num:
                    team_a = info.home
                    team_b = info.away

                    # Shared matchup computation (reuse pass #7)
                    from prediction import compute_matchup
                    pred = compute_matchup(ingestor, team_a, team_b,
                                           season, round_num,
                                           window=window_size)
                    if pred is None:
                        continue

                    predicted_margin = abs(pred.home_score - pred.away_score)
                    predictions[m_id] = {
                        "predicted_winner_id": pred.winner_id,
                        "predicted_home_score": pred.home_score,
                        "predicted_away_score": pred.away_score,
                        "predicted_margin": predicted_margin,
                        "probability_home": pred.prob_home,
                        "probability_away": 1.0 - pred.prob_home,
                        "home_elo": pred.h_elo,
                        "away_elo": pred.a_elo
                    }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(predictions).encode('utf-8'))

        elif parsed.path == '/api/ladder':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))

            season = int(req.get('season', 2026))
            round_num = int(req.get('round', 3))
            simulated_results = req.get('simulated_results', {})

            ladder = calculate_standings(season, round_num, simulated_results)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(ladder).encode('utf-8'))

        elif parsed.path == '/api/backtest-sweep':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))

            season = int(req.get('season', 2026))
            param_to_sweep = req.get('param_to_sweep', 'window_size')

            start = float(req.get('start', 5))
            end = float(req.get('end', 45))
            step = float(req.get('step', 5))

            fixed_window = int(req.get('fixed_window', 25))
            fixed_decay = float(req.get('fixed_decay', 0.9))

            # Save original config
            orig_window = config.config.window_size
            orig_decay = config.config.decay_factor

            results = []

            # Generate sweep values
            values = []
            cur = start
            while cur <= end + 1e-9:
                if param_to_sweep == 'window_size':
                    values.append(int(round(cur)))
                else:
                    values.append(cur)
                cur += step
            # Deduplicate
            values = sorted(list(set(values)))

            for val in values:
                # Set parameters
                if param_to_sweep == 'window_size':
                    config.config.window_size = val
                    config.config.decay_factor = fixed_decay
                elif param_to_sweep == 'decay_factor':
                    config.config.window_size = fixed_window
                    config.config.decay_factor = val
                    # Re-profile since decay changed
                    ingestor._skip_profiling = False
                    ingestor.profile_all_teams()

                # Run backtest
                correct = 0
                total = 0
                season_matches = [m for m, info in ingestor.match_info.items() if info.season == season and not m.startswith("POST_")]
                # Sort matches by round
                season_matches = sorted(season_matches, key=lambda x: (ingestor.match_info[x].round, x))

                for m_id in season_matches:
                    info = ingestor.match_info[m_id]
                    h_team, a_team = info.home, info.away

                    # Shared matchup computation (reuse pass #7)
                    from prediction import compute_matchup
                    pred = compute_matchup(ingestor, h_team, a_team,
                                           season, info.round)
                    if pred is None:
                        continue

                    pred_winner = pred.winner_id
                    act_winner = ingestor.actual_winners.get(m_id)

                    if act_winner == 'DRAW' or not act_winner:
                        continue

                    total += 1
                    if pred_winner == act_winner:
                        correct += 1

                accuracy = (correct / total) * 100.0 if total > 0 else 0.0
                results.append({'value': val, 'accuracy': accuracy, 'correct': correct, 'total': total})

            # Restore original config
            config.config.window_size = orig_window
            if abs(config.config.decay_factor - orig_decay) > 1e-4:
                config.config.decay_factor = orig_decay
                ingestor._skip_profiling = False
                ingestor.profile_all_teams()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode('utf-8'))
        elif parsed.path == '/api/team-profile':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))

            team_id = req['team_id']
            season_val = req.get('season')
            season = int(season_val) if (season_val is not None and str(season_val).isdigit()) else 2026

            round_val = req.get('round')
            round_num = int(round_val) if (round_val is not None and str(round_val).isdigit()) else 3

            window_val = req.get('window_size')
            window_size = int(window_val) if (window_val is not None and str(window_val).isdigit()) else 25

            decay_val = req.get('decay_factor')
            decay_factor = float(decay_val) if decay_val is not None else 0.9

            # Re-profile teams if decay factor changed
            if abs(config.config.decay_factor - decay_factor) > 1e-4:
                print(f"Decay factor changed to {decay_factor}. Re-profiling graphs...")
                config.config.decay_factor = decay_factor
                ingestor._skip_profiling = False
                ingestor.profile_all_teams()

            config.config.window_size = window_size

            m_a, used_matches = ingestor.get_team_average_matrix(team_id, window=window_size, up_to_season=season, up_to_round=round_num, return_history_info=True)
            p_mat = ingestor.get_team_player_matrix(team_id, window=window_size, up_to_season=season, up_to_round=round_num)

            edges_list = []
            for edge, score in m_a.items():
                edges_list.append({
                    'source': edge.source,
                    'target': edge.target,
                    'score': score
                })

            players_list = []
            for pid, pedges in p_mat.items():
                p_edges_list = []
                total_p_score = 0.0
                for edge, score in pedges.items():
                    p_edges_list.append({
                        'source': edge.source,
                        'target': edge.target,
                        'score': score
                    })
                    total_p_score += score

                if total_p_score > 0.05:
                    players_list.append({
                        'player_id': pid,
                        'total_score': total_p_score,
                        'edges': sorted(p_edges_list, key=lambda x: x['score'], reverse=True)
                    })

            players_list.sort(key=lambda x: x['total_score'], reverse=True)

            elo = ingestor.get_team_elo(team_id, season, round_num)
            tier = ingestor.get_team_tier(elo)

            rankings = ingestor.get_league_rankings(season, round_num)
            rank = rankings.get(team_id, 99)

            response = {
                'team_id': team_id,
                'team_name': TEAM_DATA[team_id]['name'],
                'primary': TEAM_DATA[team_id]['primary'],
                'secondary': TEAM_DATA[team_id]['secondary'],
                'elo': elo,
                'tier': tier,
                'rank': rank,
                'used_matches': used_matches,
                'edges': edges_list,
                'players': players_list[:15]
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_error(404, 'Not Found')

def run(port=8000):
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, SimulationHandler)
    print("\n==================================================")
    print(" AFL Tactical Simulation Server is running local ")
    print(f" URL: http://localhost:{port}")
    print("==================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    print("\nShutting down simulation server...")
    httpd.server_close()

if __name__ == '__main__':
    run()
