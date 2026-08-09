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
    
    matches_2025 = [m for m, info in ingestor.match_info.items() if info.season == 2025]
    matches_2025.sort(key=lambda x: (ingestor.match_info[x].round, x))
    
    windows_to_test = [5, 10, 15, 20, 25, 30, 35, 40, 50]
    
    print(f"{'Window Size':<15} | {'Correct':<10} | {'Total':<10} | {'Accuracy (incl. draws)':<25}")
    print("-" * 70)
    
    for w in windows_to_test:
        correct = 0
        total = 0
        
        for m_id in matches_2025:
            info = ingestor.match_info[m_id]
            h_team, a_team = info.home, info.away
            
            m_a = ingestor.get_team_average_matrix(h_team, window=w, up_to_season=2025, up_to_round=info.round)
            m_b = ingestor.get_team_average_matrix(a_team, window=w, up_to_season=2025, up_to_round=info.round)
            
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
        print(f"{w:<15} | {correct:<10} | {total:<10} | {acc:.2f}%")

    # Dynamic window: only games from the current season (so far)
    # This means window size grows. Since get_team_average_matrix returns up to 'window' games,
    # we can pass window=999 to get all games, but we must only include 2025 games.
    # The current engine_data logic doesn't easily allow filtering by minimum season, 
    # but we can pass window=info.round if the team plays exactly 1 game per round,
    # roughly evaluating the current season's performance. Let's test window=info.round (dynamic).
    
    correct = 0
    total = 0
    for m_id in matches_2025:
        info = ingestor.match_info[m_id]
        h_team, a_team = info.home, info.away
        
        dyn_w = max(1, info.round) # use the current round number as the window (approx current season games)
        
        m_a = ingestor.get_team_average_matrix(h_team, window=dyn_w, up_to_season=2025, up_to_round=info.round)
        m_b = ingestor.get_team_average_matrix(a_team, window=dyn_w, up_to_season=2025, up_to_round=info.round)
        
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
    print(f"{'Dynamic (Round)':<15} | {correct:<10} | {total:<10} | {acc:.2f}%")

if __name__ == '__main__':
    run_experiment()
