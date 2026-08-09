import re

with open("Core/visualize_ladder.py", "r", encoding="utf-8") as f:
    code = f.read()

# Update import
code = code.replace(
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR",
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR, get_ordinal"
)

# Update draw_cumulative_ladder team labels
# label = get_short_name(t_data['name'])
# elo_val = ingestor.get_team_elo(team_id, season, up_to_round + 1)
# full_label = f"{label} ({int(elo_val)})"
code = code.replace(
    "full_label = f\"{label} ({int(elo_val)})\"",
    "rank_val = ingestor.get_league_rankings(season, up_to_round + 1).get(team_id)\ntier_val = ingestor.get_team_tier(elo_val)\nrank_str = f'#{rank_val}' if rank_val else ''\nfull_label = f'{label} {rank_str} [{tier_val}]'"
)

# Update draw_team_journey signature
code = code.replace(
    "def draw_team_journey(self, team_id: str, ingestor, season: int, up_to_round: int, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel'):",
    "def draw_team_journey(self, team_id: str, ingestor, season: int, up_to_round: int, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel', elo: float = 1500.0, rank: int = None, tier: str = None):"
)

# Update draw_team_journey title
code = code.replace(
    "ax1.set_title(f\"{t_data['name'].upper()} ({int(current_elo)}):\\n{season} TACTICAL JOURNEY\" if is_mobile else f\"{t_data['name'].upper()} ({int(current_elo)}): {season} TACTICAL JOURNEY\", ",
    "rank_str = f'RANK: {get_ordinal(rank)}' if rank else ''\ntier_str = f' [{tier}]' if tier else ''\nax1.set_title(f\"{t_data['name'].upper()} {rank_str}{tier_str}:\\n{season} TACTICAL JOURNEY\" if is_mobile else f\"{t_data['name'].upper()} {rank_str}{tier_str}: {season} TACTICAL JOURNEY\", "
)

with open("Core/visualize_ladder.py", "w", encoding="utf-8", newline="") as f:
    f.write(code)

print("Updated visualize_ladder.py with Rank/Tier display.")
