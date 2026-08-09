import sys
import os
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine

def get_decayed_matrix(ingestor, team_id, window=25, up_to_season=None, up_to_round=None, decay_factor=1.0):
    history = ingestor.team_history.get(team_id, [])
    filtered_history = []
    for m_id, mat in history:
        info = ingestor.match_info.get(m_id)
        if up_to_season is not None and up_to_round is not None:
            if info and (info.season > up_to_season or (info.season == up_to_season and info.round >= up_to_round)):
                continue
        filtered_history.append(mat)
    
    history = filtered_history[-window:]
    if not history: 
        return {}
        
    avg_matrix = defaultdict(float)
    n = len(history)
    
    if decay_factor == 1.0:
        weights = [1.0 / n for _ in range(n)]
    else:
        weights = [decay_factor ** (n - 1 - i) for i in range(n)]
        total_w = sum(weights)
        weights = [w / total_w for w in weights]
        
    for i, mat in enumerate(history):
        w = weights[i]
        for edge, score in mat.items(): 
            avg_matrix[edge] += score * w
            
    return dict(avg_matrix)

def run_experiment():
    csv_path = 'CSV_DATA'
    ingestor = DataIngestor(csv_path)
    ingestor.load_all_data()
    ingestor.profile_all_teams()
    
    decays_to_test = [1.0, 0.98, 0.95, 0.90, 0.85, 0.80]
    seasons = [2023, 2024, 2025]
    
    results = {s: {} for s in seasons}
    window = 25
    
    for season in seasons:
        matches = [m for m, info in ingestor.match_info.items() if info.season == season]
        matches.sort(key=lambda x: (ingestor.match_info[x].round, x))
        
        for d in decays_to_test:
            correct = 0
            total = 0
            
            for m_id in matches:
                info = ingestor.match_info[m_id]
                h_team, a_team = info.home, info.away
                
                m_a = get_decayed_matrix(ingestor, h_team, window=window, up_to_season=season, up_to_round=info.round, decay_factor=d)
                m_b = get_decayed_matrix(ingestor, a_team, window=window, up_to_season=season, up_to_round=info.round, decay_factor=d)
                
                if not m_a or not m_b:
                    continue
                    
                delta = MatchupEngine.calculate_delta(m_a, m_b)
                net_delta = sum(delta.values())
                
                predicted_winner = h_team if net_delta > 0 else a_team
                actual_winner = ingestor.actual_winners.get(m_id)
                
                if not actual_winner or actual_winner == 'DRAW':
                    continue
                
                total += 1
                if predicted_winner == actual_winner:
                    correct += 1
                    
            acc = (correct / total) * 100 if total > 0 else 0
            results[season][d] = (correct, total, acc)

    print(f"{'Decay Factor':<15} | {'2023 Accuracy':<20} | {'2024 Accuracy':<20} | {'2025 Accuracy':<20}")
    print("-" * 80)
    for d in decays_to_test:
        l = '1.0 (Flat)' if d == 1.0 else str(d)
        str_2023 = f"{results[2023][d][0]}/{results[2023][d][1]} ({results[2023][d][2]:.2f}%)"
        str_2024 = f"{results[2024][d][0]}/{results[2024][d][1]} ({results[2024][d][2]:.2f}%)"
        str_2025 = f"{results[2025][d][0]}/{results[2025][d][1]} ({results[2025][d][2]:.2f}%)"
        print(f"{l:<15} | {str_2023:<20} | {str_2024:<20} | {str_2025:<20}")

if __name__ == '__main__':
    run_experiment()
