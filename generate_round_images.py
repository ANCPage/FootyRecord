# ruff: noqa: E402  (imports follow the path bootstrap below)
import argparse
import os

import matplotlib.pyplot as plt
import requests

import bootstrap  # shared sys.path bootstrap (recycle #9)

root_dir = bootstrap.ROOT

import config
import results_db
from engine_core import MatchupEngine, home_favored
from engine_data import DataIngestor
from mappings import TEAM_DATA
from models import TransitionEdge
from visualize_ladder import LadderVisualizer
from visualize_matchup import MatchupVisualizer
from visualize_story import StoryVisualizer
from visualize_tips import TipsVisualizer


class RoundProductionPipeline:
    def __init__(self, comp_id: str, round_num: int, csv_dir: str = config.DATA_DIR,
                 db_rows: dict = None, season_summary: str = None):
        self.comp_id = comp_id
        self.round = round_num
        self.target_season = int(comp_id[:4])
        self.csv_dir = csv_dir
        self.db_rows = db_rows or {}       # match_id -> decision row (compute/render separation)
        self.season_summary = season_summary  # pre-computed from the results DB
        self.ingestor = None
        self.token = None

    @staticmethod
    def get_token():
        auth_url = 'https://api.afl.com.au/cfs/afl/WMCTok'
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            resp = requests.post(auth_url, json={}, headers=headers, timeout=15)
            return resp.json().get('token')
        except Exception:
            return None

    @staticmethod
    def fetch_match_data(match_id, token):
        if not token:
            return None
        url = f'https://api.afl.com.au/cfs/afl/matchRoster/full/{match_id}'
        headers = {'x-media-mis-token': token}
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        # Fallback to match API if roster is not available
        url_match = f'https://api.afl.com.au/cfs/afl/match/{match_id}'
        try:
            resp = requests.get(url_match, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def run(self):
        # 1. Fetch token
        self.token = self.get_token()

        # 2. Setup directories
        base_images_dir = os.path.join(config.OUTPUT_DIR, str(self.target_season), f'R{self.round}')
        desktop_dir = os.path.join(base_images_dir, 'Desktop')
        mobile_dir = os.path.join(base_images_dir, 'Mobile')
        insta_post_dir = os.path.join(mobile_dir, 'InstaPost')
        insta_reels_dir = os.path.join(mobile_dir, 'InstaReels')

        os.makedirs(desktop_dir, exist_ok=True)
        os.makedirs(insta_post_dir, exist_ok=True)
        os.makedirs(insta_reels_dir, exist_ok=True)

        # 3. Load data
        print("Loading historical data...")
        self.ingestor = DataIngestor(self.csv_dir)
        self.ingestor.load_all_data()
        self.ingestor.profile_all_teams()

        # 4. Initialize visualizers
        viz = MatchupVisualizer()
        story_viz = StoryVisualizer()
        tips_viz = TipsVisualizer()
        ladder_viz = LadderVisualizer()

        # 5. Fetch matches dynamically for this round and season
        round_matches = []
        for m_id, info in self.ingestor.match_info.items():
            if info.season == self.target_season and info.round == self.round and not m_id.startswith("POST_"):
                round_matches.append(m_id)
        round_matches.sort()

        round_tips = []
        rankings = self.ingestor.get_league_rankings(self.target_season, self.round)

        for g_idx, mid in enumerate(round_matches, 1):
            info = self.ingestor.match_info[mid]
            h_id, a_id = info.home, info.away
            h_n = TEAM_DATA.get(h_id, {'name': h_id})['name']
            a_n = TEAM_DATA.get(a_id, {'name': a_id})['name']
            r_data = self.fetch_match_data(mid, self.token) or {}

            print(f'Game {g_idx}: {h_n} ({h_id}) vs {a_n} ({a_id})')
            print(f'\nProcessing Game {g_idx}: {h_n} vs {a_n}')

            # Shared matchup computation (reuse pass #7) — matrices/delta are
            # render material; DECISIONS come from the results DB when present
            # (compute/render separation, 2026-08-11).
            from prediction import compute_matchup
            pred = compute_matchup(self.ingestor, h_id, a_id,
                                   self.target_season, self.round)
            if pred is None:
                continue
            delta = pred.delta
            m_a, m_b = pred.m_home, pred.m_away
            row = self.db_rows.get(mid)
            if row is not None:
                net_delta = row['net_delta']
                h_elo, a_elo = row['home_elo'], row['away_elo']
                h_rank, a_rank = row['home_rank'], row['away_rank']
                h_tier, a_tier = row['home_tier'], row['away_tier']
                edge = row['margin']
                winner_id = row['winner']
            else:
                net_delta = pred.net_delta
                h_elo, a_elo = pred.h_elo, pred.a_elo
                h_rank, a_rank = pred.h_rank, pred.a_rank
                h_tier, a_tier = pred.h_tier, pred.a_tier
                edge = pred.edge
                winner_id = pred.winner_id

            h_name_mapped = TEAM_DATA.get(h_id, {'name': h_n})['name']
            a_name_mapped = TEAM_DATA.get(a_id, {'name': a_n})['name']

            round_tips.append({
                'home_name': h_name_mapped,
                'home_id': h_id, 'away_id': a_id, 'away_name': a_name_mapped,
                'winner_id': winner_id,
                'net_delta': net_delta,
                'edge': edge,
                'actual_winner': self.ingestor.actual_winners.get(mid),
                'home_elo': h_elo,
                'away_elo': a_elo,
                'home_rank': h_rank,
                'away_rank': a_rank,
                'home_tier': h_tier,
                'away_tier': a_tier
            })

            player_names = {}
            for t_type in ['homeTeam', 'awayTeam']:
                if t_type in r_data:
                    for pos in r_data[t_type].get('positions', []):
                        p = pos['player']
                        player_names[p['playerId']] = f"{p['playerName']['givenName'][0]}. {p['playerName']['surname']}"

            has_actual = mid in self.ingestor.actual_match_matrices
            if has_actual:
                h_actual_mat, a_actual_mat = self.ingestor.actual_match_matrices[mid]
                actual_delta = MatchupEngine.calculate_delta(h_actual_mat, a_actual_mat)

                variance_matrix = {}
                all_edges = set(delta.keys()).union(set(actual_delta.keys()))
                for e in all_edges:
                    variance_matrix[e] = actual_delta.get(e, 0) - delta.get(e, 0)

                def get_match_players(team_id, match_id):
                    for m_id, p_mat in self.ingestor.team_player_history.get(team_id, []):
                        if m_id == match_id:
                            return p_mat
                    return {}

                act_p_a = get_match_players(h_id, mid)
                act_p_b = get_match_players(a_id, mid)

                driver_annotations = {}
                sorted_vars = sorted(variance_matrix.items(), key=lambda x: abs(x[1]), reverse=True)
                top_var_edges = [edge for edge, val in sorted_vars[:5]]

                grid_names = [["A1", "B1", "C1", "D1", "E1"], ["A2", "B2", "C2", "D2", "E2"], ["A3", "B3", "C3", "D3", "E3"]]
                pos_map = {name: (r, c) for r, r_names in enumerate(grid_names) for c, name in enumerate(r_names)}
                def rotate(node):
                    if node == "SCORE": return "SCORE"
                    if node not in pos_map: return node
                    r, c = pos_map[node]
                    return grid_names[2 - r][4 - c]

                for edge in top_var_edges:
                    score = variance_matrix[edge]
                    if score > 0:
                        drivers = [(pid, v.get(edge, 0)) for pid, v in act_p_a.items() if v.get(edge, 0) > 0]
                        drivers.sort(key=lambda x: x[1], reverse=True)
                        names = [player_names.get(pid, pid) for pid, _ in drivers[:2]]
                        if names:
                            driver_annotations[edge] = ", ".join(names)
                    else:
                        actual_edge = TransitionEdge(rotate(edge.source), rotate(edge.target))
                        drivers = [(pid, v.get(actual_edge, 0)) for pid, v in act_p_b.items() if v.get(actual_edge, 0) > 0]
                        drivers.sort(key=lambda x: x[1], reverse=True)
                        names = [player_names.get(pid, pid) for pid, _ in drivers[:2]]
                        if names:
                            driver_annotations[edge] = ", ".join(names)

            old_cwd = os.getcwd()
            try:
                prefix = f'G{g_idx}_{h_n}_vs_{a_n}'.replace(' ', '')

                # Desktop
                game_desktop_dir = os.path.join(desktop_dir, prefix)
                os.makedirs(game_desktop_dir, exist_ok=True)
                os.chdir(game_desktop_dir)
                viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)
                if has_actual:
                    viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier, actual_margin=info.home_score - info.away_score)
                    story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f"STORY_{prefix}.png", is_mobile=False, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)

                    player_actuals = {}
                    player_expecteds = {}
                    hist_p_a = self.ingestor.get_team_player_matrix(h_id, up_to_season=self.target_season, up_to_round=self.round)
                    hist_p_b = self.ingestor.get_team_player_matrix(a_id, up_to_season=self.target_season, up_to_round=self.round)
                    for tid, act_mat, hist_mat in [(h_id, act_p_a, hist_p_a), (a_id, act_p_b, hist_p_b)]:
                        for pid, edges in act_mat.items():
                            player_actuals[pid] = sum(edges.values())
                            player_expecteds[pid] = sum(hist_mat.get(pid, {}).values())
                    story_viz.draw_player_performance(h_id, a_id, player_actuals, player_expecteds, player_names, f"PLAYERS_{prefix}.png", is_mobile=False)

                # Mobile
                for m_dir, m_format in [(insta_post_dir, 'post'), (insta_reels_dir, 'reel')]:
                    game_mobile_dir = os.path.join(m_dir, prefix)
                    os.makedirs(game_mobile_dir, exist_ok=True)
                    os.chdir(game_mobile_dir)
                    viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)
                    if has_actual:
                        viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier, actual_margin=info.home_score - info.away_score)
                        story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f"STORY_{prefix}.png", is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)
                        story_viz.draw_player_performance(h_id, a_id, player_actuals, player_expecteds, player_names, f"PLAYERS_{prefix}.png", is_mobile=True, mobile_format=m_format)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Error processing {mid} ({h_n} vs {a_n}): {e}")
            finally:
                os.chdir(old_cwd)
                plt.close('all')

        # Generate seasonal visualizations
        print("\nGenerating Seasonal Visualizations...")

        ladder_viz.draw_cumulative_ladder(self.ingestor, self.target_season, self.round, os.path.join(desktop_dir, 'ladder.png'), is_mobile=False)
        ladder_viz.draw_cumulative_ladder(self.ingestor, self.target_season, self.round, os.path.join(insta_post_dir, 'ladder.png'), is_mobile=True, mobile_format='post')
        ladder_viz.draw_cumulative_ladder(self.ingestor, self.target_season, self.round, os.path.join(insta_reels_dir, 'ladder.png'), is_mobile=True, mobile_format='reel')
        print("  Created season ladder images")

        print("\nFINAL TIPS LIST:")
        for tip in round_tips:
            print(f"  {tip['home_name']} vs {tip['away_name']} -> {tip['winner_id']}")

        tips_viz.draw_round_tips(self.round, self.target_season, round_tips, os.path.join(desktop_dir, 'TIPS.png'), is_mobile=False)
        tips_viz.draw_round_tips(self.round, self.target_season, round_tips, os.path.join(insta_post_dir, 'TIPS.png'), is_mobile=True, mobile_format='post')
        tips_viz.draw_round_tips(self.round, self.target_season, round_tips, os.path.join(insta_reels_dir, 'TIPS.png'), is_mobile=True, mobile_format='reel')

        evaluated_tips = [t for t in round_tips if t.get('actual_winner') is not None]
        if evaluated_tips:
            correct = sum(1 for t in evaluated_tips if t['actual_winner'] == t['winner_id'])
            total = len(evaluated_tips)

            if self.season_summary is not None:
                # Summary comes from the results DB (compute/render separation)
                summary = self.season_summary
            else:
                season_correct = correct
                season_total = total
                for mid, actual_w in self.ingestor.actual_winners.items():
                    if not mid.startswith(f'CD_M{self.target_season}'):
                        continue
                    m_info = self.ingestor.match_info[mid]
                    if m_info.round >= self.round:
                        continue
                    m_a, _ = self.ingestor.get_team_average_matrix(m_info.home, up_to_season=self.target_season, up_to_round=m_info.round, return_history_info=True)
                    m_b, _ = self.ingestor.get_team_average_matrix(m_info.away, up_to_season=self.target_season, up_to_round=m_info.round, return_history_info=True)
                    if not m_a or not m_b:
                        continue
                    d = MatchupEngine.calculate_delta(m_a, m_b)
                    n_d = sum(d.values())
                    h_elo_eval = self.ingestor.get_team_elo(m_info.home, self.target_season, m_info.round)
                    a_elo_eval = self.ingestor.get_team_elo(m_info.away, self.target_season, m_info.round)
                    # Same decision rule as the displayed picks (audit #1): the
                    # season summary must count what the model actually picked.
                    pred_w = m_info.home if home_favored(n_d, h_elo_eval, a_elo_eval) else m_info.away
                    if pred_w == actual_w:
                        season_correct += 1
                    season_total += 1
                summary = f"ROUND {self.round} TIPS: {correct}/{total} | SEASON: {season_correct}/{season_total} ({(season_correct/season_total)*100:.1f}%)"

            print(f"  {summary}")
            tips_viz.draw_round_tips(self.round, self.target_season, evaluated_tips, os.path.join(desktop_dir, 'TIPS_RESULTS.png'), is_mobile=False, show_results=True, season_summary=summary)
            tips_viz.draw_round_tips(self.round, self.target_season, evaluated_tips, os.path.join(insta_post_dir, 'TIPS_RESULTS.png'), is_mobile=True, mobile_format='post', show_results=True, season_summary=summary)
            tips_viz.draw_round_tips(self.round, self.target_season, evaluated_tips, os.path.join(insta_reels_dir, 'TIPS_RESULTS.png'), is_mobile=True, mobile_format='reel', show_results=True, season_summary=summary)

        print("  Created round tips images")

        for team_id, team_info in TEAM_DATA.items():
            team_name_clean = team_info['name'].replace(' ', '')
            t_elo = self.ingestor.get_team_elo(team_id, self.target_season, self.round + 1)
            t_rank = rankings.get(team_id)
            t_tier = self.ingestor.get_team_tier(t_elo)
            ladder_viz.draw_team_journey(team_id, self.ingestor, self.target_season, self.round, os.path.join(desktop_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=False, elo=t_elo, rank=t_rank, tier=t_tier)
            ladder_viz.draw_team_journey(team_id, self.ingestor, self.target_season, self.round, os.path.join(insta_post_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=True, mobile_format='post', elo=t_elo, rank=t_rank, tier=t_tier)
            ladder_viz.draw_team_journey(team_id, self.ingestor, self.target_season, self.round, os.path.join(insta_reels_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=True, mobile_format='reel', elo=t_elo, rank=t_rank, tier=t_tier)
        print(f"  Created team journey plots in {desktop_dir} and Mobile subfolders")
        plt.close('all')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--round', type=int, default=2)
    parser.add_argument('--comp_id', type=str, default="2026014")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--compute-only', action='store_true', help='compute + save results to the DB, no images')
    mode.add_argument('--render-only', action='store_true', help='render images from the results DB (must already be computed)')
    args = parser.parse_args()

    season = int(args.comp_id[:4])

    # Path A: compute + save (or ensure computed for the combined path)
    if not args.render_only:
        import compute_round
        ing0 = compute_round.load_ingestor()
        conn = results_db.connect()
        compute_round.compute_round(ing0, conn, season, args.round)
        conn.close()

    # Path B: render from the results DB
    if not args.compute_only:
        conn = results_db.connect()
        rows = results_db.load_round(conn, season, args.round)
        conn.close()
        if not rows:
            print(f"No results in DB for {season} R{args.round} — run compute first")
            return
        db_rows = {r['match_id']: r for r in rows}
        correct = sum(1 for r in rows if r['correct'])
        total = sum(1 for r in rows if r['actual_margin'] is not None)
        conn = results_db.connect()
        s_c, s_t = results_db.cumulative_record(conn, season, args.round)
        conn.close()
        summary = f"ROUND {args.round} TIPS: {correct}/{total} | SEASON: {s_c}/{s_t} ({100.0*s_c/s_t:.1f}%)"

        pipeline = RoundProductionPipeline(comp_id=args.comp_id, round_num=args.round,
                                           db_rows=db_rows, season_summary=summary)
        pipeline.run()
        print(f"  Summary: {summary}")


if __name__ == '__main__':
    main()
