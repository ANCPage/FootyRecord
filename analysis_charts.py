"""Analysis charts from the one-store DB (philosophy: the delta decides, the
fit explains — every chart is descriptive, misses shown honestly).

Charts:
  1. the season narrative — accuracy arc + game strip (2026)
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
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))
from Core.config import FONTS_DIR
from Core.mappings import TEAM_MAP
from Core.results_db import connect
from Core.theme import BG_COLOR, SUB_TEXT_COLOR, TEXT_COLOR

# match the card system's typography (audit S2/S3)
fm.fontManager.addfont(os.path.join(FONTS_DIR, 'Roboto-Regular.ttf'))
fm.fontManager.addfont(os.path.join(FONTS_DIR, 'FasterOne.ttf'))
plt.rcParams['font.family'] = 'Roboto'
plt.rcParams['axes.unicode_minus'] = False

OUT = 'ROUND_IMAGES_UPDATE/2026/ANALYSIS'
os.makedirs(OUT, exist_ok=True)

BG, TXT, SUB = BG_COLOR, TEXT_COLOR, SUB_TEXT_COLOR
GREEN = '#2F855A'
RED = '#C53030'
BLUE = '#2B6CB0'
AMBER = '#B7791F'

conn = connect()
rows26 = list(conn.execute(
    "SELECT round, home, away, margin, actual_margin, correct, match_id, grade"
    " FROM predictions WHERE season=2026 AND actual_margin IS NOT NULL"))
ALL = list(conn.execute(
    "SELECT round, home, away, margin, actual_margin, correct, home_elo, away_elo, grade, match_id"
    " FROM predictions WHERE actual_margin IS NOT NULL"))
conn.close()


def name(t):
    return TEAM_MAP.get(t, t)


# ================= Chart 1: the season story (ONE mobile-sized portrait) =================
# brand header · Panel A arc · Panel B strip · Panel C confidence · Panel D tiers · footer
tiers26 = defaultdict(lambda: [0, 0])
for r in rows26:
    tiers26[r[7]][0] += r[5]
    tiers26[r[7]][1] += 1
order = ['F', 'E-', 'E', 'E+', 'D-', 'D', 'D+', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+']
tlabels = [t for t in order if tiers26[t][1]]
taccs = [100 * tiers26[t][0] / tiers26[t][1] for t in tlabels]
tns = [tiers26[t][1] for t in tlabels]
overall26 = 100 * sum(tiers26[t][0] for t in tlabels) / sum(tiers26[t][1] for t in tlabels)

# per-round data: calls, cumulative + rolling-5 accuracy, confidence (avg |margin|)
by_round = defaultdict(list)
for r in rows26:
    by_round[r[0]].append(r[5])
rnds = sorted(by_round)
cum, c, t = [], 0, 0
for r in rnds:
    c += sum(by_round[r])
    t += len(by_round[r])
    cum.append(100 * c / t)
roll = []
for i, r in enumerate(rnds):
    w = [x for j, rr in enumerate(rnds) if i - 4 <= j <= i for x in by_round[rr]]
    roll.append(100 * sum(w) / len(w))
conf = []
for r in rnds:
    gm = [x for x in rows26 if x[0] == r]
    conf.append(sum(abs(x[3]) for x in gm) / len(gm))

fig, (ax, ax2, ax4) = plt.subplots(
    3, 1, figsize=(7.5, 13.4),
    gridspec_kw={'height_ratios': [1.0, 0.34, 0.72], 'hspace': 0.5})
fig.patch.set_facecolor(BG)
# brand header (audit S1)
fig.text(0.5, 0.972, 'FOOTYRECORD', ha='center', va='top', fontsize=26,
         color=TXT, family='Faster One')
fig.text(0.5, 0.945, 'THE 2026 SEASON, AS THE MODEL SAW IT', ha='center', va='top',
         fontsize=10, color=SUB, family='Roboto')

# --- Panel 1: the accuracy arc ---
ax.plot(rnds, cum, '-o', color=BLUE, lw=2.2, ms=4, label='Cumulative accuracy')
ax.plot(rnds, roll, '-', color=GREEN, lw=1.5, alpha=0.85, label='Rolling 5-round accuracy')
ax.axhline(66.4, color=SUB, lw=1.1, ls='--', alpha=0.75)
ax.text(rnds[0] + 0.3, 67.4, 'All-seasons average 66.4%', fontsize=7.5, color=SUB)
ax.axhline(50, color=SUB, lw=0.8, ls=':', alpha=0.6)
ax.scatter([22], [cum[-1]], color=BLUE, s=50, zorder=5)
ax.text(22, cum[-1] + 1.6, f'{cum[-1]:.1f}% (133/189)', fontsize=9.5,
        color=BLUE, ha='center')
ax.legend(fontsize=8, loc='upper left', framealpha=0.9)
ax.set_xlim(-0.6, len(rnds) - 0.4)
ax.set_xticks(rnds[::2])
ax.set_xticklabels([])  # labels live on the strip below (shared time axis)
ax.set_ylim(45, 95)
ax.set_ylabel('accuracy (%)', color=TXT, fontsize=8)
ax.set_title('1 · Season record, round by round', color=TXT, fontsize=12, loc='left')
ax.set_facecolor(BG)
ax.tick_params(colors=TXT, labelsize=7)
for s in ax.spines.values():
    s.set_color(SUB)

# --- Panel 2: the strip as a rug under the arc (shared time axis) ---
for i, r in enumerate(rnds):
    for j, correct in enumerate(by_round[r]):
        ax2.add_patch(Rectangle((i - 0.4, j - 0.4), 0.8, 0.8,
                                facecolor=GREEN if correct else RED, alpha=0.9))
max_games = max(len(v) for v in by_round.values())
ax2.set_xlim(-0.6, len(rnds) - 0.4)
ax2.set_ylim(-0.6, max_games - 0.4)
ax2.set_yticks(range(max_games))
ax2.set_yticklabels([str(i + 1) for i in range(max_games)], fontsize=6, color=TXT)
ax2.set_xticks(rnds[::2])
ax2.set_xticklabels([f'R{r}' for r in rnds[::2]], fontsize=6.5, color=TXT)
ax2.set_ylabel('game', color=TXT, fontsize=7)
ax2.set_title('2 · Every round\u2019s calls', color=TXT, fontsize=11, loc='left')
ax2.set_facecolor(BG)
ax2.tick_params(colors=TXT, labelsize=6)
for s in ax2.spines.values():
    s.set_color(SUB)

# --- Panel D: accuracy by confidence tier ---
xpos4 = np.arange(len(tlabels))
colors4 = [GREEN if a >= overall26 else (AMBER if a >= 55 else RED) for a in taccs]
ax4.bar(xpos4, taccs, color=colors4, alpha=0.85, width=0.62)
for xi, (a, n) in enumerate(zip(taccs, tns)):
    ax4.text(xi, a + 1.5, f'{a:.0f}%', ha='center', fontsize=8, color=TXT)
    ax4.text(xi, 1.5, f'n={n}', ha='center', fontsize=6.5, color=BG)
ax4.axhline(overall26, color=BLUE, lw=1.3, ls='--', alpha=0.9)
ax4.axhline(50, color=SUB, lw=0.8, ls=':', alpha=0.6)
ax4.legend(handles=[Patch(color=GREEN, label='At or above season average'),
                    Patch(color=AMBER, label='Below season average'),
                    Patch(color=RED, label='At chance level (≈50%)')],
           fontsize=7.5, loc='upper left', framealpha=0.9, ncol=1)
ax4.set_xticks(xpos4)
ax4.set_xticklabels(tlabels, color=TXT, fontsize=8)
ax4.set_ylim(0, 110)
ax4.set_ylabel('accuracy (%)', color=TXT, fontsize=8)
ax4.set_title('3 · Accuracy by confidence level', color=TXT, fontsize=12, loc='left')
ax4.set_facecolor(BG)
ax4.tick_params(colors=TXT, labelsize=7)
for s in ax4.spines.values():
    s.set_color(SUB)

# honesty footer (audit T3)
fig.text(0.5, 0.012,
         'Every pick uses only the information available before the round · draws count as misses',
         ha='center', va='bottom', fontsize=8, color=SUB)

fig.savefig(f'{OUT}/1_season_story.png', facecolor=BG, dpi=130)
plt.close(fig)
