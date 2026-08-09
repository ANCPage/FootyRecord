import matplotlib.patches as patches
from base_visualizer import BaseVisualizer
from engine_core import Graph


class FieldVisualizer(BaseVisualizer):
    def __init__(self):
        super().__init__()
        self.graph_helper = Graph("")
        self.node_positions = {
            'A1': (-60, 40),  'B1': (-30, 45),  'C1': (0, 50),   'D1': (30, 45),  'E1': (60, 40),
            'A2': (-70, 0),   'B2': (-35, 0),   'C2': (0, 0),    'D2': (35, 0),   'E2': (70, 0),
            'A3': (-60, -40), 'B3': (-30, -45), 'C3': (0, -50),  'D3': (30, -45), 'E3': (60, -40),
            'SCORE': (85, 0), 'AWAY_G': (-85, 0)
        }

        self.zone_labels = {
            'A1': 'LBP', 'B1': 'LHB', 'C1': 'LW', 'D1': 'LHF', 'E1': 'LFP',
            'A2': 'FB',  'B2': 'CHB', 'C2': 'C',  'D2': 'CHF', 'E2': 'FF',
            'A3': 'RBP', 'B3': 'RHB', 'C3': 'RW', 'D3': 'RHF', 'E3': 'RFP'
        }

    def draw_pitch(self, ax):
        """Draws the AFL oval pitch outline, center square, center circles, 50m arcs, and goals."""
        ax.set_facecolor(self.bg_color)
        oval = patches.Ellipse((0, 0), width=170, height=130, color=self.text_color, fill=False, linewidth=2)
        ax.add_patch(oval)
        center_sq = patches.Rectangle((-25, -25), 50, 50, color=self.text_color, fill=False, linewidth=1.5, alpha=0.5)
        ax.add_patch(center_sq)
        ax.add_patch(patches.Circle((0, 0), radius=5, color=self.text_color, fill=False, linewidth=1.5, alpha=0.5))
        ax.add_patch(patches.Circle((0, 0), radius=1.5, color=self.text_color, fill=False, linewidth=1.5, alpha=0.5))
        arc_right = patches.Arc((70, 0), 100, 100, theta1=90, theta2=270, color=self.text_color, linewidth=1.5, linestyle='--', alpha=0.4)
        ax.add_patch(arc_right)
        arc_left = patches.Arc((-70, 0), 100, 100, theta1=270, theta2=90, color=self.text_color, linewidth=1.5, linestyle='--', alpha=0.4)
        ax.add_patch(arc_left)
        ax.plot([85, 85], [-5, 5], color=self.text_color, linewidth=4)
        ax.plot([-85, -85], [-5, 5], color=self.text_color, linewidth=4)

    def draw_zones(self, ax, active_only: bool = False, active_nodes: set = None, font_scale: float = 1.0):
        """Draws circular labels for each grid zone onto the field."""
        for name, (x, y) in self.node_positions.items():
            if name in ['SCORE', 'AWAY_G']:
                continue
            if active_only and active_nodes and name not in active_nodes:
                continue
            ax.add_patch(patches.Circle((x, y), radius=3.5, color=self.bg_color, ec=self.sub_text_color, lw=1.5, zorder=2))
            ax.text(x, y, self.zone_labels.get(name, name), color=self.text_color, fontsize=8 * font_scale,
                    ha='center', va='center', zorder=3, fontproperties=self.prop_body, fontweight='bold')
