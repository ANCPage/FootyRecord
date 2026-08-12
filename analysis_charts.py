"""Analysis charts from the one-store DB (philosophy: the delta decides, the
fit explains — every chart is descriptive, misses shown honestly).

Charts:
  1. predicted-vs-actual margin scatter (2026 + all seasons)
  2. confidence ladder (accuracy per grade tier, all seasons)
  3. trap quadrant (Elo gap vs actual margin — where the model errs)

Usage: python analysis_charts.py
Output: ROUND_IMAGES_UPDATE/2026/ANALYSIS/
"""
import os
import sys
from collections import defaultdict

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))
from Core import results_db, state_store
from Core.mappings import TEAM_MAP

OUT = 'ROUND_IMAGES_UPDATE/2026/ANALYSIS'
os.makedirs(OUT, exist_ok=True)

BG = '#F4F1EA'
TXT = '#3E3A35'
SUB = '#6A655F'
GREEN = '#2F855A'
RED = '#C53030'
BLUE = '#2B6CB0'
AMBER = '#B7791F'

conn = results_db.connect()
rows26 = list(conn.execute(
    "SELECT round, home, away, margin, actual_margin, correct, home_elo, away_elo, grade, match_id"
    " FROM predictions WHERE season=2026 AND actual_margin IS NOT NULL"))
ALL = list(conn.execute(
    "SELECT round, home, away, margin, actual_margin, correct, home_elo, away_elo, grade, match_id"
    " FROM predictions WHERE actual_margin IS NOT NULL"))
conn.close()


def scatter_panel(ax, data, title):
    pred = np.array([r[3] for r in data])
    act = np.array([r[4] for r in data])
    ok = np.array([r[5] for r in data], dtype=bool)
    ax.axhline(0, color=SUB, lw=0.8, alpha=0.4)
    ax.axvline(0, color=SUB, lw=0.8, alpha=0.4)
    lim = max(abs(act.max()), abs(act.min()), 60)
    ax.plot([-60, 60], [-60, 60], color=BLUE, lw=1.2, ls='--', alpha=0.7, label='y = x')
    ax.scatter(pred[ok], act[ok], c=GREEN, s=14, alpha=0.55, label='correct')
    ax.scatter(pred[~ok], act[~ok], c=RED, s=18, alpha=0.7, label='wrong')
    ax.set_title(title, color=TXT, fontsize=12, fontweight='bold')
    ax.set_xlabel('predicted margin (pts)', color=TXT, fontsize=9)
    ax.set_ylabel('actual margin (pts)', color=TXT, fontsize=9)
    ax.set_xlim(-65, 65)
    ax.set_ylim(-lim, lim)
    ax.set_facecolor(BG)
    ax.tick_params(colors=TXT, labelsize=8)
    for s in ax.spines.values():
        s.set_color(SUB)
    # annotate the biggest misses
    worst = sorted([r for r in data if not r[5]], key=lambda r: -abs(r[3]))[:2]
    for r in worst:
        nm = TEAM_MAP.get(r[1], r[1])
        ax.annotate(f'R{r[0]} {nm[:6]}', (r[3], r[4]), xytext=(6, 6),
                    textcoords='offset points', fontsize=7, color=RED, alpha=0.85)
    ax.legend(fontsize=7, loc='lower right', framealpha=0.9)


# ---- Chart 1: scatter ----
fig, axes = plt.subplots(1, 2, figsize=(14, 6.2))
fig.patch.set_facecolor(BG)
scatter_panel(axes[0], rows26, '2026 season (189 games)')
scatter_panel(axes[1], ALL, 'All seasons (1,204 games)')
fig.suptitle('Predicted vs actual margin — the model is honest, here is where it is blind',
             color=TXT, fontsize=13, fontweight='bold')
fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig(f'{OUT}/1_margin_scatter.png', facecolor=BG, dpi=130)
plt.close(fig)

# ---- Chart 2: confidence ladder (all seasons) ----
tiers = defaultdict(lambda: [0, 0])
for r in ALL:
    tiers[r[8]][0] += r[5]
    tiers[r[8]][1] += 1
