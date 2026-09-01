import math

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
                         delta: Dict = None, animate: bool = False,
                         anim_path: str = None, fps: int = 24,
                         ink: float = 26.0):
        """Team fingerprint(s) as a WHORLFIELD card (2026-08-30).

        Design (delegated generative-art pass — Whorlfield concept):
        every edge of the matrix emits a smooth flow; summed, the edges
        define a 2D vector field; ridges ARE streamlines traced through
        that field. The whorl is the data's own circulation.

        Honesty (enforced in Core/fingerprint_field.py, unit-tested):
        - weight = packing density (equal-ink budget per colour), never
          thickness — all teams have ~equal total ink, so strength never
          reads as size
        - ridges keep min spacing (no moiré at Telegram compression)
        - verdict banner always shows the ENGINE's number (net delta);
          the geometry carries the same story but never overrides it

        Overlay: same seeds traced through A's field (teal) and B's field
        (terracotta) — agreeing regions pair up, differing regions fan.
        Single: teal = own-scoring flow, terracotta = conceded flow.

        animate=True: ridges ink in rim->goal (the "press"), A then B in
        overlay mode; writes an MP4 (and keeps the static poster).
        """
        import math

        from Core.fingerprint_field import (
            GOAL_RING,
            balance_ridges,
            build_delta_field,
            build_field,
            node_positions,
            overlay_verdict,
            trace_streamlines,
        )
        from Core.mappings import TEAM_DATA
        col_a = TEAM_DATA.get(team_a, {}).get('primary', '#1F6F6B')
        col_b = TEAM_DATA.get(team_b, {}).get('primary', '#C1553A')
        # club colours (2026-09-01, Austin's brief): A = their club colour;
        # single-team card: conceded flow = neutral grey, own = club colour
        TEAL = col_a
        TERRA = col_b if not single else '#8C8474'
        a_name = TEAM_DATA.get(team_a, {}).get('name', team_a)
        b_name = TEAM_DATA.get(team_b, {}).get('name', team_b) if team_b else None
        pos = node_positions()
        cx, cy, R = 0.5, 0.52, 0.40

        # ---------------- ridge generation (pure math)
        if single:
            field = build_field(matrix_a, pos)
            pos_share = (sum(v for v in matrix_a.values() if v > 0)
                         / max(sum(abs(v) for v in matrix_a.values()), 1e-9))
            seeds = _whorl_seeds(48, rings=2, jitter=1.4)
            # teal follows the OWN-scoring flow, terra the CONCEDED flow —
            # tracing both through the signed field is the all-one-colour bug
            # (2026-08-30: North's teal ridges died in their negative flow)
            ridges_pos = _goal_reaching(
                trace_streamlines(field, seeds, pos, ink * pos_share,
                                  fx=field['xp'], fy=field['yp'],
                                  min_spacing=0.012), cx, cy, R * GOAL_RING)
            ridges_neg = _goal_reaching(
                trace_streamlines(field, seeds, pos, ink * (1 - pos_share),
                                  fx=field['xn'], fy=field['yn'],
                                  min_spacing=0.012), cx, cy, R * GOAL_RING)
            # budget is a cap; the BALANCE is enforced structurally so the
            # colour ratio matches the data's weight ratio (equal-ink truth)
            teal_ridges, terra_ridges = balance_ridges(ridges_pos, ridges_neg,
                                                       pos_share)
            net = net_a if net_a is not None else sum(matrix_a.values())
        else:
            # THE DIFFERENCE, not both fields (2026-08-30): showing both at
            # full strength was a semantic overload — equal-ink fingerprints
            # made every card a 50/50 tangle regardless of who was winning.
            # teal = A wins the flow here, red = B wins, cream = equal.
            if delta is None:
                from Core.engine_core import fingerprint_overlay
                delta, net_a, net_b = fingerprint_overlay(matrix_a, matrix_b)
            dfield = build_delta_field(delta, pos)
            seeds = _whorl_seeds(56, rings=2, jitter=1.4)
            d_pos = sum(v for v in delta.values() if v > 0)
            d_neg = sum(-v for v in delta.values() if v < 0)
            d_share = d_pos / max(d_pos + d_neg, 1e-9)
            teal_ridges = _goal_reaching(
                trace_streamlines(dfield, seeds, pos, ink * d_share,
                                  fx=dfield['xp'], fy=dfield['yp'],
                                  min_spacing=0.012), cx, cy, R * GOAL_RING)
            terra_ridges = _goal_reaching(
                trace_streamlines(dfield, seeds, pos, ink * (1 - d_share),
                                  fx=dfield['xn'], fy=dfield['yn'],
                                  min_spacing=0.012), cx, cy, R * GOAL_RING)
            teal_ridges, terra_ridges = balance_ridges(teal_ridges, terra_ridges,
                                                       d_share)
            net = (net_a or 0.0) - (net_b or 0.0)
        ta_c, tb_c, geom_verdict = overlay_verdict(teal_ridges, terra_ridges, pos)

        # ---------------- canvas
        fig = plt.figure(figsize=(9, 12), facecolor=self.bg_color)
        try:
            fig.text(0.5, 0.978, 'FINGERPRINT', ha='center', fontsize=20,
                     color=self.text_color, fontproperties=self.prop_title)
            if not single:
                # VERDICT FIRST — the largest element, top of the card.
                # The cold-read showed the banner at the bottom is the
                # weakest position for a headline claim.
                win_name = a_name if net >= 0 else b_name
                win_col = TEAL if net >= 0 else TERRA
                fig.add_artist(patches.Rectangle((0.03, 0.906), 0.94, 0.062,
                                                 facecolor=win_col,
                                                 edgecolor='none', zorder=5))
                fig.text(0.5, 0.944, win_name.upper(), ha='center', va='center',
                         fontsize=30, color=self.bg_color, zorder=6,
                         fontproperties=self.prop_title)
                fig.text(0.5, 0.923, f'MODEL PREDICTS · EDGE {abs(net):.3f}',
                         ha='center', va='center', fontsize=10,
                         color=self.bg_color, zorder=6, fontweight='bold')
                fig.text(0.5, 0.890,
                         f'SEASON {season} · THROUGH R{round_num} · '
                         f'{a_name.upper()} vs {b_name.upper()}',
                         ha='center', fontsize=11.5, color=self.sub_text_color)
            else:
                sub = f'SEASON {season} · THROUGH R{round_num} · {a_name.upper()}'
                fig.text(0.5, 0.924, sub, ha='center', fontsize=12,
                         color=self.sub_text_color)

            ax = fig.add_axes([0.06, 0.10, 0.88, 0.80]) if single else \
                fig.add_axes([0.06, 0.115, 0.88, 0.74])
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect('equal')
            ax.axis('off')

            # paper texture: concentric rings + spokes
            for r_i in range(5):
                rr = R * (0.14 + 0.82 * (4 - r_i) / 4.0)
                ax.add_patch(patches.Circle((cx, cy), rr, fill=False,
                                            edgecolor='#E3DCCB', lw=1.2, zorder=1))
            for c_i in range(5):
                ang = math.radians(90 + (c_i - 2) * 34)
                ax.plot([cx + 0.02 * math.cos(ang), cx + R * math.cos(ang)],
                        [cy + 0.02 * math.sin(ang), cy + R * math.sin(ang)],
                        color='#EAE4D5', lw=1.0, zorder=1)
            # goal ring (the verdict ring)
            ax.add_patch(patches.Circle((cx, cy), R * GOAL_RING, fill=False,
                                        edgecolor='#D5CCB8', lw=1.6, zorder=1))

            def offset_pts(pts, dist):
                out = []
                for i, (x, y) in enumerate(pts):
                    dx = pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0]
                    dy = pts[min(i + 1, len(pts) - 1)][1] - pts[max(i - 1, 0)][1]
                    L = (dx * dx + dy * dy) ** 0.5 or 1.0
                    out.append((x - dist * dy / L, y + dist * dx / L))
                return out

            def draw_ridges(ridges, color, side, emphasis=1.0):
                # tapered: flow is thickest at its source (the seed) and
                # thins toward the goal — a real data property, not styling.
                # Perpendicular offset (side=-1/+1) pairs overlapping flows
                # side-by-side instead of stacking them — where both colours
                # run, you SEE both (draw order no longer buries a colour).
                # emphasis < 1 thins the LOSER's ridges so visual weight
                # follows the verdict (2026-08-30 cold-read: the densest
                # colour belonged to the losing team).
                widths = (3.4, 2.6, 1.9)
                for pts in ridges:
                    off = offset_pts(pts, 0.0045 * side)
                    n = len(off)
                    for seg, w in enumerate(widths):
                        i0 = n * seg // 3
                        i1 = n * (seg + 1) // 3
                        if i1 <= i0:
                            continue
                        xs = [p[0] for p in off[i0:i1 + 1]]
                        ys = [p[1] for p in off[i0:i1 + 1]]
                        ax.plot(xs, ys, color=color, lw=w * emphasis,
                                alpha=0.72 * (0.55 + 0.45 * emphasis),
                                solid_capstyle='round', zorder=3)

            if single:
                draw_ridges(terra_ridges, TERRA, side=+1)
                draw_ridges(teal_ridges, TEAL, side=-1)
            else:
                # the winner's territory is drawn heavy and on top — the
                # verdict is the message, the zones are the explanation
                win_teal = net >= 0
                draw_ridges(terra_ridges, TERRA, side=+1,
                            emphasis=0.62 if win_teal else 1.0)
                draw_ridges(teal_ridges, TEAL, side=-1,
                            emphasis=1.0 if win_teal else 0.62)

            ax.add_patch(patches.Circle((cx, cy), 0.018, facecolor=self.text_color,
                                        edgecolor='none', zorder=5))
            fig.text(cx, cy - 0.052, 'GOAL', ha='center', fontsize=13,
                     color=self.text_color, fontproperties=self.prop_title)

            # legend
            if single:
                fig.text(0.30, 0.055, '— OWN SCORING FLOW', ha='center', fontsize=11,
                         color=TEAL, fontproperties=self.prop_body)
                fig.text(0.70, 0.055, '— CONCEDED FLOW', ha='center', fontsize=11,
                         color=TERRA, fontproperties=self.prop_body)
            else:
                # THE KEY (2026-08-30): the colour legend explained the
                # colours but never the OBJECT. A viewer must learn what a
                # line IS — ball movement — before any of this reads.
                fig.text(0.5, 0.093, 'WHAT THE LINES ARE', ha='center',
                         fontsize=8.5, color=self.sub_text_color,
                         fontproperties=self.prop_body,
                         style='italic')
                fig.text(0.5, 0.077,
                         'the lines = how each team moves the ball to goal',
                         ha='center', fontsize=12.5, color=self.text_color,
                         fontproperties=self.prop_body, fontweight='bold')
                fig.text(0.5, 0.060,
                         'thicker = played more often · all flow toward the goal',
                         ha='center', fontsize=9.5, color=self.sub_text_color,
                         fontproperties=self.prop_body)
                fig.text(0.30, 0.041, f'{a_name.upper()} WINS THE FLOW',
                         ha='center', fontsize=10.5, color=TEAL,
                         fontproperties=self.prop_body)
                fig.text(0.70, 0.041, f'{b_name.upper()} WINS THE FLOW',
                         ha='center', fontsize=10.5, color=TERRA,
                         fontproperties=self.prop_body)
                fig.text(0.5, 0.026, 'blank = even', ha='center', fontsize=8,
                         color='#8C8474', fontproperties=self.prop_body)
                # direction glyph: a curved line flowing into the goal dot —
                # the one thing the whorl can't say with static ridges
                kax = fig.add_axes([0.415, 0.016, 0.17, 0.028])
                kax.set_xlim(0, 1); kax.set_ylim(0, 1); kax.axis('off')
                import numpy as np
                t = np.linspace(0, 1, 40)
                kax.plot(0.12 + 0.55 * t, 0.15 + 0.55 * t - 0.5 * t * (1 - t),
                         color=self.text_color, lw=2.0, solid_capstyle='round')
                kax.annotate('', xy=(0.80, 0.55), xytext=(0.55, 0.45),
                             arrowprops=dict(arrowstyle='-|>', color=self.text_color,
                                             lw=2.0))
                kax.add_patch(patches.Circle((0.88, 0.55), 0.055,
                                              facecolor=self.text_color,
                                              edgecolor='none'))
                fig.text(0.5, 0.0165, 'flow → goal', ha='center', fontsize=7.5,
                         color=self.sub_text_color)  # default font: has U+2192

            # single mode keeps the compact bottom banner
            if single:
                fig.add_artist(patches.Rectangle((0.03, 0.012), 0.94, 0.032,
                                                 facecolor=self.text_color,
                                                 edgecolor='none', zorder=5))
                fig.text(0.5, 0.0285, f'NET BALANCE {net:+.3f}', ha='center',
                         va='center', fontsize=17, color=self.bg_color,
                         zorder=6, fontweight='bold')

            self.save_and_close(fig, save_path, dpi=100)

            if animate and anim_path:
                act_ridges = None
                if not single:
                    # 3-act press needs each team's OWN field ridges too
                    fa = build_field(matrix_a, pos)
                    fb = build_field(matrix_b, pos)
                    sd = _whorl_seeds(56, rings=2, jitter=1.4)
                    act_ridges = (
                        _goal_reaching(trace_streamlines(
                            fa, sd, pos, ink, fx=fa['x'], fy=fa['y'],
                            min_spacing=0.012), cx, cy, R * GOAL_RING),
                        _goal_reaching(trace_streamlines(
                            fb, sd, pos, ink, fx=fb['x'], fy=fb['y'],
                            min_spacing=0.012), cx, cy, R * GOAL_RING),
                    )
                self._animate_fingerprint(teal_ridges, terra_ridges, anim_path,
                                          fps, single, a_name, b_name, season,
                                          round_num, net, cx, cy, R,
                                          act_ridges=act_ridges)
        except Exception:
            plt.close(fig)
            raise

    def _animate_fingerprint(self, teal_ridges, terra_ridges, anim_path, fps,
                             single, a_name, b_name, season, round_num, net,
                             cx, cy, R, act_ridges=None):
        """The press, in three acts (2026-08-30).

        Single mode: the team's whorl inks in, rim -> goal.

        Overlay mode (act_ridges = (A's own ridges, B's own ridges)):
          ACT 1 (0-30%)   press A — A's full fingerprint inks in, teal
          ACT 2 (30-60%)  press B — B's full fingerprint inks over it, red
          ACT 3 (60-100%) RESOLVE — both fade out and the DIFFERENCE field
                          inks in: teal where A wins, red where B wins, bare
                          paper where they're even. The loop therefore
                          *explains* the static card every time it plays:
                          two identities -> one verdict.

        Writes an MP4 (ffmpeg).
        """
        from matplotlib.animation import FuncAnimation

        from Core.mappings import TEAM_DATA
        _by_name = {v['name']: v['primary'] for v in TEAM_DATA.values()}
        col_a = _by_name.get(a_name, '#1F6F6B')
        col_b = _by_name.get(b_name or '', '#8C8474')
        TEAL = col_a
        TERRA = col_b if not single else '#8C8474'
        fig = plt.figure(figsize=(9, 12), facecolor=self.bg_color)
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
        for r_i in range(5):
            rr = R * (0.20 + 0.76 * (4 - r_i) / 4.0)
            ax.add_patch(patches.Circle((cx, cy), rr, fill=False,
                                        edgecolor='#E3DCCB', lw=1.2, zorder=1))
        # GOAL marker (2026-08-31, confusion-hunt fix #3): the centre must
        # read as the destination, not an empty hole — in the MOVING frames.
        # The RING is the real fix for "lines passing the goal": the tracer
        # stops ridges at R*GOAL_RING, but with no visible boundary the
        # converging tips read as crossing the centre (esp. at phone size).
        ring_r = R * 0.16
        win_col_anim = '#1F6F6B' if (single or net > 0) else '#C1553A'
        ax.add_patch(patches.Circle((cx, cy), ring_r, fill=False,
                                    edgecolor=win_col_anim, lw=4.0, alpha=0.9,
                                    zorder=5))
        ax.add_patch(patches.Circle((cx, cy), 0.014, facecolor=self.text_color,
                                    edgecolor='none', zorder=6))
        ax.text(cx, cy - 0.045, 'GOAL', ha='center', fontsize=11,
                color=self.text_color, fontproperties=self.prop_title, zorder=6)

        def seed_rad(pts):
            return ((pts[0][0] - cx) ** 2 + (pts[0][1] - cy) ** 2) ** 0.5

        NFRAMES = 90

        # ---- caption that narrates the acts
        cap = fig.text(0.5, 0.078, '', ha='center', fontsize=12.5,
                       color=self.sub_text_color, fontproperties=self.prop_body)
        # ---- mini-key: what the lines ARE (confusion-hunt fix #1/#4)
        fig.text(0.5, 0.061, 'the lines = how each team moves the ball to goal · '
                             'thicker = played more often',
                 ha='center', fontsize=9, color='#8A8378',
                 fontproperties=self.prop_body)
        # ---- the engine number, always visible (confusion-hunt fix #5)
        if single:
            num_text = f'NET BALANCE {net:+.3f}'
        else:
            win_name_early = a_name if net > 0 else b_name
            num_text = f'MODEL PREDICTS {win_name_early.upper()} · EDGE {abs(net):.3f}'
        fig.text(0.5, 0.045, num_text, ha='center', fontsize=11.5,
                 color=self.text_color, fontproperties=self.prop_body,
                 fontweight='bold')
        # ---- persistent colour legend (confusion-hunt fix #2: colour keyed
        # to MEANING, not just to the team name)
        if single:
            fig.text(0.28, 0.028, 'OWN SCORING FLOW', ha='center',
                     fontsize=10, color='#1F6F6B', fontproperties=self.prop_body)
            fig.text(0.72, 0.028, 'RED — CONCEDED', ha='center',
                     fontsize=10, color='#C1553A', fontproperties=self.prop_body)
        else:
            fig.text(0.30, 0.028, f'{a_name.upper()} WINS THE FLOW',
                     ha='center', fontsize=9.5, color='#1F6F6B',
                     fontproperties=self.prop_body)
            fig.text(0.70, 0.028, f'RED — {b_name.upper()} WINS THE FLOW',
                     ha='center', fontsize=9.5, color='#C1553A',
                     fontproperties=self.prop_body)
            fig.text(0.5, 0.016, 'blank = even', ha='center', fontsize=8.5,
                     color='#8A8378', fontproperties=self.prop_body)

        if single or not act_ridges:
            lines = []
            for pts in teal_ridges:
                ln, = ax.plot([], [], color=TEAL, lw=2.6, alpha=0.85,
                              solid_capstyle='round', zorder=3)
                lines.append((ln, pts))
            for pts in terra_ridges:
                ln, = ax.plot([], [], color=TERRA, lw=2.6, alpha=0.85,
                              solid_capstyle='round', zorder=3)
                lines.append((ln, pts))
            lines.sort(key=lambda it: -seed_rad(it[1]))

            def frame(t):
                prog = (t / NFRAMES) * 1.2
                for ln, pts in lines:
                    n = min(len(pts), max(1, int(len(pts) * min(prog, 1.0))))
                    ln.set_data([p[0] for p in pts[:n]], [p[1] for p in pts[:n]])
                # narration (confusion-hunt fix #6: a mid-frame half-drawing
                # with no caption reads as a broken card)
                if prog < 1.0:
                    cap.set_text(f'how {a_name.upper()} moves the ball to goal')
                else:
                    verdict = ('creates more than it concedes' if net > 0
                               else 'concedes more than it creates')
                    cap.set_text(f'NET BALANCE {net:+.3f} — {verdict}')
                return [ln for ln, _ in lines] + [cap]
        else:
            a_own, b_own = act_ridges
            # act 1+2 artists (each team's own fingerprint)
            a_lines = [(ax.plot([], [], color=TEAL, lw=2.4, alpha=0.75,
                                solid_capstyle='round', zorder=3)[0], pts)
                       for pts in a_own]
            b_lines = [(ax.plot([], [], color=TERRA, lw=2.4, alpha=0.75,
                                solid_capstyle='round', zorder=3)[0], pts)
                       for pts in b_own]
            # act 3 artists (the difference)
            d_lines = [(ax.plot([], [], color=TEAL, lw=2.9, alpha=0.0,
                                solid_capstyle='round', zorder=4)[0], pts)
                       for pts in teal_ridges]
            d_lines += [(ax.plot([], [], color=TERRA, lw=2.9, alpha=0.0,
                                 solid_capstyle='round', zorder=4)[0], pts)
                        for pts in terra_ridges]
            a_lines.sort(key=lambda it: -seed_rad(it[1]))
            b_lines.sort(key=lambda it: -seed_rad(it[1]))
            d_lines.sort(key=lambda it: -seed_rad(it[1]))
            win_name = a_name if net > 0 else b_name

            def ink(lines, prog, alpha):
                for ln, pts in lines:
                    n = max(1, int(len(pts) * min(prog * 1.1, 1.0)))
                    if prog <= 0:
                        ln.set_data([], [])
                    else:
                        ln.set_data([p[0] for p in pts[:n]],
                                    [p[1] for p in pts[:n]])
                    ln.set_alpha(alpha)

            def frame(t):
                f = t / NFRAMES
                if f < 0.30:                      # ACT 1 — press A
                    ink(a_lines, f / 0.30, 0.78)
                    ink(b_lines, 0, 0.0)
                    ink(d_lines, 0, 0.0)
                    cap.set_text(f'1 of 2 — how {a_name.upper()} moves the ball to goal')
                elif f < 0.60:                    # ACT 2 — press B over it
                    ink(a_lines, 1.0, 0.42)
                    ink(b_lines, (f - 0.30) / 0.30, 0.78)
                    ink(d_lines, 0, 0.0)
                    cap.set_text(f'2 of 2 — how {b_name.upper()} moves the ball to goal')
                else:                             # ACT 3 — resolve to the diff
                    k = (f - 0.60) / 0.40
                    fade = max(0.0, 0.42 * (1 - k * 2.2))
                    ink(a_lines, 1.0, fade)
                    ink(b_lines, 1.0, fade)
                    ink(d_lines, min(k * 1.4, 1.0), min(k * 2.0, 0.9))
                    cap.set_text(f"where they differ decides it — the model picks {win_name.upper()}")
                arts = ([ln for ln, _ in a_lines] + [ln for ln, _ in b_lines]
                        + [ln for ln, _ in d_lines] + [cap])
                return arts

        anim = FuncAnimation(fig, frame, frames=NFRAMES, interval=1000 / fps,
                             blit=False)
        anim.save(anim_path, writer='ffmpeg', fps=fps, dpi=100)
        plt.close(fig)


def _goal_reaching(ridges, cx, cy, ring, tol=2.2):
    """Keep only ridges that END at the goal ring — scoring flow only.

    2026-09-01 (Austin's alignment rule): the whorl must contain only chains
    in the model's scope (outcome == 'SCORE', profiler.py:44). Streamlines
    that swirl past the goal without terminating read as non-scoring
    movement — visually misaligned with the model — so they are removed.
    Every visible line now reaches the goal: one-for-one with the model.
    """
    keep = []
    for r in ridges:
        x, y = r[-1]
        if math.hypot(x - cx, y - cy) < ring * tol:
            keep.append(r)
    return keep

def _whorl_seeds(n: int, rings: int = 1, jitter: float = 0.0):
    """Seeds on concentric rings (outer rim + mid ring), with a tiny angle
    jitter so the whorl isn't digitally mirror-perfect (jitter is cosmetic
    only — it never moves a data point)."""
    import math
    import random

    random.seed(7)  # deterministic
    cx, cy, R = 0.5, 0.52, 0.40
    out = []
    for ring in range(rings):
        r = R * (0.98 - 0.22 * ring)
        for i in range(n):
            a = 2 * math.pi * i / n + math.radians(random.uniform(-jitter, jitter))
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out
