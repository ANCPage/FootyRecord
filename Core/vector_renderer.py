from typing import Dict, Tuple

from Core.engine_core import Graph, physical_placement
from Core.models import TransitionEdge


class VectorRenderer:
    def __init__(self, node_positions: Dict[str, Tuple[float, float]], graph_helper: Graph,
                 bg_color: str, text_color: str, sub_text_color: str, prop_body):
        self.node_positions = node_positions
        self.graph_helper = graph_helper
        self.bg_color = bg_color
        self.text_color = text_color
        self.sub_text_color = sub_text_color
        self.prop_body = prop_body

    def render_vector(self, ax, edge: TransitionEdge, score: float, color: str,
                      is_away_edge: bool = False, apply_blur: bool = False,
                      arrow_style: str = None, show_label: bool = True, max_lw: float = 12.0,
                      frame: str = 'home'):
        start, end = edge.source, edge.target

        # Placement math lives in engine_core.physical_placement (pure function,
        # regression-tested in tests/test_placement.py — the LFP->FB fix).
        phys_start, phys_end = physical_placement(start, end, is_away_edge, frame)

        p1 = self.node_positions.get(phys_start)
        p2 = self.node_positions.get(phys_end)
        if not p1 or not p2:
            return

        lw = min(max_lw, max(3, abs(score) * 2.0))
        if end == 'SCORE' or phys_end == 'AWAY_G':
            lw *= 0.7

        if arrow_style is None:
            arrow_style = '->,head_width=0.6,head_length=0.8'

        if apply_blur:
            for b_step in range(1, 6):
                ax.annotate('', xy=p2, xytext=p1,
                            arrowprops=dict(arrowstyle='-', color=color, lw=lw + b_step*4,
                                            alpha=0.04, connectionstyle='arc3,rad=0.15', shrinkB=5),
                            zorder=0)

        ax.annotate('', xy=p2, xytext=p1,
                    arrowprops=dict(arrowstyle=arrow_style, color=color, lw=lw,
                                    alpha=0.6 if apply_blur else 0.85,
                                    connectionstyle='arc3,rad=0.15', shrinkB=12 if '->' in arrow_style else 15,
                                    shrinkA=12 if '->' in arrow_style else 15),
                    zorder=1)

        if show_label and not apply_blur:
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = (dx**2 + dy**2)**0.5 if (dx**2 + dy**2) > 0 else 1
            px, py = -dy / length, dx / length
            offset = 6 + (lw * 0.4)
            mid_x = (p1[0] + p2[0]) / 2 + (px * offset)
            mid_y = (p1[1] + p2[1]) / 2 + (py * offset)
            ax.text(mid_x, mid_y, f'{score:+.2f}', color=self.text_color, fontsize=8,
                    ha='center', va='center',
                    bbox=dict(facecolor=self.bg_color, alpha=0.8, edgecolor=color, lw=1, pad=2, boxstyle='round,pad=0.2'),
                    zorder=4, fontproperties=self.prop_body)
