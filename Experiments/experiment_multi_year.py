import sys
import os
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine
import config

def run_experiment():
    csv_path = 'CSV_DATA'
    ingestor = DataIngestor(csv_path)
    ingestor.load_all_data()
    ingestor.profile_all_teams()
    
    windows_to_test = [5, 10, 15, 20, 25, 30, 40, 50, 'Dynamic']
    seasons = [2023, 2024, 2025]
    
    results = {s: {} for s in seasons}
    
    for season in seasons:
        matches = [m for m, info in ingestor.match_info.items() if info.season == season]
        matches.sort(key=lambda x: (ingestor.match_info[x].round, x))
        
        for w in windows_to_test:
            correct = 0
            total = 0
            
            for m_id in matches:
                info = ingestor.match_info[m_id]
                h_team, a_team = info.home, info.away
                
                dyn_w = max(1, info.round) if w == 'Dynamic' else w
                
                m_a = ingestor.get_team_average_matrix(h_team, window=dyn_w, up_to_season=season, up_to_round=info.round)
                m_b = ingestor.get_team_average_matrix(a_team, window=dyn_w, up_to_season=season, up_to_round=info.round)
                
                if not m_a or not m_b:
                    continue
                    
                delta = MatchupEngine.calculate_delta(m_a, m_b)
                net_delta = sum(delta.values())
                
                predicted_winner = h_team if net_delta > 0 else a_team
                actual_winner = ingestor.actual_winners.get(m_id)
                
                total += 1
                if predicted_winner == actual_winner:
                    correct += 1
                    
            acc = (correct / total) * 100 if total > 0 else 0
            results[season][w] = (correct, total, acc)

    print(f"{'Window Size':<15} | {'2023 Accuracy':<20} | {'2024 Accuracy':<20} | {'2025 Accuracy':<20}")
    print("-" * 80)
    for w in windows_to_test:
        str_2023 = f"{results[2023][w][0]}/{results[2023][w][1]} ({results[2023][w][2]:.2f}%)"
        str_2024 = f"{results[2024][w][0]}/{results[2024][w][1]} ({results[2024][w][2]:.2f}%)"
        str_2025 = f"{results[2025][w][0]}/{results[2025][w][1]} ({results[2025][w][2]:.2f}%)"
        print(f"{str(w):<15} | {str_2023:<20} | {str_2024:<20} | {str_2025:<20}")

if __name__ == '__main__':
    run_experiment()
