import re

with open("Core/visualize_matchup.py", "r", encoding="utf-8") as f:
    code = f.read()

# Update import
code = code.replace(
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR, mute_color",
    "from theme import get_fonts, BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR, mute_color, get_ordinal"
)

# Update signature
code = code.replace(
    "def _add_color_key(self, fig, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.05):",
    "def _add_color_key(self, fig, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a=None, rank_b=None, tier_a=None, tier_b=None, y_pos=0.05):"
)

# Update _add_color_key body
old_body = """        fig.text(0.35, y_pos, n_a.upper(), color=self.text_color, fontsize=12, ha='right', va='center', fontproperties=self.prop_sub)
        fig.text(0.35, y_pos - 0.02, f"RATING: {int(elo_a)}", color=self.sub_text_color, fontsize=9, ha='right', va='center', fontproperties=self.prop_body)
        
        fig.add_artist(patches.Rectangle((0.36, y_pos-0.008), 0.02, 0.016, color=c_a, transform=fig.transFigure))
        fig.text(0.5, y_pos, "VS", color=self.sub_text_color, fontsize=12, ha='center', va='center', fontproperties=self.prop_sub)
        
        fig.add_artist(patches.Rectangle((0.62, y_pos-0.008), 0.02, 0.016, color=c_b, transform=fig.transFigure))
        fig.text(0.65, y_pos, n_b.upper(), color=self.text_color, fontsize=12, ha='left', va='center', fontproperties=self.prop_sub)
        fig.text(0.65, y_pos - 0.02, f"RATING: {int(elo_b)}", color=self.sub_text_color, fontsize=9, ha='left', va='center', fontproperties=self.prop_body)"""

new_body = """        fig.text(0.35, y_pos, n_a.upper(), color=self.text_color, fontsize=12, ha='right', va='center', fontproperties=self.prop_sub)
        rank_a_str = f"RANK: {get_ordinal(rank_a)}" if rank_a else ""
        tier_a_str = f" [{tier_a}]" if tier_a else ""
        fig.text(0.35, y_pos - 0.02, f"{rank_a_str}{tier_a_str} (Rating: {int(elo_a)})", color=self.sub_text_color, fontsize=8, ha='right', va='center', fontproperties=self.prop_body)
        
        fig.add_artist(patches.Rectangle((0.36, y_pos-0.008), 0.02, 0.016, color=c_a, transform=fig.transFigure))
        fig.text(0.5, y_pos, "VS", color=self.sub_text_color, fontsize=12, ha='center', va='center', fontproperties=self.prop_sub)
        
        fig.add_artist(patches.Rectangle((0.62, y_pos-0.008), 0.02, 0.016, color=c_b, transform=fig.transFigure))
        fig.text(0.65, y_pos, n_b.upper(), color=self.text_color, fontsize=12, ha='left', va='center', fontproperties=self.prop_sub)
        rank_b_str = f"RANK: {get_ordinal(rank_b)}" if rank_b else ""
        tier_b_str = f" [{tier_b}]" if tier_b else ""
        fig.text(0.65, y_pos - 0.02, f"{rank_b_str}{tier_b_str} (Rating: {int(elo_b)})", color=self.sub_text_color, fontsize=8, ha='left', va='center', fontproperties=self.prop_body)"""

code = code.replace(old_body, new_body)

# Update draw_full_matchup signature and calls
code = code.replace(
    "def draw_full_matchup(self, team_a: str, team_b: str, matrix_a: Dict, matrix_b: Dict, delta_matrix: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0):",
    "def draw_full_matchup(self, team_a: str, team_b: str, matrix_a: Dict, matrix_b: Dict, delta_matrix: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None):"
)

# Update draw_expectation_vs_actual signature
code = code.replace(
    "def draw_expectation_vs_actual(self, team_a: str, team_b: str, expected_delta: Dict, actual_delta: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0):",
    "def draw_expectation_vs_actual(self, team_a: str, team_b: str, expected_delta: Dict, actual_delta: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None):"
)

# Update calls
code = code.replace("self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.06)", "self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.06)")
code = code.replace("self._add_color_key(fig_m, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.06)", "self._add_color_key(fig_m, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.06)")
code = code.replace("self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.08)", "self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.08)")

with open("Core/visualize_matchup.py", "w", encoding="utf-8", newline="") as f:
    f.write(code)

print("Updated visualize_matchup.py with Rank/Tier display.")
