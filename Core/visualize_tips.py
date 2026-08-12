import matplotlib

matplotlib.use('Agg')
from typing import Any, Dict, List

import matplotlib.patches as patches
import matplotlib.pyplot as plt

from Core.base_visualizer import BaseVisualizer
from Core.mappings import TEAM_DATA, get_short_name
from Core.theme import mute_color


class TipsVisualizer(BaseVisualizer):
    def __init__(self):
        super().__init__()
        # Standard table styling fields
        self.header_bg = '#3E3A35'
        self.header_text = '#F4F1EA'

    def _get_confidence_grade(self, edge: float) -> str:
        """Confidence grade from the predicted margin (shared ladder — see
        calibration.confidence_grade)."""
        from Core.calibration import confidence_grade
        return confidence_grade(edge)

    def _get_confidence_color(self, grade: str) -> str:
        if 'A' in grade: return '#228B22' # Forest Green
        if 'B' in grade: return '#4A7A59' # Muted Green
        if 'C' in grade: return '#DAA520' # Goldenrod
        if 'D' in grade: return '#CD853F' # Peru/Orange
        if 'E' in grade: return '#A8463D' # Muted Red
        return '#8B0000' # Dark Red

    def draw_round_tips(self, round_num: int, season: int, tips: List[Dict[str, Any]], save_path: str, is_mobile: bool = False, mobile_format: str = 'reel', show_results: bool = False, season_summary: str = ""):
        if is_mobile:
            figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
        else:
            figsize = (14, 10)
        fig, ax = plt.subplots(figsize=figsize, facecolor=self.bg_color)
        try:
            ax.set_facecolor(self.bg_color)
            ax.axis('off')

            title_fs = 20 if not is_mobile else 18
            sub_fs = 14 if not is_mobile else 12
            row_fs = 12 if not is_mobile else 11

            sub_font, sub_fs = self.get_font_and_size(self.prop_sub, sub_fs)
            row_sub_font, row_fs = self.get_font_and_size(self.prop_sub, row_fs)

            title_str = f'ROUND {round_num} TACTICAL TIPS' if not show_results else f'ROUND {round_num} TIPS RESULTS'
            sub_str = f'SEASON {season} | SIMULATED MATCHUP CONFIDENCE' if not show_results else f'SEASON {season} | {season_summary}'

            plt.text(0.5, 0.96, title_str, ha='center', va='center', fontsize=title_fs, color=self.text_color, fontproperties=self.prop_title)
            plt.text(0.5, 0.90, sub_str, ha='center', va='center', fontsize=sub_fs, color=self.sub_text_color, fontproperties=sub_font)

            start_y = 0.84
            row_height = 0.07 if not is_mobile else 0.08
            header_y = start_y
            rect = patches.Rectangle((0.05, header_y - 0.02), 0.9, 0.04, facecolor=self.header_bg, zorder=1)
            ax.add_patch(rect)

            col_x = [0.12, 0.38, 0.68, 0.88]
            cols = ['GAME', 'MATCHUP', 'PREDICTED WINNER', 'CONFIDENCE' if not show_results else 'RESULT']

            for x, col in zip(col_x, cols):
                plt.text(x, header_y, col, ha='center', va='center', color=self.header_text, fontsize=row_fs, zorder=2, fontproperties=row_sub_font)

            for i, tip in enumerate(tips):
                curr_y = header_y - (i + 1) * row_height
                if i % 2 == 1:
                    rect = patches.Rectangle((0.05, curr_y - row_height/2), 0.9, row_height, facecolor=self.sub_text_color, alpha=0.05, zorder=0)
                    ax.add_patch(rect)

                plt.text(col_x[0], curr_y, f'G{i+1}', ha='center', va='center', color=self.text_color, fontsize=row_fs, fontproperties=row_sub_font)

                h_name = tip['home_name']
                a_name = tip['away_name']
                matchup_str = f'{h_name} vs {a_name}'
                if is_mobile and len(matchup_str) > 22:
                    h_short = get_short_name(h_name)
                    a_short = get_short_name(a_name)
                    matchup_str = f'{h_short} vs {a_short}'

                plt.text(col_x[1], curr_y, matchup_str, ha='center', va='center', color=self.text_color, fontsize=row_fs, fontproperties=self.prop_body)

                winner_id = tip['winner_id']
                winner_name = TEAM_DATA.get(winner_id, {'name': winner_id})['name']
                w_color = mute_color(TEAM_DATA.get(winner_id, {'primary': '#333333'})['primary'])

                fig_w, fig_h = figsize
                0.22 / fig_w
                0.038 / fig_h

                # Winner Card
                rect = patches.FancyBboxPatch(
                    (col_x[2] - 0.11, curr_y - 0.018), 0.22, 0.036,
                    boxstyle="round,pad=0.002,rounding_size=0.015",
                    facecolor=w_color, edgecolor=self.text_color, lw=1.2, zorder=1
                )
                ax.add_patch(rect)

                winner_label = winner_name.upper()
                if is_mobile and len(winner_label) > 12:
                    winner_label = get_short_name(winner_name).upper()

                plt.text(col_x[2], curr_y, winner_label, ha='center', va='center', color=self.header_text, fontsize=row_fs, fontweight='bold', zorder=2, fontproperties=row_sub_font)

                if not show_results:
                    grade = self._get_confidence_grade(tip['edge'])
                    c_color = self._get_confidence_color(grade)

                    circle = patches.Circle((col_x[3], curr_y), radius=0.016, facecolor=c_color, edgecolor=self.text_color, lw=1.2, zorder=1)
                    ax.add_patch(circle)
                    plt.text(col_x[3], curr_y, grade, ha='center', va='center', color=self.header_text, fontsize=row_fs - 1, fontweight='bold', zorder=2, fontproperties=row_sub_font)
                else:
                    actual_winner = tip.get('actual_winner')
                    is_correct = (actual_winner == winner_id)
                    res_str = 'CORRECT' if is_correct else 'INCORRECT'
                    if actual_winner == 'DRAW':
                        res_str = 'DRAW'
                    res_color = '#228B22' if is_correct else '#A8463D'
                    if actual_winner == 'DRAW':
                        res_color = '#DAA520'

                    plt.text(col_x[3], curr_y, res_str, ha='center', va='center', color=res_color, fontsize=row_fs, fontweight='bold', fontproperties=row_sub_font)

            plt.tight_layout()
            self.save_and_close(fig, save_path, dpi=120 if not is_mobile else 100, bbox_inches='tight')
        except:
            plt.close(fig)
            raise
