import re

# 1. Update MatchupVisualizer
with open("Core/visualize_matchup.py", "r", encoding="utf-8") as f:
    code = f.read()

# Add elo_a, elo_b to method signatures
code = code.replace(
    "def draw_full_matchup(self, team_a: str, team_b: str, matrix_a: Dict, matrix_b: Dict, delta_matrix: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel'):",
    "def draw_full_matchup(self, team_a: str, team_b: str, matrix_a: Dict, matrix_b: Dict, delta_matrix: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0):"
)

code = code.replace(
    "fig.suptitle(f'STRATEGIC MATCHUP: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.97, fontproperties=self.prop_title)",
    "fig.suptitle(f'STRATEGIC MATCHUP: {n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=18, y=0.97, fontproperties=self.prop_title)"
)

code = code.replace(
    "fig_m.suptitle(f'MATCHUP: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=16, y=0.985, fontproperties=self.prop_title)",
    "fig_m.suptitle(f'MATCHUP: {n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=16, y=0.985, fontproperties=self.prop_title)"
)

code = code.replace(
    "def draw_expectation_vs_actual(self, team_a: str, team_b: str, expected_delta: Dict, actual_delta: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel'):",
    "def draw_expectation_vs_actual(self, team_a: str, team_b: str, expected_delta: Dict, actual_delta: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0):"
)

# 2. Update StoryVisualizer
with open("Core/visualize_story.py", "r", encoding="utf-8") as f:
    story_code = f.read()

story_code = story_code.replace(
    "def draw_variance_map(self, team_a: str, team_b: str, variance_matrix: Dict[Tuple[str, str], float], \n                          expected_delta: Dict[Tuple[str, str], float], actual_delta: Dict[Tuple[str, str], float],",
    "def draw_variance_map(self, team_a: str, team_b: str, variance_matrix: Dict[TransitionEdge, float], \n                          expected_delta: Dict[TransitionEdge, float], actual_delta: Dict[TransitionEdge, float],"
)

story_code = story_code.replace(
    "expected_net: float, actual_net: float, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel'):",
    "expected_net: float, actual_net: float, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0):"
)

story_code = story_code.replace(
    "fig.suptitle(f'TACTICAL STORY: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.98, fontproperties=self.prop_title)",
    "fig.suptitle(f'TACTICAL STORY: {n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=18, y=0.98, fontproperties=self.prop_title)"
)

story_code = story_code.replace(
    "fig.text(0.5, title_y, f'TACTICAL STORY:\\n{n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=17, ha='center', va='center', fontproperties=self.prop_title)",
    "fig.text(0.5, title_y, f'TACTICAL STORY:\\n{n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=17, ha='center', va='center', fontproperties=self.prop_title)"
)

with open("Core/visualize_matchup.py", "w", encoding="utf-8") as f:
    f.write(code)

with open("Core/visualize_story.py", "w", encoding="utf-8") as f:
    f.write(story_code)

print("Updated visualizer scripts with ELO display logic.")
