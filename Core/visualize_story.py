import matplotlib

matplotlib.use('Agg')
from typing import Dict, Tuple

import matplotlib.pyplot as plt

from Core.field_visualizer import FieldVisualizer
from Core.mappings import TEAM_DATA
from Core.models import TransitionEdge
from Core.theme import get_ordinal, mute_color
from Core.vector_renderer import VectorRenderer


class StoryVisualizer(FieldVisualizer):
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

    def draw_variance_map(self, team_a: str, team_b: str, variance_matrix: Dict[TransitionEdge, float],
                          expected_delta: Dict[TransitionEdge, float], actual_delta: Dict[TransitionEdge, float],
                          driver_annotations: Dict[Tuple[str, str], str],
                          expected_net: float, actual_net: float, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel', elo_a: float = 1500.0, elo_b: float = 1500.0, rank_a=None, rank_b=None, tier_a=None, tier_b=None):

        if is_mobile:
            figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
            fig = plt.figure(figsize=figsize, facecolor=self.bg_color)
            # Field band sized to the data aspect (190x150) with equal aspect:
            # round oval, fills the card's middle band (fix 2026-08-25).
            if mobile_format == 'reel':
                ax = fig.add_axes([0.10, 0.12, 0.80, 0.70])
                title_y = 0.90
                text_y_attack = 0.845
                text_y_footer = 0.06
            else:
                ax = fig.add_axes([0.10, 0.15, 0.80, 0.655])
                title_y = 0.92
                text_y_attack = 0.845
                text_y_footer = 0.085
            font_scale = 0.95
        else:
            fig = plt.figure(figsize=(16, 10), facecolor=self.bg_color)
            ax = fig.add_subplot(111)
            title_y = 0.97
            text_y_attack = 0.90
            text_y_footer = 0.05
            font_scale = 1.0

        try:
            n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
            n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']

            c_a, c_b = self.get_team_colors(team_a, team_b)
            self.draw_pitch(ax)
            if is_mobile:
                ax.set_aspect('equal')  # round oval, not stretched (fix 2026-08-25)

            home_vars = [(e, v) for e, v in variance_matrix.items() if v > 0]
            away_vars = [(e, v) for e, v in variance_matrix.items() if v < 0]

            home_top = sorted(home_vars, key=lambda x: x[1], reverse=True)[:3]
            away_top = sorted(away_vars, key=lambda x: x[1])[:3]
            top_edges = [e for e, v in home_top + away_top]

            active_nodes = set()
            for edge in top_edges:
                active_nodes.add(edge.source)
                active_nodes.add(edge.target)

            self.draw_zones(ax, active_only=True, active_nodes=active_nodes, font_scale=font_scale)
            labels_to_draw = []

            for edge in top_edges:
                score = variance_matrix[edge]
                start, end = edge.source, edge.target

                base_score = expected_delta.get(edge, actual_delta.get(edge, 0))
                is_away_edge = base_score < 0

                # Arrow thickness: same |score| scaling as vector_renderer
                # (was ×0.9 vs ×2.0 — inconsistent multipliers, audit cleanup).
                lw = min(15, max(5, abs(score) * 2.0))
                edge_owner = n_b if is_away_edge else n_a
                arrow_color = mute_color(c_b if is_away_edge else c_a)
                is_defense = (score > 0 and is_away_edge) or (score < 0 and not is_away_edge)

                if is_defense:
                    arrow_style = ']-'
                    action_type = "SUPPRESSED"
                    variance_str = f"-{abs(score):.2f}"
                else:
                    arrow_style = '->,head_width=0.7,head_length=0.9'
                    action_type = "OVERPERFORMANCE"
                    variance_str = f"+{abs(score):.2f}"

                self.vector_renderer.render_vector(
                    ax=ax,
                    edge=edge,
                    score=score,
                    color=arrow_color,
                    is_away_edge=is_away_edge,
                    apply_blur=False,
                    arrow_style=arrow_style,
                    show_label=False,
                    max_lw=15.0
                )

                # We need to get physical coordinates for labeling.
                # Delta keys are in the home frame already (audit fix): do not
                # rotate zones for away edges, only map the goal to the away end.
                if is_away_edge:
                    phys_start = start
                    phys_end = end
                    if phys_start == 'SCORE': phys_start = 'AWAY_G'
                    elif phys_start == 'AWAY_G': phys_start = 'SCORE'
                    if phys_end == 'SCORE': phys_end = 'AWAY_G'
                    elif phys_end == 'AWAY_G': phys_end = 'SCORE'
                else:
                    phys_start = start
                    phys_end = end

                p1 = self.node_positions.get(phys_start)
                p2 = self.node_positions.get(phys_end)
                if not p1 or not p2: continue

                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = (dx**2 + dy**2)**0.5 if (dx**2 + dy**2) > 0 else 1
                px = -dy / length
                py = dx / length
                offset = 8 + (lw * 0.5)

                mid_x = (p1[0] + p2[0]) / 2 + (px * offset)
                mid_y = (p1[1] + p2[1]) / 2 + (py * offset)

                pct_str = " (New)"
                if abs(base_score) > 0.1:
                    pct = (abs(score) / abs(base_score)) * 100
                    pct_str = f" ({pct:.0f}%)"

                label_text = f"{edge_owner.upper()} {action_type}\n{variance_str}{pct_str}"
                if edge in driver_annotations:
                    label_text += f"\nDriven by: {driver_annotations[edge]}"

                labels_to_draw.append({
                    'x': mid_x, 'y': mid_y, 'orig_x': mid_x, 'orig_y': mid_y,
                    'text': label_text, 'color': arrow_color
                })

            min_dist_x = 40
            min_dist_y = 18
            for _ in range(50):
                moved = False
                for i in range(len(labels_to_draw)):
                    for j in range(i + 1, len(labels_to_draw)):
                        l1 = labels_to_draw[i]
                        l2 = labels_to_draw[j]
                        dx = l1['x'] - l2['x']
                        dy = l1['y'] - l2['y']
                        if abs(dx) < min_dist_x and abs(dy) < min_dist_y:
                            if abs(dx) > abs(dy):
                                push = (min_dist_x - abs(dx)) / 2.0
                                sign = 1 if dx > 0 else -1
                                l1['x'] += push * sign
                                l2['x'] -= push * sign
                            else:
                                push = (min_dist_y - abs(dy)) / 2.0
                                sign = 1 if dy > 0 else -1
                                l1['y'] += push * sign
                                l2['y'] -= push * sign
                            moved = True
                if not moved:
                    break

            # Keep annotation boxes inside the canvas — text is not clipped by the
            # axes, so unclamped labels ran past the figure edge (fix 2026-08-25).
            for label in labels_to_draw:
                label['x'] = max(-72.0, min(72.0, label['x']))
                label['y'] = max(-58.0, min(58.0, label['y']))

            for label in labels_to_draw:
                if abs(label['x'] - label['orig_x']) > 2 or abs(label['y'] - label['orig_y']) > 2:
                    ax.plot([label['orig_x'], label['x']], [label['orig_y'], label['y']], color=label['color'], linewidth=1, alpha=0.5, linestyle=':', zorder=3)

                lbl_font, lbl_size = self.get_font_and_size(self.prop_sub, 9 * font_scale)
                ax.text(label['x'], label['y'], label['text'], color=self.text_color, fontsize=lbl_size,
                        ha='center', va='center', bbox=dict(facecolor=self.bg_color, alpha=0.9, edgecolor=label['color'], lw=1.5, pad=3, boxstyle='round,pad=0.4'), zorder=4, fontproperties=lbl_font)

            if not is_mobile:
                fig.suptitle(f'TACTICAL STORY: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.98, fontproperties=self.prop_title)
                ax.set_title("Top Variance Vectors (Actual vs 25-Game Baseline)", color=self.sub_text_color, fontsize=14, pad=10, fontproperties=self.prop_sub)
            else:
                fig.text(0.5, title_y, f'TACTICAL STORY:\n{n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=17, ha='center', va='center', fontproperties=self.prop_title)
                sub_font, sub_size = self.get_font_and_size(self.prop_sub, 12)
                fig.text(0.5, title_y - 0.05, "Top Variance Vectors (Actual vs Baseline)", color=self.sub_text_color, fontsize=sub_size, ha='center', va='center', fontproperties=sub_font)

            ax.set_xlim(-95, 95); ax.set_ylim(-75, 75); ax.axis('off')

            footer_text = f"EXPECTED MATCHUP SCORE: {expected_net:+.2f}  |  ACTUAL MATCHUP SCORE: {actual_net:+.2f}"
            foot_font, foot_size = self.get_font_and_size(self.prop_sub, 14 * font_scale)
            plt.figtext(0.5, text_y_footer, footer_text, ha='center', fontsize=foot_size, color=self.bg_color, bbox=dict(facecolor=self.text_color, alpha=1.0, pad=8), fontproperties=foot_font)

            rank_b_str = f'RANK: {get_ordinal(rank_b)}' if rank_b else ''
            tier_b_str = f' [{tier_b}]' if tier_b else ''
            att_font, att_size = self.get_font_and_size(self.prop_sub, 11 * font_scale)
            fig.text(0.15 if not is_mobile else 0.2, text_y_attack, f'{n_b.upper()} ATTACK\n{rank_b_str}{tier_b_str}', color=mute_color(c_b), fontsize=att_size, ha='center', va='center', fontproperties=att_font)
            rank_a_str = f'RANK: {get_ordinal(rank_a)}' if rank_a else ''
            tier_a_str = f' [{tier_a}]' if tier_a else ''
            fig.text(0.85 if not is_mobile else 0.8, text_y_attack, f'{n_a.upper()} ATTACK\n{rank_a_str}{tier_a_str}', color=mute_color(c_a), fontsize=att_size, ha='center', va='center', fontproperties=att_font)

            if is_mobile:
                self.save_and_close(fig, save_path, dpi=100, bbox_inches=None)
            else:
                self.save_and_close(fig, save_path, dpi=100, bbox_inches='tight')
        except:
            plt.close(fig)
            raise

    def draw_player_performance(self, team_a: str, team_b: str, player_actuals: Dict[str, float],
                                  player_expecteds: Dict[str, float], player_names: Dict[str, str],
                                  save_path: str, is_mobile: bool = False, mobile_format: str = 'reel'):
        if is_mobile:
            # Same canvas as every other mobile card (9x12 / 9x16) — the old
            # (10,14)/(10,18) rendered a different aspect in the feed (fix 2026-08-25).
            figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, facecolor=self.bg_color)
            title_fontsize = 18
            label_fontsize = 12
            header_fontsize = 20
            sub_fontsize = 14
        else:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 11), facecolor=self.bg_color)
            title_fontsize = 18
            label_fontsize = 11
            header_fontsize = 20
            sub_fontsize = 16

        try:
            n_a = TEAM_DATA.get(team_a, {'name': team_a})['name']
            n_b = TEAM_DATA.get(team_b, {'name': team_b})['name']

            variances = {pid: player_actuals[pid] - player_expecteds.get(pid, 0) for pid in player_actuals}
            sorted_p = sorted(variances.items(), key=lambda x: x[1], reverse=True)
            top_10 = sorted_p[:10]
            bottom_10 = sorted_p[-10:]

            def plot_ax(ax, data, title, is_top):
                names = [player_names.get(pid, pid).upper() for pid, val in data]
                vals = [val for pid, val in data]

                bar_color = mute_color('#228B22') if is_top else mute_color('#8B0000')

                bars = ax.barh(names, vals, color=bar_color, alpha=0.9)
                # Roboto for panel titles — Wallpoet's S renders as a '9' at this size
                # (fix 2026-08-25; see base_visualizer.get_font_and_size).
                ax.set_title(title, color=self.text_color, fontsize=title_fontsize + 1, pad=12, fontproperties=self.prop_body)
                ax.set_facecolor(self.bg_color)
                ax.invert_yaxis()
                ax.grid(axis='x', linestyle=':', color=self.sub_text_color, alpha=0.4)
                ax.tick_params(axis='both', colors=self.text_color, labelsize=label_fontsize)
                for label in ax.get_yticklabels():
                    label.set_fontproperties(self.prop_body)
                    label.set_fontsize(label_fontsize)
                for label in ax.get_xticklabels():
                    label.set_fontproperties(self.prop_body)
                    label.set_fontsize(label_fontsize)

                for spine in ax.spines.values(): spine.set_color(self.text_color)

                max_abs_val = max([abs(v) for v in vals]) if vals else 1

                if is_top:
                    ax.set_xlim(0, max_abs_val + (max_abs_val * 0.45))
                else:
                    ax.set_xlim(min(vals) - (max_abs_val * 0.45), 0)

                for bar, (pid, val) in zip(bars, data):
                    width = bar.get_width()
                    exp = player_expecteds.get(pid, 0)
                    pct_str = ""
                    if abs(exp) > 0.1:
                        pct = (abs(val) / abs(exp)) * 100
                        pct_str = f" ({pct:.0f}%)"

                    label_text = f'{width:+.2f}{pct_str}'
                    lbl_font, lbl_size = self.get_font_and_size(self.prop_sub, label_fontsize)

                    if is_top:
                        ax.text(width + (max_abs_val * 0.02), bar.get_y() + bar.get_height()/2, label_text,
                                va='center', ha='left', color=self.text_color,
                                fontsize=lbl_size, fontproperties=lbl_font)
                    else:
                        ax.text(width - (max_abs_val * 0.02), bar.get_y() + bar.get_height()/2, label_text,
                                va='center', ha='right', color=self.text_color,
                                fontsize=lbl_size, fontproperties=lbl_font)

            plot_ax(ax1, top_10, "MATCH WINNERS (OVERPERFORMERS)", True)
            plot_ax(ax2, bottom_10, "SUPPRESSED (UNDERPERFORMERS)", False)

            main_title = f"PLAYER IMPACT: {n_a.upper()} VS {n_b.upper()}"
            if is_mobile:
                # Clean Roboto header (fix 2026-08-25): FasterOne's striated glyphs
                # read as "shattered" on long two-line titles; Wallpoet's S mangles
                # at small sizes. Desktop keeps the branded suptitle.
                fig.text(0.5, 0.972, "PLAYER IMPACT", color=self.text_color, fontsize=24,
                         ha='center', va='center', fontproperties=self.prop_body)
                fig.text(0.5, 0.938, f"{n_a.upper()} VS {n_b.upper()}", color=self.text_color,
                         fontsize=15, ha='center', va='center', fontproperties=self.prop_body)
                fig.text(0.5, 0.905, "Actual Tactical Output vs 25-Game Baseline",
                         color=self.sub_text_color, fontsize=13, ha='center', va='center',
                         fontproperties=self.prop_body)
                # Fill the 9:12 / 9:16 canvas — no dead band (fix 2026-08-25).
                plt.tight_layout(rect=[0.02, 0.03, 0.98, 0.885])
                self.save_and_close(fig, save_path, dpi=100, bbox_inches=None)
            else:
                if len(main_title) > 35:
                    main_title = f"PLAYER IMPACT:\n{n_a.upper()} VS {n_b.upper()}"
                fig.suptitle(main_title, color=self.text_color, fontsize=header_fontsize, y=0.97, fontproperties=self.prop_title)
                sub_font2, sub_size2 = self.get_font_and_size(self.prop_sub, sub_fontsize)
                fig.text(0.5, 0.93, "Actual Tactical Output vs 25-Game Baseline", color=self.sub_text_color, fontsize=sub_size2, ha='center', fontproperties=sub_font2)
                plt.tight_layout(rect=[0.05, 0.05, 0.95, 0.92])
                self.save_and_close(fig, save_path, dpi=100, bbox_inches='tight')
        except:
            plt.close(fig)
            raise
