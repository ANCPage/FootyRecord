import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from typing import Dict, Tuple, List
from theme import get_ordinal
from mappings import TEAM_DATA
from field_visualizer import FieldVisualizer
from vector_renderer import VectorRenderer
from engine_core import home_favored

class MatchupVisualizer(FieldVisualizer):
    def __init__(self):
        super().__init__()
        self.vector_renderer = VectorRenderer(
            node_positions=self.node_positions,
            graph_helper=self.graph_helper,
            bg_color=self.bg_color,
            text_color=self.text_color,
            sub_text_color=self.sub_text_color,
            prop_body=self.prop_body
        )

    def _draw_field_on_ax(self, ax, title: str, matrix: Dict, target_edges: List, is_delta: bool, c_a: str, c_b: str, apply_blur: bool = False, frame: str = 'home'):
        self.draw_pitch(ax)
        self.draw_zones(ax)

        edges_to_plot = target_edges if target_edges else matrix.keys()
        for edge in edges_to_plot:
            score = matrix.get(edge, 0.0)
            if abs(score) < 0.01:
                continue 
            
            is_away_edge = score < 0
            color = (c_a if score > 0 else c_b) if is_delta else (c_a if score > 0 else '#ffaa00')
            
            self.vector_renderer.render_vector(
                ax=ax,
                edge=edge,
                score=score,
                color=color,
                is_away_edge=is_away_edge,
                apply_blur=apply_blur,
                show_label=bool(target_edges),
                frame=frame,
            )
        
        ax.set_title(title, color=self.text_color, fontsize=12, fontproperties=self.prop_sub)
        ax.set_xlim(-95, 95)
        ax.set_ylim(-75, 75)
        ax.axis('off')

    def _draw_table(self, ax, delta_matrix: Dict, team_a: str, team_b: str):
        ax.axis('off')
        n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
        n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']
        sorted_items = sorted(delta_matrix.items(), key=lambda x: abs(x[1]), reverse=True)[:20]
        
        def safe_label(n):
            return self.zone_labels.get(n, n)
        table_data = [[f'{safe_label(edge_obj.source)} -> {safe_label(edge_obj.target)}', f'{abs(v):.2f}', n_a if v > 0 else n_b] for edge_obj, v in sorted_items]
        
        table = ax.table(cellText=table_data, colLabels=['Vector', 'Advantage', 'Ownership'], loc='center', cellLoc='center', colWidths=[0.25, 0.25, 0.50])
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.4)
        
        for (row, col), cell in table.get_celld().items(): 
            if row == 0:
                cell.set_facecolor(self.text_color)
                cell.get_text().set_color(self.bg_color) 
                sub_font, sub_size = self.get_font_and_size(self.prop_sub, 8)
                cell.get_text().set_fontproperties(sub_font)
                cell.get_text().set_fontsize(sub_size)
            else:
                cell.set_facecolor(self.bg_color)
                cell.get_text().set_color(self.text_color)
                cell.get_text().set_fontproperties(self.prop_body)
                cell.get_text().set_fontsize(8)
            cell.set_edgecolor(self.sub_text_color)
            
        ax.set_title('TOP 20 TACTICAL BATTLES', color=self.text_color, fontsize=14, pad=40, fontproperties=self.prop_sub)

    def _add_color_key(self, fig, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a=None, rank_b=None, tier_a=None, tier_b=None, y_pos=0.05):
        fig.text(0.35, y_pos, n_a.upper(), color=self.text_color, fontsize=12, ha='right', va='center', fontproperties=self.prop_sub)
        rank_a_str = f"RANK: {get_ordinal(rank_a)}" if rank_a else ""
        tier_a_str = f" [{tier_a}]" if tier_a else ""
        fig.text(0.35, y_pos - 0.02, f"{rank_a_str}{tier_a_str} (Rating: {int(elo_a)})", color=self.sub_text_color, fontsize=8, ha='right', va='center', fontproperties=self.prop_body)
        
        fig.add_artist(patches.Rectangle((0.36, y_pos-0.008), 0.02, 0.016, color=c_a, transform=fig.transFigure))
        fig.text(0.5, y_pos, "VS", color=self.sub_text_color, fontsize=12, ha='center', va='center', fontproperties=self.prop_sub)
        
        fig.add_artist(patches.Rectangle((0.62, y_pos-0.008), 0.02, 0.016, color=c_b, transform=fig.transFigure))
        fig.text(0.65, y_pos, n_b.upper(), color=self.text_color, fontsize=12, ha='left', va='center', fontproperties=self.prop_sub)
        rank_b_str = f"RANK: {get_ordinal(rank_b)}" if rank_b else ""
        tier_b_str = f" [{tier_b}]" if tier_b else ""
        fig.text(0.65, y_pos - 0.02, f"{rank_b_str}{tier_b_str} (Rating: {int(elo_b)})", color=self.sub_text_color, fontsize=8, ha='left', va='center', fontproperties=self.prop_body)

    def draw_full_matchup(self, team_a: str, team_b: str, matrix_a: Dict, matrix_b: Dict, delta_matrix: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None):
        n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
        n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']
        c_a, c_b = self.get_team_colors(team_a, team_b)
        net_delta = sum(delta_matrix.values())
        winner_name = n_a if home_favored(net_delta, elo_a, elo_b) else n_b
        target_edges = [e for e, s in sorted(delta_matrix.items(), key=lambda x: abs(x[1]), reverse=True)[:20]]
        
        for suffix, edges, blur in [('', target_edges, False)]:
            if not is_mobile:
                fig = plt.figure(figsize=(20, 14), facecolor=self.bg_color)
                gs = fig.add_gridspec(2, 3, height_ratios=[1, 1.2])
                try:
                    ax1 = fig.add_subplot(gs[0, 0])
                    ax2 = fig.add_subplot(gs[0, 1])
                    ax3 = fig.add_subplot(gs[1, :2])
                    ax_t = fig.add_subplot(gs[0, 2])
                    
                    self._draw_field_on_ax(ax1, f'{n_a.upper()} PROFILE', matrix_a, edges, False, c_a, c_a, apply_blur=blur)
                    self._draw_field_on_ax(ax2, f'{n_b.upper()} PROFILE', matrix_b, edges, False, c_b, c_b, apply_blur=blur, frame='team')
                    self._draw_field_on_ax(ax3, f'ABSOLUTE MATCHUP OWNERSHIP', delta_matrix, edges, True, c_a, c_b, apply_blur=blur)
                    self._draw_table(ax_t, delta_matrix, team_a, team_b)
                    
                    fig.suptitle(f'STRATEGIC MATCHUP: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.97, fontproperties=self.prop_title)
                    self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.06)
                    plt.figtext(0.5, 0.02, f'MATCHUP SCORE: {net_delta:+.2f}  |  PREDICTED WINNER: {winner_name.upper()}', ha='center', fontsize=18, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':12}, fontproperties=self.prop_sub)
                    
                    self.save_and_close(fig, f'{save_prefix}{suffix}.png', dpi=100)
                except:
                    plt.close(fig)
                    raise
            else:
                figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
                fig_m = plt.figure(figsize=figsize, facecolor=self.bg_color)
                gs_m = fig_m.add_gridspec(4, 1, height_ratios=[1, 1, 1, 1.6])
                try:
                    ax1_m = fig_m.add_subplot(gs_m[0, 0])
                    ax2_m = fig_m.add_subplot(gs_m[1, 0])
                    ax3_m = fig_m.add_subplot(gs_m[2, 0])
                    ax_tm = fig_m.add_subplot(gs_m[3, 0])
                    
                    self._draw_field_on_ax(ax1_m, f'{n_a.upper()} PROFILE', matrix_a, edges, False, c_a, c_a, apply_blur=blur)
                    self._draw_field_on_ax(ax2_m, f'{n_b.upper()} PROFILE', matrix_b, edges, False, c_b, c_b, apply_blur=blur, frame='team')
                    self._draw_field_on_ax(ax3_m, f'ABSOLUTE MATCHUP OWNERSHIP', delta_matrix, edges, True, c_a, c_b, apply_blur=blur)
                    self._draw_table(ax_tm, delta_matrix, team_a, team_b)
                    
                    fig_m.suptitle(f'MATCHUP: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=16, y=0.985, fontproperties=self.prop_title)
                    self._add_color_key(fig_m, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.06)
                    plt.figtext(0.5, 0.02, f'WINNER: {winner_name.upper()} ({net_delta:+.2f})', ha='center', fontsize=16, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':8}, fontproperties=self.prop_sub)
                    plt.tight_layout(rect=[0.05, 0.12, 0.95, 0.95])
                    
                    self.save_and_close(fig_m, f'{save_prefix}{suffix}.png', dpi=100)
                except:
                    plt.close(fig_m)
                    raise

    def draw_expectation_vs_actual(self, team_a: str, team_b: str, expected_delta: Dict, actual_delta: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None):
        n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
        n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']
        c_a, c_b = self.get_team_colors(team_a, team_b)
        
        net_expected = sum(expected_delta.values())
        net_actual = sum(actual_delta.values())
        
        target_edges_exp = [e for e, s in sorted(expected_delta.items(), key=lambda x: abs(x[1]), reverse=True)[:20]]
        target_edges_act = [e for e, s in sorted(actual_delta.items(), key=lambda x: abs(x[1]), reverse=True)[:20]]
        
        for suffix, e_exp, e_act, blur in [('', target_edges_exp, target_edges_act, False)]:
            if not is_mobile:
                fig = plt.figure(figsize=(20, 10), facecolor=self.bg_color)
                try:
                    gs = fig.add_gridspec(1, 2)
                    ax1 = fig.add_subplot(gs[0, 0])
                    ax2 = fig.add_subplot(gs[0, 1])
                    
                    self._draw_field_on_ax(ax1, 'EXPECTED TACTICAL DELTA', expected_delta, e_exp, True, c_a, c_b, apply_blur=blur)
                    self._draw_field_on_ax(ax2, 'ACTUAL TACTICAL DELTA', actual_delta, e_act, True, c_a, c_b, apply_blur=blur)
                    
                    fig.suptitle(f'EXPECTATION VS ACTUAL: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.95, fontproperties=self.prop_title)
                    self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.08)
                    
                    plt.figtext(0.3, 0.02, f'PREDICTED SCORE: {net_expected:+.2f}', ha='center', fontsize=18, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':12}, fontproperties=self.prop_sub)
                    plt.figtext(0.7, 0.02, f'ACTUAL SCORE: {net_actual:+.2f}', ha='center', fontsize=18, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':12}, fontproperties=self.prop_sub)
                    
                    self.save_and_close(fig, f'{save_prefix}_expectation_vs_actual{suffix}.png', dpi=100)
                except:
                    plt.close(fig)
                    raise
            else:
                figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
                fig_m = plt.figure(figsize=figsize, facecolor=self.bg_color)
                try:
                    gs_m = fig_m.add_gridspec(2, 1)
                    ax1_m = fig_m.add_subplot(gs_m[0, 0])
                    ax2_m = fig_m.add_subplot(gs_m[1, 0])
                    
                    self._draw_field_on_ax(ax1_m, 'EXPECTED TACTICAL DELTA', expected_delta, e_exp, True, c_a, c_b, apply_blur=blur)
                    self._draw_field_on_ax(ax2_m, 'ACTUAL TACTICAL DELTA', actual_delta, e_act, True, c_a, c_b, apply_blur=blur)
                    
                    fig_m.suptitle(f'EXPECTATION VS ACTUAL:\n{n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=16, y=0.98, fontproperties=self.prop_title)
                    self._add_color_key(fig_m, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.06)
                    
                    plt.figtext(0.5, 0.01, f'ACTUAL SCORE: {net_actual:+.2f}', ha='center', fontsize=16, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':8}, fontproperties=self.prop_sub)
                    plt.tight_layout(rect=[0.02, 0.10, 0.98, 0.94])
                    
                    self.save_and_close(fig_m, f'{save_prefix}_expectation_vs_actual{suffix}.png', dpi=100)
                except:
                    plt.close(fig_m)
                    raise
