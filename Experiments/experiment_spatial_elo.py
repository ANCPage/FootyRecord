import sys
import os
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine
import config

def run_spatial_elo_experiment():
    csv_path = config.DATA_DIR
    ingestor = DataIngestor(csv_path)
    ingestor.load_all_data()
    
    seasons = [2022, 2023, 2024, 2025, 2026]
    ingestor.profile_all_teams()
    
    all_matches = sorted(ingestor.match_info.keys(), key=lambda x: (ingestor.match_info[x].season, ingestor.match_info[x].round, x))
    
    spatial_winners = {}
    for m_id in all_matches:
        actual_delta = ingestor.match_performance.get(m_id, {}).get('actual', 0.0)
        h_team, a_team = ingestor.match_info[m_id].home, ingestor.match_info[m_id].away
        if actual_delta > 0:
            spatial_winners[m_id] = h_team
        elif actual_delta < 0:
            spatial_winners[m_id] = a_team
        else:
            spatial_winners[m_id] = 'DRAW'
            
    K = config.config.elo_k
    
    def test_strategy(strategy_name, use_spatial_winner):
        print(f'\n--- Strategy: {strategy_name} ---')
        header_years = " | ".join([f"{s:<12}" for s in seasons])
        print(f"{'Metrics':<12} | {header_years}")
        print('-' * 100)
        
        ratings = defaultdict(lambda: 1500.0)
        current_season = 0
        
        correct = {s: 0 for s in seasons}
        total = {s: 0 for s in seasons}
        
        for m_id in all_matches:
            info = ingestor.match_info[m_id]
            h_team, a_team = info.home, info.away
            
            if info.season != current_season:
                current_season = info.season
                ratings.clear()
                
            h_val = ratings[h_team]
            a_val = ratings[a_team]
            diff_feature = (h_val - a_val) / 100.0
            
            if info.season in seasons:
                m_a = ingestor.get_team_average_matrix(h_team, window=config.config.window_size, up_to_season=info.season, up_to_round=info.round)
                m_b = ingestor.get_team_average_matrix(a_team, window=config.config.window_size, up_to_season=info.season, up_to_round=info.round)
                
                if m_a and m_b:
                    delta = MatchupEngine.calculate_delta(m_a, m_b)
                    net_delta = sum(delta.values())
                    
                    combined_score = net_delta + (config.config.elo_weight * diff_feature)
                    predicted_winner = h_team if combined_score > 0 else a_team
                    
                    actual_scoreboard_winner = ingestor.actual_winners.get(m_id)
                    if actual_scoreboard_winner and actual_scoreboard_winner != 'DRAW':
                        total[info.season] += 1
                        if predicted_winner == actual_scoreboard_winner:
                            correct[info.season] += 1
            
            perf = ingestor.match_performance.get(m_id)
            actual_delta = perf.get('actual', 0.0) if perf else 0.0
            
            actual_scoreboard_winner = ingestor.actual_winners.get(m_id)
            sp_winner = spatial_winners.get(m_id)
            
            winner_to_use = sp_winner if use_spatial_winner else actual_scoreboard_winner
            
            if winner_to_use and winner_to_use != 'DRAW':
                S_h = 1.0 if winner_to_use == h_team else 0.0
                S_a = 1.0 if winner_to_use == a_team else 0.0
                E_h = 1 / (1 + 10 ** ((a_val - h_val) / 400.0))
                E_a = 1 - E_h
                margin_mult = min(3.0, max(0.5, abs(actual_delta) / 10.0 + 1.0))
                
                ratings[h_team] = h_val + (K * margin_mult) * (S_h - E_h)
                ratings[a_team] = a_val + (K * margin_mult) * (S_a - E_a)
                
        strs = []
        for s in seasons:
            acc = (correct[s]/max(1, total[s]))*100
            strs.append(f"{correct[s]}/{total[s]} ({acc:.1f}%)")
            
        print(f"{'Tips Acc':<12} | " + " | ".join([f"{val:<12}" for val in strs]))

        tot_c = sum(correct.values())
        tot_t = sum(total.values())
        print(f"Overall Accuracy: {tot_c}/{tot_t} ({(tot_c/max(1, tot_t))*100:.1f}%)")

    test_strategy('Current ELO (Actual Scoreboard Winners)', use_spatial_winner=False)
    test_strategy('Spatial ELO (Spatial Delta Winners)', use_spatial_winner=True)

if __name__ == '__main__':
    run_spatial_elo_experiment()
