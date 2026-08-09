import sys
import os
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine
from mappings import TEAM_DATA

def run_backtest():
    csv_path = 'CSV_DATA'
    ingestor = DataIngestor(csv_path)
    ingestor.load_all_data()
    ingestor.profile_all_teams()
    
    correct = 0
    total = 0
    
    matches_2026 = [m for m, info in ingestor.match_info.items() if info.season == 2026]
    matches_2026.sort(key=lambda x: (ingestor.match_info[x].round, x))
    
    results = []
    
    for m_id in matches_2026:
        info = ingestor.match_info[m_id]
        h_team, a_team = info.home, info.away
        h_name = TEAM_DATA.get(h_team, {'name': h_team})['name']
        a_name = TEAM_DATA.get(a_team, {'name': a_team})['name']
        
        m_a = ingestor.get_team_average_matrix(h_team, up_to_season=2026, up_to_round=info.round)
        m_b = ingestor.get_team_average_matrix(a_team, up_to_season=2026, up_to_round=info.round)
        
        if not m_a or not m_b:
            continue
            
        delta = MatchupEngine.calculate_delta(m_a, m_b)
        net_delta = sum(delta.values())
        
        predicted_winner = h_team if net_delta > 0 else a_team
        actual_winner = ingestor.actual_winners.get(m_id)
        
        if actual_winner == 'DRAW' or not actual_winner:
            continue
            
        total += 1
        is_correct = (predicted_winner == actual_winner)
        if is_correct:
            correct += 1
            
        results.append((info.round, h_name, a_name, is_correct))
    
    print('\n' + '='*60)
    print(' BACKTEST RESULTS: 2026 SEASON (ROUNDS 0-4)')
    print('='*60)
    print('Round    Match                                    Result')
    print('-'*60)
    
    for rnd, h_name, a_name, is_correct in results:
        status = 'CORRECT' if is_correct else 'WRONG'
        match_str = f'{h_name} vs {a_name}'
        print(f'R{rnd:<7} {match_str:<40} {status}')
        
    print('-'*60)
    if total > 0:
        print(f'TOTAL ACCURACY: {correct} / {total} ({(correct/total)*100:.1f}%)')
    else:
        print('No matches to evaluate.')

if __name__ == '__main__':
    run_backtest()