order = ['F', 'E-', 'E', 'E+', 'D-', 'D', 'D+', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+']
names = ['F', 'E-', 'E', 'E+', 'D-', 'D', 'D+', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+']
accs = [100 * tiers[t][0] / tiers[t][1] for t in order if tiers[t][1]]
ns = [tiers[t][1] for t in order if tiers[t][1]]
labels = [t for t in order if tiers[t][1]]
overall = 100 * sum(tiers[t][0] for t in order) / sum(tiers[t][1] for t in order)
fig, ax = plt.subplots(figsize=(9, 6))
fig.patch.set_facecolor(BG)
ypos = np.arange(len(labels))
colors = [GREEN if a >= overall else (AMBER if a >= 55 else RED) for a in accs]
ax.barh(ypos, accs, color=colors, alpha=0.85, height=0.62)
for y, a, n in zip(ypos, accs, ns):
    ax.text(a + 1, y, f'{a:.0f}% (n={n})', va='center', fontsize=8, color=TXT)
ax.axvline(50, color=SUB, lw=1, ls='--', alpha=0.7)
ax.text(50.5, len(labels) - 0.3, 'coin flip', fontsize=8, color=SUB)
ax.axvline(overall, color=BLUE, lw=1.4, ls='--', alpha=0.9)
ax.text(overall + 0.5, -0.3, f'overall {overall:.1f}%', fontsize=8, color=BLUE)
ax.set_yticks(ypos)
ax.set_yticklabels(labels, color=TXT, fontsize=9)
ax.set_xlim(0, 108)
ax.set_xlabel('winner accuracy (%)', color=TXT, fontsize=9)
ax.set_title('Confidence ladder — every tier is measured, weak ones shown honestly',
             color=TXT, fontsize=12, fontweight='bold')
ax.set_facecolor(BG)
ax.tick_params(colors=TXT, labelsize=8)
for s in ax.spines.values():
    s.set_color(SUB)
fig.tight_layout()
fig.savefig(f'{OUT}/2_confidence_ladder.png', facecolor=BG, dpi=130)
plt.close(fig)

# ---- Chart 3: trap quadrant (all seasons) ----
# home_elo/away_elo can be NULL in older rows — join the state's elo_history
sconn = state_store.connect()
elo_at = {}
for team, m_id, elo in sconn.execute("SELECT team, m_id, elo FROM elo_history"):
    elo_at.setdefault(m_id, {})[team] = elo
sconn.close()


def gap(r):
    if r[6] is not None and r[7] is not None:
        return r[6] - r[7]
    m = elo_at.get(r[9], {})
    return m.get(r[1], 0.0) - m.get(r[2], 0.0)


elo_gap = np.array([gap(r) for r in ALL])
act = np.array([r[4] for r in ALL])
ok = np.array([r[5] for r in ALL], dtype=bool)
fig, ax = plt.subplots(figsize=(10, 6.2))
fig.patch.set_facecolor(BG)
# trap zone: clear favorite by Elo (>= 45 pts) that LOST at home
ax.axvspan(45, elo_gap.max() + 10, ymin=0, ymax=0.5, color=RED, alpha=0.06)
ax.axvspan(-(elo_gap.max() + 10), -45, ymin=0.5, ymax=1, color=RED, alpha=0.06)
ax.axhline(0, color=SUB, lw=0.8, alpha=0.4)
ax.axvline(0, color=SUB, lw=0.8, alpha=0.4)
ax.scatter(elo_gap[ok], act[ok], c=GREEN, s=14, alpha=0.5, label='correct')
ax.scatter(elo_gap[~ok], act[~ok], c=RED, s=18, alpha=0.75, label='wrong')
ax.set_title('The trap zone — strong favourites that lost (all seasons)',
             color=TXT, fontsize=12, fontweight='bold')
ax.set_xlabel('Elo gap, home minus away (pts)', color=TXT, fontsize=9)
ax.set_ylabel('actual margin, home frame (pts)', color=TXT, fontsize=9)
ax.text(elo_gap.max() - 8, -ax.get_ylim()[1] * 0.92, 'favourite lost\nat home', fontsize=8,
        color=RED, ha='right', alpha=0.8)
ax.set_facecolor(BG)
ax.tick_params(colors=TXT, labelsize=8)
for s in ax.spines.values():
    s.set_color(SUB)
worst = sorted([r for r in ALL if not r[5]], key=lambda r: -abs(gap(r)))[:2]
for r in worst:
    nm = TEAM_MAP.get(r[2], r[2])
    ax.annotate(f'R{r[0]} {nm[:7]} won', (gap(r), r[4]), xytext=(6, 6),
                textcoords='offset points', fontsize=7, color=RED)
ax.legend(fontsize=7, loc='upper left', framealpha=0.9)
fig.tight_layout()
fig.savefig(f'{OUT}/3_trap_quadrant.png', facecolor=BG, dpi=130)
plt.close(fig)

print(f'charts written to {OUT}/')
for f in sorted(os.listdir(OUT)):
    print(' ', f)
