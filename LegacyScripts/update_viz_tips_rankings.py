import re

with open("Core/visualize_tips.py", "r", encoding="utf-8") as f:
    code = f.read()

# Update import
code = code.replace(
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR, HEADER_BG, HEADER_TEXT, mute_color",
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR, HEADER_BG, HEADER_TEXT, mute_color, get_ordinal"
)

# Replace rating line
old_line = """            winner_elo = tip.get('home_elo') if tip['winner_id'] == tip.get('home_id') else tip.get('away_elo')
            if winner_elo:
                plt.text(col_x[2], curr_y - 0.012, f'RATING: {int(winner_elo)}', ha='center', va='center', color=txt_color, fontsize=row_fs-4, zorder=2, fontproperties=self.prop_body, alpha=0.8)"""

new_line = """            winner_elo = tip.get('home_elo') if tip['winner_id'] == tip.get('home_id') else tip.get('away_elo')
            winner_rank = tip.get('home_rank') if tip['winner_id'] == tip.get('home_id') else tip.get('away_rank')
            winner_tier = tip.get('home_tier') if tip['winner_id'] == tip.get('home_id') else tip.get('away_tier')
            if winner_elo:
                rank_str = f"RANK: {get_ordinal(winner_rank)}" if winner_rank else ""
                tier_str = f" [{winner_tier}]" if winner_tier else ""
                plt.text(col_x[2], curr_y - 0.012, f'{rank_str}{tier_str}', ha='center', va='center', color=txt_color, fontsize=row_fs-4, zorder=2, fontproperties=self.prop_body, alpha=0.8)"""

code = code.replace(old_line, new_line)

with open("Core/visualize_tips.py", "w", encoding="utf-8", newline="") as f:
    f.write(code)

print("Updated visualize_tips.py with Rank/Tier display.")
