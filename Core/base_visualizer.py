import matplotlib

matplotlib.use('Agg')
from typing import Optional, Tuple

import matplotlib.pyplot as plt
from mappings import TEAM_DATA
from matplotlib.font_manager import FontProperties
from theme import BG_COLOR, SUB_TEXT_COLOR, TEXT_COLOR, get_fonts, is_dark_color, mute_color


class BaseVisualizer:
    def __init__(self):
        self.bg_color = BG_COLOR
        self.text_color = TEXT_COLOR
        self.sub_text_color = SUB_TEXT_COLOR
        self.prop_title, self.prop_sub, self.prop_body = get_fonts()

    def get_font_and_size(self, font: FontProperties, size: float) -> Tuple[FontProperties, float]:
        """Wallpoet size fallback: if the font is Wallpoet (prop_sub) and size is < 12, fall back to Roboto (prop_body)."""
        if font == self.prop_sub and size < 12:
            return self.prop_body, size
        return font, size

    def get_team_colors(self, team_a_id: str, team_b_id: str) -> Tuple[str, str]:
        """Resolves readable contrast colors for two teams using centralized darkness check."""
        d_a = TEAM_DATA.get(team_a_id, {'primary': '#333333', 'secondary': '#dddddd'})
        d_b = TEAM_DATA.get(team_b_id, {'primary': '#555555', 'secondary': '#eeeeee'})

        c_a = d_a['primary']
        if not is_dark_color(c_a):
            c_a = d_a['secondary']
            if not is_dark_color(c_a):
                c_a = '#B22222'

        c_b = d_b['primary']
        if not is_dark_color(c_b) or c_a == c_b:
            c_b = d_b['secondary']
            if not is_dark_color(c_b) or c_a == c_b:
                c_b = '#004B87'

        return mute_color(c_a), mute_color(c_b)

    def create_canvas(self, is_mobile: bool = False, mobile_format: str = 'reel', default_desktop_size: Tuple[float, float] = (16, 10)) -> Tuple[plt.Figure, plt.Axes]:
        """Centralizes figure and canvas creation."""
        if is_mobile:
            figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
        else:
            figsize = default_desktop_size
        fig, ax = plt.subplots(figsize=figsize, facecolor=self.bg_color)
        ax.set_facecolor(self.bg_color)
        return fig, ax

    def save_and_close(self, fig: plt.Figure, path: str, dpi: int = 120, bbox_inches: Optional[str] = None) -> None:
        """Safely saves the figure and cleans up Matplotlib resources.

        bbox_inches=None (default): the figure renders at its declared figsize —
        fixed aspect. 'tight' crops to content (was collapsing chart heights
        inconsistently across teams, fixed 2026-08-10)."""
        try:
            fig.savefig(path, facecolor=self.bg_color, dpi=dpi, bbox_inches=bbox_inches)
        finally:
            plt.close(fig)
