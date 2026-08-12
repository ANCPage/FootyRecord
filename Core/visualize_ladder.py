import matplotlib

matplotlib.use('Agg')
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

from Core.base_visualizer import BaseVisualizer
from Core.mappings import TEAM_DATA, get_short_name
from Core.theme import get_ordinal


class LadderVisualizer(BaseVisualizer):
    def __init__(self):
        super().__init__()

    def draw_cumulative_ladder(self, ingestor, season: int, up_to_round: int, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel'):
        team_scores = defaultdict(lambda: defaultdict(float))
        max_round = 0

        matches = [m_id for m_id, info in ingestor.match_info.items() if info.season == season and info.round <= up_to_round]
        for m_id in matches:
            info = ingestor.match_info[m_id]
            perf = ingestor.match_performance.get(m_id)
            if not perf:
                continue

            r = info.round
            if r > max_round:
                max_round = r

            h_team = info.home
            a_team = info.away

            actual = perf.get('actual', 0.0)
            team_scores[h_team][r] += actual
            team_scores[a_team][r] -= actual

        cumulative = defaultdict(lambda: [0.0] * (max_round + 1))
        rounds_range = sorted(list(set(range(max_round + 1))))

        for team_id, rounds in team_scores.items():
            current = 0.0
            for r in rounds_range:
                current += rounds.get(r, 0.0)
                cumulative[team_id][r] = current

        if is_mobile:
            figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
        else:
            figsize = (16, 10)

        fig, ax = plt.subplots(figsize=figsize, facecolor=self.bg_color)
        try:
            ax.set_facecolor(self.bg_color)

            rounds_x = rounds_range
            final_scores = sorted(cumulative.items(), key=lambda x: x[1][max_round], reverse=True)

            y_vals = {team_id: scores[max_round] for team_id, scores in final_scores}
            sorted_items = sorted(y_vals.items(), key=lambda x: x[1], reverse=True)
            y_new = [v for k, v in sorted_items]

            max_y = max(y_new) if y_new else 1
            min_y = min(y_new) if y_new else 0
            min_dist = (max_y - min_y) * 0.04
            if min_dist == 0:
                min_dist = 0.5

            for _ in range(200):
                moved = False
                for i in range(len(y_new) - 1):
                    diff = y_new[i] - y_new[i+1]
                    if diff < min_dist:
                        push = (min_dist - diff) / 2.0
                        y_new[i] += push
                        y_new[i+1] -= push
                        moved = True
                if not moved:
                    break

            label_y_positions = {sorted_items[i][0]: y_new[i] for i in range(len(y_new))}

            def smooth_line(x, y, num_points=300):
                if len(x) < 3:
                    return np.array(x), np.array(y)
                x_smooth = np.linspace(x[0], x[-1], num_points)
                y_smooth = np.zeros(num_points)
                n = len(x)
                for i in range(num_points):
                    idx = np.searchsorted(x, x_smooth[i]) - 1
                    idx = max(0, min(idx, n - 2))
                    p0 = y[max(0, idx - 1)]
                    p1 = y[idx]
                    p2 = y[idx + 1]
                    p3 = y[min(n - 1, idx + 2)]
                    t = (x_smooth[i] - x[idx]) / (x[idx+1] - x[idx]) if x[idx+1] != x[idx] else 0
                    t2, t3 = t * t, t * t * t
                    f1 = -0.5 * t3 + t2 - 0.5 * t
                    f2 = 1.5 * t3 - 2.5 * t2 + 1.0
                    f3 = -1.5 * t3 + 2.0 * t2 + 0.5 * t
                    f4 = 0.5 * t3 - 0.5 * t2
                    y_smooth[i] = p0 * f1 + p1 * f2 + p2 * f3 + p3 * f4
                return x_smooth, y_smooth

            for team_id, scores in final_scores:
                t_data = TEAM_DATA.get(team_id, {'name': team_id, 'primary': '#888888'})

                x_s, y_s = smooth_line(rounds_x, scores)
                ax.plot(x_s, y_s, label=t_data['name'], color=t_data['primary'], linewidth=2.5 if not is_mobile else 1.5)
                ax.scatter(rounds_x, scores, color=t_data['primary'], s=25 if not is_mobile else 9, zorder=5)

                label = get_short_name(t_data['name'])
                elo_val = ingestor.get_team_elo(team_id, season, up_to_round + 1)
                rank_val = ingestor.get_league_rankings(season, up_to_round + 1).get(team_id)
                tier_val = ingestor.get_team_tier(elo_val)
                rank_str = f'#{rank_val}' if rank_val else ''
                full_label = f'{label} {rank_str} [{tier_val}]'

                y_pos = label_y_positions[team_id]
                lbl_fs = 9 if not is_mobile else 8
                lbl_font, lbl_size = self.get_font_and_size(self.prop_sub, lbl_fs)
                ax.text(max_round + 0.15, y_pos, full_label, color=t_data['primary'], va='center', fontsize=lbl_size, fontproperties=lbl_font)
                if abs(y_pos - scores[max_round]) > min_dist * 0.2:
                    ax.plot([max_round, max_round + 0.12], [scores[max_round], y_pos], color=t_data['primary'], linewidth=0.5, alpha=0.5, linestyle=':')

            ax.set_xlim(rounds_x[0] - 0.2, max_round + 1.8)

            title_fs = 13 if is_mobile else 17
            ax.set_title(f"SEASON {season} CUMULATIVE\nTACTICAL POWER LADDER" if is_mobile else f"SEASON {season} CUMULATIVE TACTICAL POWER LADDER",
                         color=self.text_color, fontsize=title_fs, pad=35, fontproperties=self.prop_title)

            fig.text(0.5, 0.92 if not is_mobile else 0.91, "Score = Raw Tactical Output | Rating = Momentum (Baseline: 1500)",
                     ha='center', fontsize=9 if not is_mobile else 7, color=self.sub_text_color, fontproperties=self.prop_body, style='italic')

            ax.set_xlabel("ROUND", color=self.text_color, fontsize=12 if not is_mobile else 10, fontproperties=self.prop_sub)
            ax.set_ylabel("CUMULATIVE TACTICAL SCORE", color=self.text_color, fontsize=12 if not is_mobile else 10, fontproperties=self.prop_sub)

            ax.grid(True, linestyle='--', alpha=0.3, color=self.sub_text_color)
            ax.axhline(0, color=self.text_color, linewidth=1.5, alpha=0.6)

            plt.xticks(rounds_x, [f"R{r}" for r in rounds_x], fontsize=10 if not is_mobile else 8)
            for label in ax.get_xticklabels():
                label.set_fontproperties(self.prop_body)
                label.set_fontsize(10 if not is_mobile else 8)
            for label in ax.get_yticklabels():
                label.set_fontproperties(self.prop_body)
                label.set_fontsize(10 if not is_mobile else 8)

            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            for spine in ax.spines.values():
                spine.set_color(self.text_color)

            plt.tight_layout()
            self.save_and_close(fig, save_path, dpi=120 if not is_mobile else 100, bbox_inches=None)  # fixed aspect — no tight-crop (was collapsing heights)
        except:
            plt.close(fig)
            raise

    def draw_team_journey(self, team_id: str, ingestor, season: int, up_to_round: int, save_path: str, is_mobile: bool = False, mobile_format: str = 'reel', elo: float = 1500.0, rank: int = None, tier: str = None):
        t_data = TEAM_DATA.get(team_id, {'name': team_id, 'primary': '#333333', 'secondary': '#666666'})

        rounds = []
        expected_scores = []
        actual_scores = []
        opponents = []

        matches = []
        for m_id, info in ingestor.match_info.items():
            if info.season == season and info.round <= up_to_round and (info.home == team_id or info.away == team_id):
                matches.append((info.round, m_id))

        matches.sort()

        for r, m_id in matches:
            perf = ingestor.match_performance.get(m_id)
            if not perf:
                continue

            info = ingestor.match_info[m_id]
            is_home = (info.home == team_id)
            opp_id = info.away if is_home else info.home
            opp_name = TEAM_DATA.get(opp_id, {'name': opp_id})['name']

            rounds.append(r)
            opponents.append(opp_name)

            mult = 1.0 if is_home else -1.0
            expected_scores.append(perf.get('expected', 0.0) * mult)
            actual_scores.append(perf.get('actual', 0.0) * mult)

        if not rounds:
            return

        cum_actual = np.cumsum(actual_scores)
        cum_expected = np.cumsum(expected_scores)

        if is_mobile:
            figsize = (9, 16) if mobile_format == 'reel' else (9, 12)
        else:
            figsize = (14, 8)
        fig, ax1 = plt.subplots(figsize=figsize, facecolor=self.bg_color)
        try:
            ax1.set_facecolor(self.bg_color)

            colors = ['#4A7A59' if v > 0 else '#A8463D' for v in actual_scores]
            ax1.bar(rounds, actual_scores, color=colors, alpha=0.4, label='ROUND ACTUAL SCORE', width=0.6)

            ax2 = ax1.twinx()

            def smooth_line(x, y, num_points=300):
                if len(x) < 3:
                    return np.array(x), np.array(y)
                x_smooth = np.linspace(x[0], x[-1], num_points)
                y_smooth = np.zeros(num_points)
                n = len(x)
                for i in range(num_points):
                    idx = np.searchsorted(x, x_smooth[i]) - 1
                    idx = max(0, min(idx, n - 2))
                    p0 = y[max(0, idx - 1)]
                    p1 = y[idx]
                    p2 = y[idx + 1]
                    p3 = y[min(n - 1, idx + 2)]
                    t = (x_smooth[i] - x[idx]) / (x[idx+1] - x[idx]) if x[idx+1] != x[idx] else 0
                    t2, t3 = t * t, t * t * t
                    f1 = -0.5 * t3 + t2 - 0.5 * t
                    f2 = 1.5 * t3 - 2.5 * t2 + 1.0
                    f3 = -1.5 * t3 + 2.0 * t2 + 0.5 * t
                    f4 = 0.5 * t3 - 0.5 * t2
                    y_smooth[i] = p0 * f1 + p1 * f2 + p2 * f3 + p3 * f4
                return x_smooth, y_smooth

            r_smooth, exp_smooth = smooth_line(rounds, cum_expected)
            r_smooth_act, act_smooth = smooth_line(rounds, cum_actual)

            ax2.plot(r_smooth, exp_smooth, color=self.sub_text_color, linestyle='--', linewidth=2 if not is_mobile else 1.5, alpha=0.7, zorder=4)
            ax2.plot(rounds, cum_expected, color=self.sub_text_color, marker='x', markersize=6 if not is_mobile else 4, linestyle='None', alpha=0.7, label='CUMULATIVE EXPECTED')

            ax2.plot(r_smooth_act, act_smooth, color=t_data['primary'], linewidth=4 if not is_mobile else 2.5, zorder=5)
            ax2.plot(rounds, cum_actual, color=t_data['primary'], marker='o', markersize=10 if not is_mobile else 6, linestyle='None', zorder=5, label='CUMULATIVE ACTUAL')

            for i, v in enumerate(actual_scores):
                score_fs = 9 if not is_mobile else 7
                score_font, score_size = self.get_font_and_size(self.prop_sub, score_fs)
                ax1.text(rounds[i], v + (0.5 if v > 0 else -1.5), f"{v:+.1f}",
                         ha='center', va='bottom' if v > 0 else 'top',
                         color=colors[i], fontsize=score_size, fontproperties=score_font)

            title_fs = 13 if is_mobile else 16
            rank_str = f'RANK: {get_ordinal(rank)}' if rank else ''
            tier_str = f' [{tier}]' if tier else ''
            ax1.set_title(f"{t_data['name'].upper()} {rank_str}{tier_str}:\n{season} TACTICAL JOURNEY" if is_mobile else f"{t_data['name'].upper()} {rank_str}{tier_str}: {season} TACTICAL JOURNEY",
                         color=self.text_color, fontsize=title_fs, pad=30, fontproperties=self.prop_title)

            ax1.set_xlabel("ROUND", color=self.text_color, fontsize=12 if not is_mobile else 10, fontproperties=self.prop_sub)
            ax1.set_ylabel("ROUND TACTICAL SCORE", color=self.text_color, fontsize=12 if not is_mobile else 10, fontproperties=self.prop_sub)
            ax2.set_ylabel("CUMULATIVE PERFORMANCE", color=self.text_color, fontsize=12 if not is_mobile else 10, fontproperties=self.prop_sub)

            if is_mobile:
                plt.xticks(rounds, [f"R{r}\n{get_short_name(opp)}" for r, opp in zip(rounds, opponents)], rotation=45, ha='right', rotation_mode='anchor')
            else:
                plt.xticks(rounds, [f"R{r}\n{get_short_name(opp)}" for r, opp in zip(rounds, opponents)])
            for label in ax1.get_xticklabels():
                label.set_fontproperties(self.prop_body)
                label.set_fontsize(10 if not is_mobile else 7)
            for ax in [ax1, ax2]:
                for label in ax.get_yticklabels():
                    label.set_fontproperties(self.prop_body)
                    label.set_fontsize(10 if not is_mobile else 8)

            ax1.grid(True, linestyle=':', alpha=0.4, color=self.sub_text_color)
            ax1.axhline(0, color=self.text_color, linewidth=2, alpha=0.7)

            h1, l1 = ax1.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            legend = ax1.legend(h1 + h2, l1 + l2, facecolor=self.bg_color, edgecolor=self.text_color, loc='upper left', fontsize=10 if not is_mobile else 8)
            for text in legend.get_texts():
                leg_fs = 10 if not is_mobile else 8
                leg_font, leg_size = self.get_font_and_size(self.prop_sub, leg_fs)
                text.set_fontproperties(leg_font)
                text.set_fontsize(leg_size)

            for ax in [ax1, ax2]:
                ax.spines['top'].set_visible(False)
                for spine in ax.spines.values():
                    spine.set_color(self.text_color)
                ax.tick_params(colors=self.text_color)

            plt.tight_layout()
            self.save_and_close(fig, save_path, dpi=120 if not is_mobile else 100, bbox_inches=None)  # fixed aspect — no tight-crop (was collapsing heights)
        except:
            plt.close(fig)
            raise
