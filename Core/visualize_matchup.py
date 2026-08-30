import matplotlib

matplotlib.use('Agg')
from typing import Dict, List

import matplotlib.patches as patches
import matplotlib.pyplot as plt

from Core.engine_core import home_favored
from Core.field_visualizer import FieldVisualizer
from Core.mappings import TEAM_DATA
from Core.theme import get_ordinal
from Core.vector_renderer import VectorRenderer


def _fallback_cal():
    """Shipped coefficients when no calibration is threaded in (Phase 1)."""
    from Core.calibration import Calibration
    return Calibration.fallback()


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

    def _draw_field_on_ax(self, ax, title: str, matrix: Dict, target_edges: List, is_delta: bool, c_a: str, c_b: str, apply_blur: bool = False, frame: str = 'home', active_zones: bool = False):
        self.draw_pitch(ax)
        if active_zones:
            involved = set()
            for e in (target_edges or matrix.keys()):
                involved.add(e.source); involved.add(e.target)
            self.draw_zones(ax, active_only=True, active_nodes={z for z in involved if z in self.zone_labels})
        else:
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

        if title:
            t_font, t_size = self.get_font_and_size(self.prop_sub, 11)
            ax.set_title(title, color=self.text_color, fontsize=t_size, fontproperties=t_font)
        ax.set_xlim(-95, 95)
        ax.set_ylim(-75, 75)
        ax.set_aspect('equal')  # keep the 170x130 oval round at any figure size
        ax.axis('off')

    def _draw_table(self, ax, delta_matrix: Dict, team_a: str, team_b: str, limit: int = 20):
        ax.axis('off')
        n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
        n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']
        sorted_items = sorted(delta_matrix.items(), key=lambda x: abs(x[1]), reverse=True)[:limit]

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

        t_font, t_size = self.get_font_and_size(self.prop_sub, 14)
        ax.set_title(f'TOP {limit} TACTICAL BATTLES', color=self.text_color, fontsize=t_size, pad=40, fontproperties=t_font)

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

    def draw_full_matchup(self, team_a: str, team_b: str, matrix_a: Dict, matrix_b: Dict, delta_matrix: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None, calibration=None):
        n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
        n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']
        c_a, c_b = self.get_team_colors(team_a, team_b)
        net_delta = sum(delta_matrix.values())
        # Phase 1: calibration passed in by the caller (was a module global)
        cal = calibration or _fallback_cal()
        margin = cal.margin(net_delta, (elo_a - elo_b) / 100.0)  # the one calibrated output
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
                    self._draw_field_on_ax(ax3, 'ABSOLUTE MATCHUP OWNERSHIP', delta_matrix, edges, True, c_a, c_b, apply_blur=blur)
                    self._draw_table(ax_t, delta_matrix, team_a, team_b)

                    fig.suptitle(f'STRATEGIC MATCHUP: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.97, fontproperties=self.prop_title)
                    self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, rank_a, rank_b, tier_a, tier_b, y_pos=0.06)
                    plt.figtext(0.5, 0.02, f'PREDICTED MARGIN: {margin:+.0f} PTS  |  PREDICTED WINNER: {winner_name.upper()}', ha='center', fontsize=18, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':12}, fontproperties=self.prop_sub)

                    self.save_and_close(fig, f'{save_prefix}{suffix}.png', dpi=100)
                except:
                    plt.close(fig)
                    raise
            else:
                # OPTION A mobile layout (2026-08-26): masthead, one round field,
                # battles table, winner banner. Post-only 9x12.
                figsize = (9, 12) if mobile_format == 'reel' else (9, 12)
                fig_m = plt.figure(figsize=figsize, facecolor=self.bg_color)
                try:
                    fig_m.text(0.5, 0.955, 'MATCHUP', ha='center', fontsize=34, color=self.text_color, fontproperties=self.prop_title)
                    fig_m.text(0.5, 0.915, f'{n_a.upper()}  VS  {n_b.upper()}', ha='center', fontsize=15, color=self.sub_text_color)
                    rank_a_str = f"RANK {rank_a} [{tier_a}]" if rank_a else ''
                    rank_b_str = f"RANK {rank_b} [{tier_b}]" if rank_b else ''
                    fig_m.text(0.5, 0.888, f'{n_a} — {rank_a_str}   ·   {n_b} — {rank_b_str}', ha='center', fontsize=10.5, color=self.sub_text_color)

                    # one ownership field: axes sized to the 190:150 data ratio so the
                    # round oval FILLS the panel (equal aspect, no letterbox gutters)
                    top_edges = [e for e, s in sorted(delta_matrix.items(), key=lambda x: abs(x[1]), reverse=True)[:6]]
                    ax3_m = fig_m.add_axes([0.16, 0.35, 0.68, 0.52])
                    self._draw_field_on_ax(ax3_m, '', delta_matrix, top_edges, True, c_a, c_b, apply_blur=False, active_zones=True)

                    ax_tm = fig_m.add_axes([0.06, 0.10, 0.88, 0.24])
                    self._draw_table(ax_tm, delta_matrix, team_a, team_b, limit=10)

                    # winner banner (A style): FasterOne headline + Roboto sub
                    fig_m.add_artist(patches.Rectangle((0.03, 0.035), 0.94, 0.06, facecolor=self.text_color, edgecolor='none', zorder=5))
                    fig_m.text(0.5, 0.071, f'{winner_name.upper()} WINNER', ha='center', va='center', fontsize=20, color=self.bg_color, zorder=6, fontproperties=self.prop_title)
                    fig_m.text(0.5, 0.047, f'MARGIN {margin:+.0f} PTS  ·  NET DELTA {net_delta:+.2f}', ha='center', va='center', fontsize=10, color=self.bg_color, zorder=6)

                    self.save_and_close(fig_m, f'{save_prefix}{suffix}.png', dpi=100)
                except:
                    plt.close(fig_m)
                    raise

    def draw_expectation_vs_actual(self, team_a: str, team_b: str, expected_delta: Dict, actual_delta: Dict, save_prefix: str = 'matchup_analysis', is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None, actual_margin: float = None, calibration=None):
        n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
        n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']
        c_a, c_b = self.get_team_colors(team_a, team_b)

        net_expected = sum(expected_delta.values())
        net_actual = sum(actual_delta.values())
        cal = calibration or _fallback_cal()   # Phase 1: passed in, not global
        expected_margin = cal.margin(net_expected, (elo_a - elo_b) / 100.0)
        if actual_margin is None:
            actual_margin = net_actual

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

                    plt.figtext(0.3, 0.02, f'PREDICTED MARGIN: {expected_margin:+.0f}', ha='center', fontsize=18, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':12}, fontproperties=self.prop_sub)
                    plt.figtext(0.7, 0.02, f'ACTUAL MARGIN: {actual_margin:+.0f}', ha='center', fontsize=18, color=self.bg_color, bbox={'facecolor':self.text_color, 'alpha':1.0, 'pad':12}, fontproperties=self.prop_sub)

                    self.save_and_close(fig, f'{save_prefix}_expectation_vs_actual{suffix}.png', dpi=100)
                except:
                    plt.close(fig)
                    raise
            else:
                # OPTION A mobile layout (2026-08-26): masthead, two stacked fields,
                # predicted vs actual margin banner.
                figsize = (9, 12) if mobile_format == 'reel' else (9, 12)
                fig_m = plt.figure(figsize=figsize, facecolor=self.bg_color)
                try:
                    fig_m.text(0.5, 0.955, 'EXPECTATION', ha='center', fontsize=32, color=self.text_color, fontproperties=self.prop_title)
                    fig_m.text(0.5, 0.918, f'{n_a.upper()}  VS  {n_b.upper()}', ha='center', fontsize=15, color=self.sub_text_color)

                    # two stacked round fields, boxes sized to the 190:150 data ratio
                    # so each oval FILLS its panel under equal aspect (no gutters, no
                    # dead bands — fixes the side-by-side layout's empty lower half)
                    lbl_font, lbl_size = self.get_font_and_size(self.prop_sub, 12)
                    fig_m.text(0.5, 0.895, 'EXPECTED', ha='center', fontsize=lbl_size, color=self.sub_text_color, fontproperties=lbl_font)
                    ax1_m = fig_m.add_axes([0.24, 0.52, 0.52, 0.355])
                    self._draw_field_on_ax(ax1_m, '', expected_delta, e_exp[:8], True, c_a, c_b, apply_blur=blur, active_zones=True)
                    fig_m.text(0.5, 0.505, 'ACTUAL', ha='center', fontsize=lbl_size, color=self.sub_text_color, fontproperties=lbl_font)
                    ax2_m = fig_m.add_axes([0.24, 0.135, 0.52, 0.355])
                    self._draw_field_on_ax(ax2_m, '', actual_delta, e_act[:8], True, c_a, c_b, apply_blur=blur, active_zones=True)

                    # A-style banner: predicted vs actual margin
                    fig_m.add_artist(patches.Rectangle((0.03, 0.035), 0.94, 0.06, facecolor=self.text_color, edgecolor='none', zorder=5))
                    fig_m.text(0.5, 0.071, f'PREDICTED MARGIN {expected_margin:+.0f}', ha='center', va='center', fontsize=18, color=self.bg_color, zorder=6, fontproperties=self.prop_title)
                    fig_m.text(0.5, 0.047, f'ACTUAL MARGIN {actual_margin:+.0f}', ha='center', va='center', fontsize=10.5, color=self.bg_color, zorder=6)

                    self.save_and_close(fig_m, f'{save_prefix}_expectation_vs_actual{suffix}.png', dpi=100)
                except:
                    plt.close(fig_m)
                    raise


    def draw_fingerprint(self, team_a: str, team_b: str, matrix_a: Dict,
                         matrix_b: Dict, season: int, round_num: int,
                         save_path: str, single: bool = False,
                         net_a: float = None, net_b: float = None,
                         delta: Dict = None):
        """Team fingerprint(s) as a whorl card (2026-08-30, Austin's idea).

        Geometry is REAL data, not decoration:
          angle  = the edge's ground bearing (column A..E, row offset)
          radius = depth from the goal (E-row innermost, A-row outermost;
                   the GOAL is the centre)
          width  = |weight|          colour = sign (teal = A/own, terracotta = B/conceded)

        Overlay mode shows the DELTA (A wins edge = teal, B wins = terracotta),
        because fingerprints are E2-normalised: size is meaningless, balance
        decides. The verdict banner reads sign(net_a - net_b) — the same
        number the engine tips on.
        """
        import math


        fig = plt.figure(figsize=(9, 12), facecolor=self.bg_color)
        try:
            TEAL, TERRA = '#1F6F6B', '#C1553A'
            a_name = TEAM_DATA.get(team_a, {}).get('name', team_a)
            b_name = TEAM_DATA.get(team_b, {}).get('name', team_b) if team_b else None

            # ---- masthead
            fig.text(0.5, 0.955, 'FINGERPRINT', ha='center', fontsize=30,
                     color=self.text_color, fontproperties=self.prop_title)
            sub = (f'SEASON {season} · THROUGH R{round_num}'
                   + (f' · {a_name.upper()} vs {b_name.upper()}' if not single
                      else f' · {a_name.upper()}'))
            fig.text(0.5, 0.924, sub, ha='center', fontsize=12,
                     color=self.sub_text_color)

            ax = fig.add_axes([0.06, 0.10, 0.88, 0.80])
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect('equal')
            ax.axis('off')
            cx, cy, R = 0.5, 0.52, 0.40

            # ---- node positions: radius = depth from goal, angle = bearing
            from Core.geometry import GRID_NAMES
            pos = {}
            for r_i, row in enumerate(GRID_NAMES):
                for c_i, name in enumerate(row):
                    radius = R * (0.14 + 0.82 * (4 - r_i) / 4.0)
                    angle = math.radians(90 + (c_i - 2) * 34 + (1 - 1) * 0)
                    pos[name] = (cx + radius * math.cos(angle),
                                 cy + radius * math.sin(angle))
            pos['SCORE'] = (cx, cy)

            # ---- paper texture: concentric rings + spokes
            for r_i in range(5):
                rr = R * (0.14 + 0.82 * (4 - r_i) / 4.0)
                circ = patches.Circle((cx, cy), rr, fill=False,
                                      edgecolor='#E3DCCB', lw=1.2, zorder=1)
                ax.add_patch(circ)
            for c_i in range(5):
                ang = math.radians(90 + (c_i - 2) * 34)
                ax.plot([cx + 0.02 * math.cos(ang), cx + R * math.cos(ang)],
                        [cy + 0.02 * math.sin(ang), cy + R * math.sin(ang)],
                        color='#EAE4D5', lw=1.0, zorder=1)

            # ---- which edges to draw
            if single:
                edges = dict(matrix_a)
                edges = {k: v for k, v in edges.items()
                         if abs(v) > 0.02 * max((abs(x) for x in edges.values()), default=0)}
                maxw = max((abs(v) for v in edges.values()), default=0.0)
                net = net_a if net_a is not None else sum(matrix_a.values())
            else:
                edges = {k: v for k, v in (delta or {}).items()
                         if abs(v) > 0.02 * max((abs(x) for x in (delta or {}).values()), default=0)}
                maxw = max((abs(v) for v in edges.values()), default=0.0)
                net = (net_a or 0.0) - (net_b or 0.0)

            def sample_quad(p0, p1, p2, n=42):
                pts = []
                for i in range(n + 1):
                    t = i / n
                    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
                    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
                    pts.append((x, y))
                return pts

            def offset_curve(pts, dist):
                out = []
                for i, (x, y) in enumerate(pts):
                    dx = pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0]
                    dy = pts[min(i + 1, len(pts) - 1)][1] - pts[max(i - 1, 0)][1]
                    L = math.hypot(dx, dy) or 1.0
                    out.append((x - dist * dy / L, y + dist * dx / L))
                return out

            def draw_edge(s, t, v):
                w = 1.2 + 22.0 * abs(v) / maxw
                col = TEAL if v > 0 else TERRA
                if t == 'SCORE':
                    p0 = pos[s]; p2 = (cx + 0.03 * (p0[0] - cx), cy + 0.03 * (p0[1] - cy))
                    p1 = ((p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2)
                else:
                    p0, p2 = pos[s], pos[t]
                    mx, my = (p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2
                    d = math.hypot(p2[0] - p0[0], p2[1] - p0[1]) or 1.0
                    bow = 0.10 * d
                    p1 = (mx - (my - cy) / d * bow, my + (mx - cx) / d * bow)
                pts = sample_quad(p0, p1, p2)
                # ridge texture: two faint parallel curves + the main band
                for off, al in ((-(w / 2 + 1.6), 0.28), (w / 2 + 1.6, 0.28)):
                    xs, ys = zip(*offset_curve(pts, off))
                    ax.plot(xs, ys, color=col, lw=1.0, alpha=al, zorder=3)
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color=col, lw=w, alpha=0.88, solid_capstyle='round', zorder=4)

            # smallest first so the big ridges sit on top
            for k, v in sorted(edges.items(), key=lambda kv: abs(kv[1])):
                if k.source in pos and k.target in pos:
                    draw_edge(k.source, k.target, v)

            # ---- centre goal mark
            ax.add_patch(patches.Circle((cx, cy), 0.018, facecolor=self.text_color,
                                        edgecolor='none', zorder=5))
            fig.text(cx, cy - 0.052, 'GOAL', ha='center', fontsize=13,
                     color=self.text_color, fontproperties=self.prop_title)

            # ---- legend
            if single:
                fig.text(0.30, 0.055, '— OWN SCORING', ha='center', fontsize=11,
                         color=TEAL, fontproperties=self.prop_body)
                fig.text(0.70, 0.055, '— CONCEDED', ha='center', fontsize=11,
                         color=TERRA, fontproperties=self.prop_body)
            else:
                fig.text(0.30, 0.055, f'— {a_name.upper()} EDGE', ha='center', fontsize=11,
                         color=TEAL, fontproperties=self.prop_body)
                fig.text(0.70, 0.055, f'— {b_name.upper()} EDGE', ha='center', fontsize=11,
                         color=TERRA, fontproperties=self.prop_body)

            # ---- verdict banner
            fig.add_artist(patches.Rectangle((0.03, 0.012), 0.94, 0.032,
                                             facecolor=self.text_color, edgecolor='none', zorder=5))
            if single:
                msg = f'NET BALANCE {net:+.3f}'
            else:
                win = a_name if net > 0 else b_name
                msg = f'NET DELTA {net:+.3f}  →  {win.upper()}'
            # DejaVu Sans (matplotlib default) — FasterOne/Roboto both lack
            # the U+2192 arrow glyph; a missing glyph renders as a tofu box.
            fig.text(0.5, 0.0285, msg, ha='center', va='center', fontsize=17,
                     color=self.bg_color, zorder=6, fontweight='bold')

            self.save_and_close(fig, save_path, dpi=100)
        except Exception:
            plt.close(fig)
            raise
