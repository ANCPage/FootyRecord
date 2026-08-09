import os
import sys
import requests
import argparse
import matplotlib.pyplot as plt
import numpy as np

root_dir = os.path.dirname(os.path.abspath(__file__))
core_dir = os.path.join(root_dir, "Core")
sys.path.append(core_dir)

import config
from models import TransitionEdge
from engine_data import DataIngestor
from engine_core import MatchupEngine, home_favored
from visualize_matchup import MatchupVisualizer
from visualize_story import StoryVisualizer
from visualize_ladder import LadderVisualizer
from visualize_tips import TipsVisualizer
from mappings import TEAM_DATA

class RoundProductionPipeline:
    def __init__(self, comp_id: str, round_num: int, csv_dir: str = config.DATA_DIR):
        self.comp_id = comp_id
        self.round = round_num
        self.target_season = int(comp_id[:4])
        self.csv_dir = csv_dir
        self.ingestor = None
        self.token = None

    @staticmethod
    def get_token():
        auth_url = 'https://api.afl.com.au/cfs/afl/WMCTok'
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            resp = requests.post(auth_url, json={}, headers=headers, timeout=15)
            return resp.json().get('token')
        except:
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
        except:
            pass
        
        # Fallback to match API if roster is not available
        url_match = f'https://api.afl.com.au/cfs/afl/match/{match_id}'
        try:
            resp = requests.get(url_match, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except:
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
            
            m_a, _ = self.ingestor.get_team_average_matrix(h_id, up_to_season=self.target_season, up_to_round=self.round, return_history_info=True)
            m_b, _ = self.ingestor.get_team_average_matrix(a_id, up_to_season=self.target_season, up_to_round=self.round, return_history_info=True)
            
            if not m_a or not m_b: 
                continue
                
            delta = MatchupEngine.calculate_delta(m_a, m_b)
            net_delta = sum(delta.values())
            
            h_elo = self.ingestor.get_team_elo(h_id, self.target_season, self.round)
            a_elo = self.ingestor.get_team_elo(a_id, self.target_season, self.round)
            elo_diff = (h_elo - a_elo) / 100.0
            combined_score = net_delta + (config.config.elo_weight * elo_diff)
            
            h_rank = rankings.get(h_id)
            a_rank = rankings.get(a_id)
            h_tier = self.ingestor.get_team_tier(h_elo)
            a_tier = self.ingestor.get_team_tier(a_elo)
            
            h_name_mapped = TEAM_DATA.get(h_id, {'name': h_n})['name']
            a_name_mapped = TEAM_DATA.get(a_id, {'name': a_n})['name']
            
            round_tips.append({
                'home_name': h_name_mapped,
                'home_id': h_id, 'away_id': a_id, 'away_name': a_name_mapped,
                'winner_id': h_id if home_favored(net_delta, h_elo, a_elo) else a_id,
                'net_delta': combined_score,
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
                    viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)
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
                        viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)
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
        print(f"  Created season ladder images")
    
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
                e_d = (h_elo_eval - a_elo_eval) / 100.0
                c_s = n_d + (config.config.elo_weight * e_d)
                pred_w = m_info.home if c_s > 0 else m_info.away
                if pred_w == actual_w: 
                    season_correct += 1
                season_total += 1
                
            summary = f"ROUND {self.round} TIPS: {correct}/{total} | SEASON: {season_correct}/{season_total} ({(season_correct/season_total)*100:.1f}%)"
            print(f"  {summary}")
            tips_viz.draw_round_tips(self.round, self.target_season, evaluated_tips, os.path.join(desktop_dir, 'TIPS_RESULTS.png'), is_mobile=False, show_results=True, season_summary=summary)
            tips_viz.draw_round_tips(self.round, self.target_season, evaluated_tips, os.path.join(insta_post_dir, 'TIPS_RESULTS.png'), is_mobile=True, mobile_format='post', show_results=True, season_summary=summary)
            tips_viz.draw_round_tips(self.round, self.target_season, evaluated_tips, os.path.join(insta_reels_dir, 'TIPS_RESULTS.png'), is_mobile=True, mobile_format='reel', show_results=True, season_summary=summary)
            
        print(f"  Created round tips images")
        
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
    args = parser.parse_args()

    pipeline = RoundProductionPipeline(comp_id=args.comp_id, round_num=args.round)
    pipeline.run()

if __name__ == '__main__':
    main()
