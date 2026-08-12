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
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

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
    "SELECT round, home, away, margin, actual_margin, correct, match_id"
    " FROM predictions WHERE season=2026 AND actual_margin IS NOT NULL"))
ALL = list(conn.execute(
    "SELECT round, home, away, margin, actual_margin, correct, home_elo, away_elo, grade, match_id"
    " FROM predictions WHERE actual_margin IS NOT NULL"))
conn.close()


def name(t):
    return TEAM_MAP.get(t, t)


# ================= Chart 1: the season narrative =================
by_round = defaultdict(list)
for r in rows26:
    by_round[r[0]].append(r[5])
rnds = sorted(by_round)

# cumulative + rolling-5 accuracy
cum, c, t = [], 0, 0
for r in rnds:
    c += sum(by_round[r])
    t += len(by_round[r])
    cum.append(100 * c / t)
roll = []
for i, r in enumerate(rnds):
    w = [x for j, rr in enumerate(rnds) if i - 4 <= j <= i for x in by_round[rr]]
    roll.append(100 * sum(w) / len(w))

fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 9),
                              gridspec_kw={'height_ratios': [1.15, 1], 'hspace': 0.42})
fig.patch.set_facecolor(BG)

# --- Panel A: the accuracy arc ---
ax.plot(rnds, cum, '-o', color=BLUE, lw=2.2, ms=5, label='cumulative accuracy')
ax.plot(rnds, roll, '-', color=GREEN, lw=1.6, alpha=0.85, label='rolling-5 accuracy')
ax.axhline(66.4, color=SUB, lw=1.1, ls='--', alpha=0.75)
ax.text(rnds[0] + 0.3, 67.3, 'all-seasons average 66.4%', fontsize=8, color=SUB)
ax.axhline(50, color=SUB, lw=0.8, ls=':', alpha=0.6)
# the story markers
ax.annotate('R15–R21 purple patch\n47/59 (80%) — the line steepens',
            xy=(21, 74.5), xytext=(13.5, 84), fontsize=9, color=GREEN,
            arrowprops=dict(arrowstyle='->', color=GREEN, lw=1))
ax.annotate('R22 stumble 4/9 —\nthe line dips', xy=(22, 70.4), xytext=(18.2, 58),
            fontsize=9, color=RED, arrowprops=dict(arrowstyle='->', color=RED, lw=1))
ax.scatter([22], [cum[-1]], color=BLUE, s=60, zorder=5)
ax.text(22, cum[-1] + 1.6, f'{cum[-1]:.1f}% (133/189)', fontsize=10,
        fontweight='bold', color=BLUE, ha='center')
ax.set_xticks(rnds)
ax.set_xticklabels([f'R{r}' for r in rnds], fontsize=7, color=TXT, rotation=45)
ax.set_ylim(45, 95)
ax.set_ylabel('accuracy (%)', color=TXT, fontsize=9)
ax.set_title('The season, as an arc — cumulative and rolling accuracy through 2026',
             color=TXT, fontsize=12, fontweight='bold')
ax.legend(fontsize=8, loc='lower right', framealpha=0.9)
ax.set_facecolor(BG)
ax.tick_params(colors=TXT, labelsize=8)
for s in ax.spines.values():
    s.set_color(SUB)

# --- Panel B: the game strip (calls in order) ---
for i, r in enumerate(rnds):
    for j, correct in enumerate(by_round[r]):
        ax2.add_patch(Rectangle((i - 0.4, j - 0.4), 0.8, 0.8,
                                facecolor=GREEN if correct else RED, alpha=0.85))
# purple patch band
ax2.axvspan(15 - 0.5, 21 + 0.5, color=GREEN, alpha=0.06)
ax2.text(18, 8.6, 'R15–R21 purple patch', fontsize=8, color=GREEN, ha='center')
ax2.axvspan(22 - 0.5, 22 + 0.5, color=RED, alpha=0.08)
ax2.text(22, -1.6, 'R22', fontsize=7, color=RED, ha='center')
# y: game slots (most rounds have 9)
max_games = max(len(v) for v in by_round.values())
ax2.set_xlim(-0.6, len(rnds) - 0.4)
ax2.set_ylim(-0.6, max_games - 0.4)
ax2.set_yticks(range(max_games))
ax2.set_yticklabels([str(i + 1) for i in range(max_games)], fontsize=7, color=TXT)
ax2.set_xticks(range(len(rnds)))
ax2.set_xticklabels([f'R{r}' for r in rnds], fontsize=7, color=TXT, rotation=45)
ax2.set_ylabel('game in round', color=TXT, fontsize=8)
ax2.set_title('Every call, in order — green right, red wrong (streaks are the story)',
              color=TXT, fontsize=11, fontweight='bold')
