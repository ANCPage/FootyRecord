import re

with open("Core/visualize_story.py", "r", encoding="utf-8") as f:
    code = f.read()

# Update import
code = code.replace(
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR, mute_color",
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR, mute_color, get_ordinal"
)

# Update signature
code = code.replace(
    "expected_net: float, actual_net: float, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0):",
    "expected_net: float, actual_net: float, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None):"
)

# Update attack headers
code = code.replace(
    "fig.text(0.15 if not is_mobile else 0.2, text_y_attack, f'{n_b.upper()} ATTACK\\n(RATING: {int(elo_b)})', color=mute_color(c_b), fontsize=12 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)",
    "rank_b_str = f'RANK: {get_ordinal(rank_b)}' if rank_b else ''\n        tier_b_str = f' [{tier_b}]' if tier_b else ''\n        fig.text(0.15 if not is_mobile else 0.2, text_y_attack, f'{n_b.upper()} ATTACK\\n{rank_b_str}{tier_b_str}', color=mute_color(c_b), fontsize=11 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)"
)

code = code.replace(
    "fig.text(0.85 if not is_mobile else 0.8, text_y_attack, f'{n_a.upper()} ATTACK\\n(RATING: {int(elo_a)})', color=mute_color(c_a), fontsize=12 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)",
    "rank_a_str = f'RANK: {get_ordinal(rank_a)}' if rank_a else ''\n        tier_a_str = f' [{tier_a}]' if tier_a else ''\n        fig.text(0.85 if not is_mobile else 0.8, text_y_attack, f'{n_a.upper()} ATTACK\\n{rank_a_str}{tier_a_str}', color=mute_color(c_a), fontsize=11 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)"
)

with open("Core/visualize_story.py", "w", encoding="utf-8", newline="") as f:
    f.write(code)

print("Updated visualize_story.py with Rank/Tier display.")
