import re

with open('generate_round_images.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_block = '''        # Add ELO component
        h_elo = ingestor.get_team_elo(h_id, target_season, target_round)
        a_elo = ingestor.get_team_elo(a_id, target_season, target_round)
        elo_diff = (h_elo - a_elo) / 100.0
        combined_score = net_delta + (config.config.elo_weight * elo_diff)
        
        h_name_mapped = TEAM_DATA.get(h_id, {'name': h_n})['name']
        a_name_mapped = TEAM_DATA.get(a_id, {'name': a_n})['name']
        
        round_tips.append({
            'home_name': h_name_mapped,
            'home_id': h_id, 'away_id': a_id, 'away_name': a_name_mapped,
            'winner_id': h_id if combined_score > 0 else a_id,
            'net_delta': combined_score,
            'actual_winner': ingestor.actual_winners.get(mid),
            'home_elo': h_elo,
            'away_elo': a_elo
        })'''

new_block = '''        # Add ELO component
        h_elo = ingestor.get_team_elo(h_id, target_season, target_round)
        a_elo = ingestor.get_team_elo(a_id, target_season, target_round)
        elo_diff = (h_elo - a_elo) / 100.0
        combined_score = net_delta + (config.config.elo_weight * elo_diff)
        
        h_rank = rankings.get(h_id)
        a_rank = rankings.get(a_id)
        h_tier = ingestor.get_team_tier(h_elo)
        a_tier = ingestor.get_team_tier(a_elo)
        
        h_name_mapped = TEAM_DATA.get(h_id, {'name': h_n})['name']
        a_name_mapped = TEAM_DATA.get(a_id, {'name': a_n})['name']
        
        round_tips.append({
            'home_name': h_name_mapped,
            'home_id': h_id, 'away_id': a_id, 'away_name': a_name_mapped,
            'winner_id': h_id if combined_score > 0 else a_id,
            'net_delta': combined_score,
            'actual_winner': ingestor.actual_winners.get(mid),
            'home_elo': h_elo,
            'away_elo': a_elo,
            'home_rank': h_rank,
            'away_rank': a_rank,
            'home_tier': h_tier,
            'away_tier': a_tier
        })'''

code = code.replace(old_block, new_block)

with open('generate_round_images.py', 'w', encoding='utf-8', newline='') as f:
    f.write(code)
