import re

with open('Core/visualize_ladder.py', 'r', encoding='utf-8') as f:
    code = f.read()

bad_indent = '''            rank_val = ingestor.get_league_rankings(season, up_to_round + 1).get(team_id)
tier_val = ingestor.get_team_tier(elo_val)
rank_str = f'#{rank_val}' if rank_val else ''
full_label = f'{label} {rank_str} [{tier_val}]'
            
            y_pos = label_y_positions[team_id]'''

fixed_indent = '''            rank_val = ingestor.get_league_rankings(season, up_to_round + 1).get(team_id)
            tier_val = ingestor.get_team_tier(elo_val)
            rank_str = f'#{rank_val}' if rank_val else ''
            full_label = f'{label} {rank_str} [{tier_val}]'
            
            y_pos = label_y_positions[team_id]'''

code = code.replace(bad_indent, fixed_indent)

with open('Core/visualize_ladder.py', 'w', encoding='utf-8', newline='') as f:
    f.write(code)
