import sys
import os
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor

ingestor = DataIngestor('CSV_DATA')
ingestor.load_all_data()

multi_ratings = defaultdict(lambda: 1500.0)
soft_ratings = defaultdict(lambda: 1500.0)
sorted_matches = sorted(ingestor.match_info.keys(), key=lambda x: (ingestor.match_info[x].season, ingestor.match_info[x].round))

current_season = 0
for m_id in sorted_matches:
    info = ingestor.match_info[m_id]
    if current_season != 0 and info.season != current_season:
        for t in soft_ratings:
            soft_ratings[t] = (soft_ratings[t] * 0.70) + (1500.0 * 0.30)
    current_season = info.season
    
    # fake update just to see if we get drift
    multi_ratings[info.home] += 10
    multi_ratings[info.away] -= 10
    soft_ratings[info.home] += 10
    soft_ratings[info.away] -= 10

print(list(multi_ratings.values())[:5])
print(list(soft_ratings.values())[:5])
