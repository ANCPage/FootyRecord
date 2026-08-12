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


# ---- Panel A: the scatter with a narrative ----
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw={'width_ratios': [1, 1]})
fig.patch.set_facecolor(BG)

rows = rows26  # 2026 games from main
pred = np.array([r[3] for r in rows])
act = np.array([r[4] for r in rows])
ok = np.array([r[5] for r in rows], dtype=bool)

# zone labels
ax.axvspan(-65, 0, 0, 0.5, color=RED, alpha=0.05)
ax.axvspan(0, 65, 0.5, 1, color=RED, alpha=0.05)
ax.text(60, -118, 'THE UPSETS\nmodel said home,\naway won', fontsize=8, color=RED, ha='right', alpha=0.85)
ax.text(-60, 118, 'THE UPSETS\nmodel said away,\nhome won', fontsize=8, color=RED, ha='left', alpha=0.85, va='top')
ax.axhline(0, color=SUB, lw=0.8, alpha=0.5)
ax.axvline(0, color=SUB, lw=0.8, alpha=0.5)
lim = 130
ax.plot([-65, 65], [-65, 65], color=BLUE, lw=1.2, ls='--', alpha=0.6)
ax.scatter(pred[ok], act[ok], c=GREEN, s=16, alpha=0.55)
ax.scatter(pred[~ok], act[~ok], c=RED, s=26, alpha=0.85, zorder=3)

# landmark annotations (team names, not ids)
def nm(t):
    return TEAM_MAP.get(t, t).replace(' ', '\n') if False else TEAM_MAP.get(t, t)

landmarks = [
    # (find by round+teams) — hardcode the season's stories
]
for r in rows:
    if r[0] == 13 and r[2] == 'CD_T60' and r[4] < -100:
        ax.annotate("R13: Freo beat North by 123\n(model said 30)", (r[3], r[4]),
                    xytext=(10, -6), textcoords='offset points', fontsize=8, color=RED,
                    arrowprops=dict(arrowstyle='->', color=RED, lw=0.8))
    if r[0] == 22 and r[1] == 'CD_T10' and r[2] == 'CD_T120':
        ax.annotate("R22: Richmond upset Adelaide\n(pred +49, actual -4)", (r[3], r[4]),
                    xytext=(-14, 6), textcoords='offset points', fontsize=8, color=RED,
                    arrowprops=dict(arrowstyle='->', color=RED, lw=0.8))
    if r[0] == 22 and r[1] == 'CD_T70' and r[2] == 'CD_T50':
        ax.annotate("R22: Geelong by 59\n(model said 52)", (r[3], r[4]),
                    xytext=(10, 6), textcoords='offset points', fontsize=8, color=GREEN,
                    arrowprops=dict(arrowstyle='->', color=GREEN, lw=0.8))
    if r[0] == 6 and r[1] == 'CD_T100' and r[4] > 70:
        ax.annotate("R6: North by 75", (r[3], r[4]), xytext=(8, 4),
                    textcoords='offset points', fontsize=8, color=GREEN,
                    arrowprops=dict(arrowstyle='->', color=GREEN, lw=0.8))
    if r[0] == 20 and r[1] == 'CD_T80' and r[4] > 80:
        ax.annotate("R20: Hawthorn by 88\n(model said 49)", (r[3], r[4]),
                    xytext=(8, -14), textcoords='offset points', fontsize=8, color=GREEN,
                    arrowprops=dict(arrowstyle='->', color=GREEN, lw=0.8))
    if r[0] == 5 and r[1] == 'CD_T20' and r[2] == 'CD_T100':
        ax.annotate("R5: Brisbane by 18", (r[3], r[4]), xytext=(8, -14),
                    textcoords='offset points', fontsize=8, color=GREEN,
                    arrowprops=dict(arrowstyle='->', color=GREEN, lw=0.8))

ax.set_title('2026 — every game, model vs reality\n(green = right, red = upsets, line = perfect call)',
             color=TXT, fontsize=11, fontweight='bold')
ax.set_xlabel('predicted margin (pts, home frame)', color=TXT, fontsize=9)
ax.set_ylabel('actual margin (pts, home frame)', color=TXT, fontsize=9)
ax.set_xlim(-65, 65)
ax.set_ylim(-lim, lim)
ax.set_facecolor(BG)
ax.tick_params(colors=TXT, labelsize=8)
for s in ax.spines.values():
    s.set_color(SUB)

# ---- Panel B: the season strip (the narrative) ----
rounds = defaultdict(lambda: [0, 0, []])  # rnd -> [correct, total, margins]
for r in rows:
    rounds[r[0]][0] += r[5]
    rounds[r[0]][1] += 1
    rounds[r[0]][2].append(r)

rnds = sorted(rounds)
x = np.arange(len(rnds))
accs = [100 * rounds[r][0] / rounds[r][1] for r in rnds]
ns = [rounds[r][1] for r in rnds]
cols = [GREEN if rounds[r][0] >= rounds[r][1] / 2 else RED for r in rnds]
bars = ax2.bar(x, accs, color=cols, alpha=0.85, width=0.66)
for xi, a, n, r in zip(x, accs, ns, rnds):
    ax2.text(xi, a + 1.5, f'{rounds[r][0]}/{n}', ha='center', fontsize=7, color=TXT)
ax2.axhline(66.4, color=BLUE, lw=1.2, ls='--', alpha=0.85)
ax2.text(len(rnds) - 0.4, 67.5, 'model average 66.4%', fontsize=8, color=BLUE, ha='right')
ax2.axhline(50, color=SUB, lw=0.8, ls=':', alpha=0.7)
# story markers
ax2.annotate('R15–R21 purple patch\n47/59 (80%)', xy=(18, 74), xytext=(14.5, 88),
             fontsize=8, color=GREEN, arrowprops=dict(arrowstyle='->', color=GREEN, lw=0.8))
ax2.annotate('R22 stumble 4/9', xy=(21.5, 44), xytext=(17.5, 26),
             fontsize=8, color=RED, arrowprops=dict(arrowstyle='->', color=RED, lw=0.8))
ax2.set_xticks(x)
ax2.set_xticklabels([f'R{r}' for r in rnds], fontsize=7, color=TXT, rotation=45)
ax2.set_ylim(0, 100)
ax2.set_title('2026 — the season as a story\n(accuracy per round, green ≥ 50%)',
              color=TXT, fontsize=11, fontweight='bold')
ax2.set_ylabel('round accuracy (%)', color=TXT, fontsize=9)
ax2.set_facecolor(BG)
ax2.tick_params(colors=TXT, labelsize=8)
for s in ax2.spines.values():
    s.set_color(SUB)

fig.tight_layout()
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
    wnm = TEAM_MAP.get(r[2], r[2])
    ax.annotate(f'R{r[0]} {wnm[:7]} won', (gap(r), r[4]), xytext=(6, 6),
                textcoords='offset points', fontsize=7, color=RED)
ax.legend(fontsize=7, loc='upper left', framealpha=0.9)
fig.tight_layout()
fig.savefig(f'{OUT}/3_trap_quadrant.png', facecolor=BG, dpi=130)
plt.close(fig)

print(f'charts written to {OUT}/')
for f in sorted(os.listdir(OUT)):
    print(' ', f)