ax2.set_facecolor(BG)
ax2.tick_params(colors=TXT, labelsize=7)
for s in ax2.spines.values():
    s.set_color(SUB)

fig.savefig(f'{OUT}/1_season_arc.png', facecolor=BG, dpi=130)
plt.close(fig)

# ================= Chart 2: confidence ladder (all seasons) =================
tiers = defaultdict(lambda: [0, 0])
for r in ALL:
    tiers[r[8]][0] += r[5]
    tiers[r[8]][1] += 1
order = ['F', 'E-', 'E', 'E+', 'D-', 'D', 'D+', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+']
labels = [t for t in order if tiers[t][1]]
accs = [100 * tiers[t][0] / tiers[t][1] for t in labels]
ns = [tiers[t][1] for t in labels]
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

# ================= Chart 3: trap quadrant (all seasons) =================
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
ax.set_facecolor(BG)
ax.tick_params(colors=TXT, labelsize=8)
for s in ax.spines.values():
    s.set_color(SUB)
worst = sorted([r for r in ALL if not r[5]], key=lambda r: -abs(gap(r)))[:2]
for r in worst:
    wnm = name(r[2])
    ax.annotate(f'R{r[0]} {wnm[:7]} won', (gap(r), r[4]), xytext=(6, 6),
                textcoords='offset points', fontsize=7, color=RED)
ax.legend(fontsize=7, loc='upper left', framealpha=0.9)
fig.tight_layout()
fig.savefig(f'{OUT}/3_trap_quadrant.png', facecolor=BG, dpi=130)
plt.close(fig)

# clean up the old narrative scatter name (renamed to the arc chart)
old = f'{OUT}/1_margin_scatter.png'
if os.path.exists(old):
    os.remove(old)

# ================= Chart 4: accuracy by confidence (the punch) =================
# binned by |predicted margin|; left axis = accuracy, right axis = share of picks
bins = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 40), (40, 100)]
bacc = []
bshare = []
bn = []
for lo, hi in bins:
    g = [r for r in ALL if lo <= abs(r[3]) < hi]
    if not g:
        bacc.append(0)
        bshare.append(0)
        bn.append(0)
        continue
    bacc.append(100 * sum(r[5] for r in g) / len(g))
    bshare.append(100 * len(g) / len(ALL))
    bn.append(len(g))

fig, ax = plt.subplots(figsize=(10, 5.8))
fig.patch.set_facecolor(BG)
xpos = np.arange(len(bins))
labels = [f'{lo}–{hi - 1}' if hi < 100 else f'{lo}+' for lo, hi in bins]
bars = ax.bar(xpos, bshare, color=BLUE, alpha=0.22, width=0.6, label='share of picks (right axis)')
ax.set_ylabel('share of all picks (%)', color=BLUE, fontsize=9)
ax.set_ylim(0, max(bshare) * 2.1)
ax.tick_params(axis='y', colors=BLUE, labelsize=8)
ax2 = ax.twinx()
ax2.plot(xpos, bacc, '-o', color=GREEN, lw=2.2, ms=6, label='accuracy (left axis)')
ax2.axhline(66.4, color=SUB, lw=1, ls='--', alpha=0.7)
ax2.text(len(bins) - 0.4, 67.5, 'overall 66.4%', fontsize=8, color=SUB, ha='right')
ax2.axhline(50, color=SUB, lw=0.8, ls=':', alpha=0.6)
ax2.set_ylabel('winner accuracy (%)', color=GREEN, fontsize=9)
ax2.set_ylim(40, 100)
ax2.tick_params(axis='y', colors=GREEN, labelsize=8)
for xi, (a, n, sh) in enumerate(zip(bacc, bn, bshare)):
    ax2.text(xi, a + 1.8, f'{a:.0f}%', ha='center', fontsize=9, fontweight='bold', color=GREEN)
    ax.text(xi, sh + 0.8, f'{sh:.0f}%', ha='center', fontsize=7, color=BLUE)
ax.set_xticks(xpos)
ax.set_xticklabels(labels, color=TXT, fontsize=8)
ax.set_xlabel('predicted margin, magnitude (pts)', color=TXT, fontsize=9)
ax.set_title('The punch — accuracy rises with confidence, and here is how often\n'
             'each confidence level actually occurs (all seasons, 1,204 games)',
             color=TXT, fontsize=11.5, fontweight='bold')
ax.set_facecolor(BG)
ax.tick_params(colors=TXT, labelsize=8)
for s in ax.spines.values():
    s.set_color(SUB)
fig.tight_layout()
fig.savefig(f'{OUT}/4_accuracy_by_confidence.png', facecolor=BG, dpi=130)
plt.close(fig)

print(f'charts written to {OUT}/')
for f in sorted(os.listdir(OUT)):
    print(' ', f)
