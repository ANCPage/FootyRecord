import sys
import os
import csv
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine
from mappings import TEAM_DATA

def main():
    csv_dir = 'CSV_DATA'
    ingestor = DataIngestor(csv_dir)
    print('Loading core data...')
    ingestor.load_all_data()
    ingestor.profile_all_teams()
    
    real_margins = {}
    path = os.path.join(csv_dir, 'flattened_stats_2026_simple.csv')
    if not os.path.exists(path):
        print("Missing 2026 data")
        return
        
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        match_chain_scores = defaultdict(dict)
        for row in reader:
            m_id = row['matchId']
            c_idx = row['chain_id']
            desc = row['description']
            team = row['team_id']
            
            if desc == 'Goal':
                match_chain_scores[m_id][c_idx] = (team, 6)
            elif desc == 'Behind' or 'Rushed' in desc:
                if match_chain_scores[m_id].get(c_idx, (None, 0))[1] != 6:
                    match_chain_scores[m_id][c_idx] = (team, 1)
        
        for m_id, chains in match_chain_scores.items():
            if m_id not in ingestor.match_info: continue
            h_team = ingestor.match_info[m_id].home
            a_team = ingestor.match_info[m_id].away
            
            h_score = sum(pts for team, pts in chains.values() if team == h_team)
            a_score = sum(pts for team, pts in chains.values() if team == a_team)
            real_margins[m_id] = h_score - a_score

    print('\n================================================================================')
    print(' ROUND 4 2026 - EXPECTED vs ACTUAL MARGIN (from Home Team perspective)')
    print('================================================================================')
    print(f'{"Match":<40} | {"Exp Margin":<12} | {"Act Margin":<12} | {"Diff"}')
    print('-'*80)
    
    matches = [m for m, info in ingestor.match_info.items() if info.season == 2026 and info.round == 4]
    matches.sort(key=lambda x: (ingestor.match_info[x].round, x))
    
    for m_id in matches:
        info = ingestor.match_info[m_id]
        h_team, a_team = info.home, info.away
        h_name = TEAM_DATA.get(h_team, {'name': h_team})['name']
        a_name = TEAM_DATA.get(a_team, {'name': a_team})['name']
        
        if m_id not in real_margins:
            continue
            
        m_a = ingestor.get_team_average_matrix(h_team, up_to_season=2026, up_to_round=4)
        m_b = ingestor.get_team_average_matrix(a_team, up_to_season=2026, up_to_round=4)
        
        if not m_a or not m_b:
            continue
            
        delta = MatchupEngine.calculate_delta(m_a, m_b)
        net_delta = sum(delta.values())
        
        actual_margin = real_margins[m_id]
        expected_margin = (1.1661 * net_delta) + 6.2511
        diff = abs(expected_margin - actual_margin)
        
        match_str = f'{h_name} vs {a_name}'
        print(f'{match_str:<40} | {expected_margin:>+10.1f} | {actual_margin:>+10.1f} | {diff:>6.1f}')
        
    print('================================================================================')

if __name__ == '__main__':
    main()
