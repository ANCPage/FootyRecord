import sys
import os
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine
import config

def run_elo_experiment():
    csv_path = config.DATA_DIR
    ingestor = DataIngestor(csv_path)
    ingestor.load_all_data()
    ingestor.profile_all_teams()
    
    # 2021 is the burn-in year for the 25-game window, so we test 2022-2025
    seasons = [2022, 2023, 2024, 2025]
    
    all_matches = []
    for m_id, info in ingestor.match_info.items():
        all_matches.append(m_id)
        
    all_matches.sort(key=lambda x: (ingestor.match_info[x].season, ingestor.match_info[x].round, x))
    
    K = 32
    weights = [0.0, 0.5, 0.75, 1.0]
    
    print('Testing 25-Game Window combined with Intra-Season Tactical ELO')
    print('-' * 120)
    
    def test_strategy(strategy_name, get_diff_func, update_func):
        print(f'\n--- Strategy: {strategy_name} ---')
        print(f"{'Weight':<8} | {'2022':<16} | {'2023':<16} | {'2024':<16} | {'2025':<16}")
        print('-' * 90)
        
        for w in weights:
            ratings = defaultdict(lambda: 1500.0)
            current_season = 0
            
            correct = {s: 0 for s in seasons}
            total = {s: 0 for s in seasons}
            
            for m_id in all_matches:
                info = ingestor.match_info[m_id]
                h_team, a_team = info.home, info.away
                
                # Reset to 1500 at start of season
                if info.season != current_season:
                    current_season = info.season
                    ratings.clear()
                    
                h_val = ratings[h_team]
                a_val = ratings[a_team]
                
                diff_feature = get_diff_func(h_val, a_val)
                
                if info.season in seasons:
                    m_a = ingestor.get_team_average_matrix(h_team, window=25, up_to_season=info.season, up_to_round=info.round)
                    m_b = ingestor.get_team_average_matrix(a_team, window=25, up_to_season=info.season, up_to_round=info.round)
                    
                    if m_a and m_b:
                        delta = MatchupEngine.calculate_delta(m_a, m_b)
                        net_delta = sum(delta.values())
                        
                        combined_score = net_delta + (w * diff_feature)
                        
                        predicted_winner = h_team if combined_score > 0 else a_team
                        actual_winner = ingestor.actual_winners.get(m_id)
                        
                        if actual_winner and actual_winner != 'DRAW':
                            total[info.season] += 1
                            if predicted_winner == actual_winner:
                                correct[info.season] += 1
                                
                perf = ingestor.match_performance.get(m_id)
                actual_delta = perf.get('actual', 0.0) if perf else 0.0
                actual_winner = ingestor.actual_winners.get(m_id)
                
                if update_func and actual_winner and actual_winner != 'DRAW':
                    h_new, a_new = update_func(h_team, a_team, ratings[h_team], ratings[a_team], actual_winner, actual_delta)
                    ratings[h_team] = h_new
                    ratings[a_team] = a_new
                    
            strs = []
            for s in seasons:
                acc = (correct[s]/max(1, total[s]))*100
                strs.append(f"{correct[s]}/{total[s]} ({acc:.1f}%)")
                
            print(f'{w:<8} | {strs[0]:<16} | {strs[1]:<16} | {strs[2]:<16} | {strs[3]:<16}')
            
    def tactical_elo_update(h_team, a_team, h_elo, a_elo, actual_winner, actual_delta):
        S_h = 1.0 if actual_winner == h_team else 0.0
        S_a = 1.0 if actual_winner == a_team else 0.0
        E_h = 1 / (1 + 10 ** ((a_elo - h_elo) / 400.0))
        E_a = 1 - E_h
        margin_mult = min(3.0, max(0.5, abs(actual_delta) / 10.0 + 1.0))
        return h_elo + (K * margin_mult) * (S_h - E_h), a_elo + (K * margin_mult) * (S_a - E_a)

    test_strategy('Intra-Season Tactical ELO', lambda h, a: (h - a) / 100.0, tactical_elo_update)

if __name__ == '__main__':
    run_elo_experiment()
