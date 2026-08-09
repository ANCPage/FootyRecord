import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine
from mappings import TEAM_DATA

def main():
    ingestor = DataIngestor('CSV_DATA')
    ingestor.load_all_data()
    ingestor.profile_all_teams()

    mid = 'CD_M20260140207'
    if mid not in ingestor.match_info:
        print("Match not found.")
        return

    h_id = ingestor.match_info[mid].home
    a_id = ingestor.match_info[mid].away
    h_n = TEAM_DATA.get(h_id, {'name': h_id})['name']
    a_n = TEAM_DATA.get(a_id, {'name': a_id})['name']

    m_a, _ = ingestor.get_team_average_matrix(h_id, up_to_season=2026, up_to_round=2, return_history_info=True)
    m_b, _ = ingestor.get_team_average_matrix(a_id, up_to_season=2026, up_to_round=2, return_history_info=True)

    delta = MatchupEngine.calculate_delta(m_a, m_b)
    
    if mid not in ingestor.actual_match_matrices:
        print("Actual data not found.")
        return
        
    h_actual_mat, a_actual_mat = ingestor.actual_match_matrices[mid]
    actual_delta = MatchupEngine.calculate_delta(h_actual_mat, a_actual_mat)

    print(f"{h_n} (Positive) vs {a_n} (Negative)")
    
    expected_net = sum(delta.values())
    actual_net = sum(actual_delta.values())
    print(f"\nNet Expected Advantage: {expected_net:.2f}")
    print(f"Net Actual Advantage: {actual_net:.2f}")

    print("\nEXPECTED TOP EDGES:")
    expected_sorted = sorted(delta.items(), key=lambda x: abs(x[1]), reverse=True)
    for k, v in expected_sorted[:10]:
        print(f"  {k.source} -> {k.target}: {v:.2f}")

    print("\nACTUAL TOP EDGES:")
    actual_sorted = sorted(actual_delta.items(), key=lambda x: abs(x[1]), reverse=True)
    for k, v in actual_sorted[:10]:
        print(f"  {k.source} -> {k.target}: {v:.2f}")

    print("\nBIGGEST DIFFERENCES (Actual - Expected):")
    diff = {}
    all_edges = set(delta.keys()).union(set(actual_delta.keys()))
    for e in all_edges:
        exp_v = delta.get(e, 0)
        act_v = actual_delta.get(e, 0)
        diff[e] = act_v - exp_v
        
    diff_sorted = sorted(diff.items(), key=lambda x: abs(x[1]), reverse=True)
    for k, v in diff_sorted[:10]:
        exp_v = delta.get(k, 0)
        act_v = actual_delta.get(k, 0)
        print(f"  {k.source} -> {k.target}: Expected {exp_v:.2f}, Actual {act_v:.2f} (Diff: {v:+.2f})")

if __name__ == '__main__':
    main()
