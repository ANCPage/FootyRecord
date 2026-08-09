import sys
import os
import csv
from collections import defaultdict
import numpy as np

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine

def main():
    csv_dir = 'CSV_DATA'
    ingestor = DataIngestor(csv_dir)
    print('Loading core data...')
    ingestor.load_all_data()
    ingestor.profile_all_teams()
    
    real_margins = {}
    for year in [2024, 2025]:
        path = os.path.join(csv_dir, f'flattened_stats_{year}_simple.csv')
        if not os.path.exists(path):
            continue
        
        print(f'Extracting real scores from {year}...')
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

    x_vals = []
    y_vals = []
    
    print('\nRunning backtest and regression analysis...')
    for year in [2024, 2025]:
        matches = [m for m, info in ingestor.match_info.items() if info.season == year]
        matches.sort(key=lambda x: (ingestor.match_info[x].round, x))
        
        for m_id in matches:
            info = ingestor.match_info[m_id]
            h_team, a_team = info.home, info.away
            
            if m_id not in real_margins:
                continue
                
            m_a = ingestor.get_team_average_matrix(h_team, up_to_season=year, up_to_round=info.round)
            m_b = ingestor.get_team_average_matrix(a_team, up_to_season=year, up_to_round=info.round)
            
            if not m_a or not m_b:
                continue
                
            delta = MatchupEngine.calculate_delta(m_a, m_b)
            net_delta = sum(delta.values())
            
            actual_margin = real_margins[m_id]
            
            x_vals.append(net_delta)
            y_vals.append(actual_margin)
            
    if len(x_vals) > 0:
        slope, intercept = np.polyfit(x_vals, y_vals, 1)
        correlation_matrix = np.corrcoef(x_vals, y_vals)
        r_value = correlation_matrix[0,1]
        print(f'\n==================================================')
        print(f' BACKTEST & MARGIN ANALYSIS: 2024-2025 SEASONS')
        print(f'==================================================')
        print(f'Analyzed Matches  : {len(x_vals)}')
        print(f'Correlation (r)   : {r_value:.4f}')
        print(f'R-squared (R^2)   : {r_value**2:.4f}')
        print(f'--------------------------------------------------')
        print(f'PREDICTIVE EQUATION:')
        print(f'Expected Margin = {slope:.4f} * (Tactical Score) + {intercept:.4f}')
        print(f'--------------------------------------------------')
    else:
        print('No matches analyzed. Check data availability.')

if __name__ == '__main__':
    main()
