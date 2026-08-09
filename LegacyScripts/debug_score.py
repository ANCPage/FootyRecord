import csv
from collections import defaultdict

match_scores = defaultdict(int)
seen_stats = set()
f_path = 'CSV_DATA/flattened_stats_2026.csv'

with open(f_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['matchId'] == 'CD_M20260140305':
            stat_key = (row['chain_period'], row['stat_periodSeconds'], row['x'], row['y'], row['stat_playerId'])
            if stat_key in seen_stats: continue
            seen_stats.add(stat_key)
            if row.get('chain_finalState_class') == 'SCORE' and row.get('stat_shotAtGoal') != '':
                match_scores[row['stat_teamId']] += 1

print(dict(match_scores))
