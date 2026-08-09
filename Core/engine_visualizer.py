import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from typing import Dict, Tuple
from mappings import TEAM_DATA

class TacticalHUD:
    def __init__(self):
        self.node_positions = {
            'A1': (-60, 40),  'B1': (-30, 45),  'C1': (0, 50),   'D1': (30, 45),  'E1': (60, 40),
            'A2': (-70, 0),   'B2': (-35, 0),   'C2': (0, 0),    'D2': (35, 0),   'E2': (70, 0),
            'A3': (-60, -40), 'B3': (-30, -45), 'C3': (0, -50),  'D3': (30, -45), 'E3': (60, -40),
            'SCORE': (85, 0), 'AWAY_G': (-85, 0)
        }

    def _get_team_color(self, team_id, opponent_id=None):
        data = TEAM_DATA.get(team_id, {'primary': '#ffffff', 'secondary': '#888888'})
        if not opponent_id: return data['primary'], data['secondary']
        opp_data = TEAM_DATA.get(opponent_id, {'primary': '#ffffff', 'secondary': '#888888'})
        if data['primary'].lower() == opp_data['primary'].lower(): return data['secondary'], data['primary']
        return data['primary'], data['secondary']

    def draw_matchup(self, team_a: str, team_b: str, delta_matrix: Dict[Tuple[str, str], float]):
        plt.style.use('dark_background')
        name_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
        name_b = TEAM_DATA.get(team_b, {'name': team_b})['name']
        c_a_prim, c_a_sec = self._get_team_color(team_a, team_b)
        c_b_prim, c_b_sec = self._get_team_color(team_b, team_a)
        
        fig, ax = plt.subplots(figsize=(14, 9)); ax.set_facecolor('#0a0a0a')
        oval = patches.Ellipse((0, 0), width=170, height=130, color='#00ffff', fill=False, linewidth=2, alpha=0.3)
        ax.add_patch(oval)
        for x in range(-80, 81, 20): ax.plot([x, x], [-60, 60], color='#222222', lw=0.5, zorder=0)
        for y in range(-60, 61, 20): ax.plot([-80, 80], [y, y], color='#222222', lw=0.5, zorder=0)
        
        pos_deltas = {}
        for (start, end), score in delta_matrix.items(): pos_deltas[start] = pos_deltas.get(start, 0.0) + score

        for name, (x, y) in self.node_positions.items():
            if name in ['SCORE', 'AWAY_G']: continue
            val = pos_deltas.get(name, 0.0)
            color = c_a_prim if val > 0 else c_b_prim
            alpha = min(1.0, abs(val) / 5.0) if val != 0 else 0.1
            ax.add_patch(patches.Circle((x, y), radius=4, color=color, alpha=alpha, zorder=2))
            ax.text(x, y, name, color='white', fontsize=8, ha='center', va='center', zorder=3)

        sorted_edges = sorted(delta_matrix.items(), key=lambda x: abs(x[1]), reverse=True)
        for (start, end), score in sorted_edges[:12]:
            if abs(score) < 0.2: continue
            p1 = self.node_positions.get(start); target = end
            if end == 'SCORE' and score < 0: target = 'AWAY_G'
            p2 = self.node_positions.get(target)
            if not p1 or not p2: continue
            color = c_a_prim if score > 0 else c_b_prim; linewidth = min(5, abs(score) * 1.5)
            ax.annotate('', xy=p2, xytext=p1, arrowprops=dict(arrowstyle='->,head_width=0.4,head_length=0.6', color=color, lw=linewidth, alpha=0.7, connectionstyle='arc3,rad=0.15', shrinkB=5), zorder=1)
            ax.text((p1[0]+p2[0])/2, (p1[1]+p2[1])/2 + 5, f'{score:+.2f}', color=color, fontsize=9, fontweight='bold', ha='center')

        plt.title(f'TACTICAL OVERLAY: {name_a} vs {name_b}', color='white', fontsize=16, pad=20)
        ax.set_xlim(-95, 95); ax.set_ylim(-75, 75); ax.axis('off')
        net_delta = sum(delta_matrix.values()); winner_id = team_a if net_delta > 0 else team_b; winner_name = TEAM_DATA.get(winner_id, {'name': winner_id})['name']
        plt.figtext(0.5, 0.05, f'PREDICTED WINNER: {winner_name} | NET MATCHUP DELTA: {net_delta:+.2f}', ha='center', fontsize=14, color='white', bbox={'facecolor':'#333333', 'alpha':0.5, 'pad':5})
        plt.savefig('matchup_analysis_single.png', bbox_inches='tight', dpi=150); plt.close()
