import re

with open('generate_round_images.py', 'r', encoding='utf-8') as f:
    code = f.read()

bad_indent = '''        t_elo = ingestor.get_team_elo(team_id, target_season, target_round + 1)
t_rank = rankings.get(team_id)
t_tier = ingestor.get_team_tier(t_elo)
ladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(desktop_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=False, elo=t_elo, rank=t_rank, tier=t_tier)'''

fixed_indent = '''        t_elo = ingestor.get_team_elo(team_id, target_season, target_round + 1)
        t_rank = rankings.get(team_id)
        t_tier = ingestor.get_team_tier(t_elo)
        ladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(desktop_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=False, elo=t_elo, rank=t_rank, tier=t_tier)'''

code = code.replace(bad_indent, fixed_indent)

with open('generate_round_images.py', 'w', encoding='utf-8', newline='') as f:
    f.write(code)
