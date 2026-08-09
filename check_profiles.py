import os
import sys

# Add Core to system path
root_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(root_dir, "Core"))

import config
from engine_data import DataIngestor
from mappings import TEAM_DATA

config.DATA_DIR = os.path.join(root_dir, "CSV_DATA")

print("Initializing Data Ingestor...")
ingestor = DataIngestor(config.DATA_DIR)
ingestor.load_all_data()
ingestor.profile_all_teams()

team_id = "CD_T80"  # Hawthorn
season = 2026
round_num = 3

print(f"\n--- Testing average matrix for {TEAM_DATA[team_id]['name']} ---")
m, used = ingestor.get_team_average_matrix(team_id, window=25, up_to_season=season, up_to_round=round_num, return_history_info=True)
print(f"Used {len(used)} matches: {used}")
print("Top 5 transitions:")
sorted_edges = sorted(m.items(), key=lambda x: x[1], reverse=True)
for edge, score in sorted_edges[:5]:
    print(f"  {edge.source} -> {edge.target}: {score:.4f}")

print(f"\n--- Testing player matrix for {TEAM_DATA[team_id]['name']} ---")
p_mat = ingestor.get_team_player_matrix(team_id, window=25, up_to_season=season, up_to_round=round_num)
print(f"Found {len(p_mat)} players with transition contributions.")
p_totals = []
for pid, pedges in p_mat.items():
    total_score = sum(pedges.values())
    p_totals.append((pid, total_score, pedges))
p_totals.sort(key=lambda x: x[1], reverse=True)

for pid, tot, pedges in p_totals[:5]:
    print(f"  Player {pid}: Total Score = {tot:.4f}")
    sorted_p_edges = sorted(pedges.items(), key=lambda x: x[1], reverse=True)
    for edge, score in sorted_p_edges[:2]:
        print(f"    {edge.source} -> {edge.target}: {score:.4f}")
