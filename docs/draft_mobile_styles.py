#!/usr/bin/env python3
"""Draft mobile design systems for review — 4 directions x 2 cards (R24 G8 + R24 tips).
Output: ROUND_IMAGES_UPDATE/2026/DRAFTS/DRAFT_<style>_<card>.png (900x1200).
Data: results DB only (read-only; the walk-forward record)."""
import json, sqlite3, sys, os, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.font_manager import FontProperties, fontManager

sys.path.insert(0, '/mnt/projects/FootyRecord')
from Core.mappings import TEAM_DATA  # noqa: E402

ROOT = '/mnt/projects/FootyRecord'
fontManager.addfont(f'{ROOT}/downloaded_fonts/Roboto-Regular.ttf')
fontManager.addfont(f'{ROOT}/downloaded_fonts/FasterOne.ttf')
FASTER = FontProperties(fname=f'{ROOT}/downloaded_fonts/FasterOne.ttf')
ROBOTO = FontProperties(fname=f'{ROOT}/downloaded_fonts/Roboto-Regular.ttf')
plt.rcParams['font.family'] = 'Roboto'

OUT = f'{ROOT}/ROUND_IMAGES_UPDATE/2026/DRAFTS'
os.makedirs(OUT, exist_ok=True)

CREAM = '#F4F1EA'; INK = '#3E3A35'; SUB = '#6A655F'; WHITE = '#FFFFFF'
NAVY = '#14213D'; DARK = '#141414'; CARD = '#FFFFFF'; BORDER = '#D8D2C6'

NODE = {'A1': (-60, 40), 'B1': (-30, 45), 'C1': (0, 50), 'D1': (30, 45), 'E1': (60, 40),
        'A2': (-70, 0), 'B2': (-35, 0), 'C2': (0, 0), 'D2': (35, 0), 'E2': (70, 0),
        'A3': (-60, -40), 'B3': (-30, -45), 'C3': (0, -50), 'D3': (30, -45), 'E3': (60, -40),
        'SCORE': (85, 0), 'AWAY_G': (-85, 0)}
ZONE = {'A1': 'LBP', 'B1': 'LHB', 'C1': 'LW', 'D1': 'LHF', 'E1': 'LFP',
        'A2': 'FB', 'B2': 'CHB', 'C2': 'C', 'D2': 'CHF', 'E2': 'FF',
        'A3': 'RBP', 'B3': 'RHB', 'C3': 'RW', 'D3': 'RHF', 'E3': 'RFP'}

def blend(h1, h2, w):
    a = [int(h1[i:i+2], 16) for i in (1, 3, 5)]; b = [int(h2[i:i+2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(a[i]*w + b[i]*(1-w)) for i in range(3))

def team_color(tid, key='primary'):
    return TEAM_DATA.get(tid, {}).get(key, '#888888')

# ---------------- data ----------------
conn = sqlite3.connect('/home/austin/footyrecord-results/footyrecord.db')
row = conn.execute("SELECT * FROM predictions WHERE match_id='CD_M20260142408'").fetchone()
cols = [d[0] for d in conn.execute("SELECT * FROM predictions WHERE match_id='CD_M20260142408'").description]
R = dict(zip(cols, row))
H, A = R['home'], R['away']
HN, AN = TEAM_DATA[H]['name'], TEAM_DATA[A]['name']
HC, AC = team_color(H), team_color(A)
L_AC = blend(AC, '#FFFFFF', 0.55)  # light away colour for dark bgs
delta = json.loads(R['delta'])
edges = sorted(((abs(v), k, v) for k, v in delta.items()), reverse=True)[:6]
tips = conn.execute("SELECT home, away, margin, winner, correct FROM predictions WHERE season=2026 AND round=24 ORDER BY match_id").fetchall()

def new_fig():
    return plt.figure(figsize=(9, 12), dpi=100, facecolor='none')

def save(fig, name):
    fig.savefig(f'{OUT}/{name}', dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    print('wrote', name)

def draw_field(ax, xlim=(-95, 95), ylim=(-75, 75), lw=1.2, color='#444'):
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect('equal'); ax.axis('off')
    ax.add_patch(patches.Ellipse((0, 0), 170, 130, fill=False, ec=color, lw=lw))
    ax.add_patch(patches.Rectangle((-25, -25), 50, 50, fill=False, ec=color, lw=0.8, alpha=0.6))
    ax.add_patch(patches.Circle((0, 0), 5, fill=False, ec=color, lw=0.8, alpha=0.6))
    ax.add_patch(patches.Arc((70, 0), 100, 100, theta1=90, theta2=270, ec=color, lw=0.8, ls='--', alpha=0.5))
    ax.add_patch(patches.Arc((-70, 0), 100, 100, theta1=270, theta2=90, ec=color, lw=0.8, ls='--', alpha=0.5))
    ax.plot([85, 85], [-5, 5], color=color, lw=2.5)
    ax.plot([-85, -85], [-5, 5], color=color, lw=2.5)

def split_edge(k):
    return tuple(k.split('->')) if isinstance(k, str) else (k.source, k.target)

def draw_arrows(ax, edges, home_c, away_c, top=6, lw_scale=3.0):
    for _, edge, score in edges[:top]:
        s, t = split_edge(edge)
        p1 = NODE.get(s); p2 = NODE.get(t)
        if not p1 or not p2:
            continue
        c = home_c if score > 0 else away_c
        ax.annotate('', xy=p2, xytext=p1,
                    arrowprops=dict(arrowstyle='-|>', color=c, lw=min(6, 1 + abs(score) * lw_scale),
                                    shrinkA=8, shrinkB=8, alpha=0.85))

def draw_zones(ax, involved, fs=6.5, c='#444'):
    for name, (x, y) in NODE.items():
        if name in ('SCORE', 'AWAY_G') or (involved and name not in involved):
            continue
        ax.add_patch(patches.Circle((x, y), 4.5, fc='white', ec=c, lw=0.8, zorder=3))
        ax.text(x, y, ZONE.get(name, name), ha='center', va='center', fontsize=fs, color=c, zorder=4)

def involved_nodes(edges, n=6):
    nodes = set()
    for _, e, _ in edges[:n]:
        nodes.add(split_edge(e)[0]); nodes.add(split_edge(e)[1])
    return {x for x in nodes if x in ZONE}

def banner(fig, text, sub=None, y=0.06, h=0.075, bg=INK, fg=WHITE, fs=30, sub_fs=13):
    fig.add_artist(patches.Rectangle((0.03, y), 0.94, h, facecolor=bg, edgecolor='none', zorder=5))
    fig.text(0.5, y + h/2 + (0.012 if sub else 0), text, ha='center', va='center', fontsize=fs,
             color=fg, zorder=6, fontproperties=FASTER if fs >= 26 else ROBOTO)
    if sub:
        fig.text(0.5, y + h/2 - 0.022, sub, ha='center', va='center', fontsize=sub_fs, color=fg, zorder=6, alpha=0.85)

# ============ STYLE A — CLEAN SHEET (cream, minimal, data-dense) ============
def style_a_matchup():
    fig = new_fig(); fig.patch.set_facecolor(CREAM)
    fig.text(0.5, 0.945, 'MATCHUP', ha='center', fontsize=40, color=INK, fontproperties=FASTER)
    fig.text(0.5, 0.905, f'{HN.upper()}  VS  {AN.upper()}', ha='center', fontsize=17, color=SUB)
    # rank/tier chips
    fig.text(0.5, 0.875, f'{HN} — RANK {R["home_rank"]} [{R["home_tier"]}]  ·  {AN} — RANK {R["away_rank"]} [{R["away_tier"]}]',
             ha='center', fontsize=11, color=SUB)
    # one ownership field
    ax = fig.add_axes([0.08, 0.42, 0.84, 0.42])
    draw_field(ax)
    draw_arrows(ax, edges, HC, AC)
    draw_zones(ax, involved_nodes(edges))
    # top battles
    ax2 = fig.add_axes([0.08, 0.13, 0.84, 0.26]); ax2.axis('off')
    ax2.text(0, 1.0, 'TOP 12 TACTICAL BATTLES', fontsize=12, color=INK, fontweight='bold')
    for i, (_, e, v) in enumerate(sorted(((abs(v), k, v) for k, v in delta.items()), reverse=True)[:12]):
        y = 0.88 - i * 0.073
        owner = HN if v > 0 else AN
        ax2.text(0, y, f'{split_edge(e)[0]} -> {split_edge(e)[1]}', fontsize=9, color=INK)
        ax2.text(0.55, y, f'{v:+.3f}', fontsize=9, color=HC if v > 0 else AC, ha='right')
        ax2.text(0.62, y, owner, fontsize=9, color=SUB)
    banner(fig, f'{HN.upper()} WINNER', sub=f'MARGIN {R["margin"]:+.0f} PTS  ·  NET DELTA {R["net_delta"]:+.2f}', bg=INK)
    save(fig, 'DRAFT_A_matchup.png')

def style_a_tips():
    fig = new_fig(); fig.patch.set_facecolor(CREAM)
    fig.text(0.5, 0.95, 'ROUND 24 TIPS', ha='center', fontsize=36, color=INK, fontproperties=FASTER)
    fig.text(0.5, 0.915, 'SEASON 2026  ·  147/207 (71.0%)', ha='center', fontsize=13, color=SUB)
    ax = fig.add_axes([0.07, 0.09, 0.86, 0.80]); ax.axis('off')
    for i, (h, a, m, w, ok) in enumerate(tips):
        y = 0.94 - i * 0.095
        hn, an = TEAM_DATA[h]['name'], TEAM_DATA[a]['name']
        pick = hn if m >= 0 else an
        ax.text(0, y, f'G{i+1}', fontsize=10, color=SUB, va='center')
        ax.text(0.08, y, f'{hn} v {an}', fontsize=12, color=INK, va='center')
        ax.add_patch(patches.FancyBboxPatch((0.62, y - 0.028), 0.20, 0.056, boxstyle='round,pad=0.008',
                                            fc=team_color(h if m >= 0 else a), ec='none'))
        ax.text(0.72, y, pick.upper(), fontsize=9, color=WHITE, ha='center', va='center')
        ax.text(0.88, y, 'W' if ok else 'L', fontsize=13, color='#2E7D32' if ok else '#C62828', ha='center', va='center')
    save(fig, 'DRAFT_A_tips.png')

# ============ STYLE B — TEAM-TINTED CARDS (white, rounded cards) ============
def card(fig, x, y, w, h, fc=CARD, ec=BORDER):
    fig.add_artist(patches.FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.012', fc=fc, ec=ec, lw=1.2, zorder=2))

def style_b_matchup():
    fig = new_fig(); fig.patch.set_facecolor('#F7F6F2')
    # header card with team colors
    card(fig, 0.05, 0.86, 0.90, 0.105, fc=WHITE)
    fig.text(0.5, 0.945, 'MATCHUP  ·  R24', ha='center', fontsize=13, color=SUB)
    fig.text(0.5, 0.905, f'{HN.upper()}  VS  {AN.upper()}', ha='center', fontsize=22, color=INK, fontweight='bold')
    fig.add_artist(patches.Rectangle((0.05, 0.86), 0.008, 0.105, fc=HC, ec='none', zorder=3))
    fig.add_artist(patches.Rectangle((0.942, 0.86), 0.008, 0.105, fc=AC, ec='none', zorder=3))
    # team stat cards
    for i, (tid, name, cc, rr, tier, elo) in enumerate([(H, HN, HC, R['home_rank'], R['home_tier'], R['home_elo']),
                                                        (A, AN, AC, R['away_rank'], R['away_tier'], R['away_elo'])]):
        x = 0.05 + i * 0.465
        card(fig, x, 0.73, 0.44, 0.11, fc=WHITE)
        fig.add_artist(patches.Circle((x + 0.05, 0.775), 0.022, fc=cc, ec='none', zorder=3))
        fig.text(x + 0.085, 0.785, name.upper(), fontsize=13, color=INK, fontweight='bold', va='center')
        fig.text(x + 0.085, 0.752, f'RANK {rr}  ·  {tier}', fontsize=9.5, color=SUB, va='center')
        fig.text(x + 0.40, 0.775, f'{elo:.0f}', fontsize=13, color=cc, ha='right', va='center', fontweight='bold')
    # field card
    card(fig, 0.05, 0.28, 0.90, 0.42, fc=WHITE)
    ax = fig.add_axes([0.13, 0.315, 0.74, 0.35])
    ax.set_zorder(4)  # above the card patch
    draw_field(ax)
    draw_arrows(ax, edges, HC, AC)
    draw_zones(ax, involved_nodes(edges))
    # battles card (top 8)
    card(fig, 0.05, 0.105, 0.90, 0.15, fc=WHITE)
    ax2 = fig.add_axes([0.10, 0.115, 0.82, 0.13]); ax2.axis('off')
    ax2.set_zorder(4)
    for i, (_, e, v) in enumerate(sorted(((abs(v), k, v) for k, v in delta.items()), reverse=True)[:8]):
        x = 0.25 * (i % 4); y = 0.72 - (i // 4) * 0.55
        ax2.text(x, y, f'{split_edge(e)[0]}->{split_edge(e)[1]}', fontsize=8.5, color=INK)
        ax2.text(x + 0.14, y, f'{v:+.2f}', fontsize=8.5, color=HC if v > 0 else AC)
    banner(fig, f'{HN.upper()} WINNER', sub=f'PREDICTED MARGIN {R["margin"]:+.0f} PTS', y=0.045, h=0.06,
           bg=HC, fs=26, sub_fs=11)
    save(fig, 'DRAFT_B_matchup.png')

def style_b_tips():
    fig = new_fig(); fig.patch.set_facecolor('#F7F6F2')
    fig.text(0.5, 0.945, 'ROUND 24 · TIPS RESULTS', ha='center', fontsize=20, color=INK, fontweight='bold')
    fig.text(0.5, 0.915, 'SEASON 2026 · 147/207 (71.0%)', ha='center', fontsize=12, color=SUB)
    for i, (h, a, m, w, ok) in enumerate(tips):
        y = 0.885 - i * 0.093
        card(fig, 0.05, y - 0.072, 0.90, 0.082, fc=WHITE)
        hn, an = TEAM_DATA[h]['name'], TEAM_DATA[a]['name']
        pick = hn if m >= 0 else an
        pc = team_color(h if m >= 0 else a)
        fig.text(0.09, y - 0.032, f'G{i+1}', fontsize=10, color=SUB, va='center')
        fig.text(0.16, y - 0.018, hn, fontsize=12, color=INK, va='center')
        fig.text(0.16, y - 0.052, an, fontsize=12, color=INK, va='center')
        fig.add_artist(patches.Rectangle((0.62, y - 0.065), 0.06, 0.055, fc=pc, ec='none', zorder=3))
        fig.text(0.71, y - 0.037, 'PICK', fontsize=7.5, color=SUB, va='center')
        fig.text(0.71, y - 0.016, pick.upper(), fontsize=9, color=INK, va='center', fontweight='bold')
        fig.text(0.92, y - 0.037, 'W' if ok else 'L', fontsize=15, color='#2E7D32' if ok else '#C62828', ha='center', va='center')
    save(fig, 'DRAFT_B_tips.png')

# ============ STYLE C — STAT SHEET (navy editorial) ============
def style_c_matchup():
    fig = new_fig(); fig.patch.set_facecolor(NAVY)
    fig.add_artist(patches.Rectangle((0, 0.86), 1, 0.14, fc='#0B1526', ec='none', zorder=1))
    fig.text(0.5, 0.955, HN.upper(), ha='center', fontsize=24, color=HC, fontweight='bold', zorder=2)
    fig.text(0.5, 0.905, 'VS', ha='center', fontsize=16, color='#8899AA', zorder=2)
    fig.text(0.5, 0.875, AN.upper(), ha='center', fontsize=24, color=L_AC, fontweight='bold', zorder=2)
    # stat rows
    rows = [('RANK', f'{R["home_rank"]}  vs  {R["away_rank"]}'),
            ('TIER', f'{R["home_tier"]}  vs  {R["away_tier"]}'),
            ('RATING', f'{R["home_elo"]:.0f}  vs  {R["away_elo"]:.0f}'),
            ('NET DELTA', f'{R["net_delta"]:+.2f}')]
    for i, (k, v) in enumerate(rows):
        y = 0.80 - i * 0.075
        fig.text(0.12, y, k, fontsize=11, color='#8899AA', va='center')
        fig.text(0.88, y, v, fontsize=13, color=WHITE, ha='right', va='center')
        if i < 3:
            fig.add_artist(patches.Rectangle((0.10, y - 0.028), 0.80, 0.002, fc='#2A3A55', ec='none'))
    # advantage bar
    share = 1 / (1 + math.exp(-R['net_delta'] * 4))
    fig.add_artist(patches.Rectangle((0.10, 0.52), 0.80, 0.045, fc='#2A3A55', ec='none'))
    fig.add_artist(patches.Rectangle((0.10, 0.52), 0.80 * share, 0.045, fc=HC, ec='none'))
    fig.text(0.5, 0.485, f'{HN} ADVANTAGE  {share*100:.0f}%', ha='center', fontsize=10, color='#B8C4D4')
    # battles top 10
    fig.text(0.12, 0.435, 'TOP 9 TACTICAL BATTLES', fontsize=12, color=WHITE, fontweight='bold')
    for i, (_, e, v) in enumerate(sorted(((abs(v), k, v) for k, v in delta.items()), reverse=True)[:9]):
        y = 0.408 - i * 0.031
        fig.text(0.12, y, f'{split_edge(e)[0]} -> {split_edge(e)[1]}', fontsize=9.5, color='#B8C4D4')
        fig.text(0.88, y, f'{v:+.3f}  {HN if v > 0 else AN}', fontsize=9.5, color=HC if v > 0 else L_AC, ha='right')
    banner(fig, f'{HN.upper()} BY {abs(R["margin"]):.0f}', sub=f'PREDICTED MARGIN  ·  R24', y=0.06, h=0.07, bg=HC, fs=34, sub_fs=12)
    save(fig, 'DRAFT_C_matchup.png')

def style_c_tips():
    fig = new_fig(); fig.patch.set_facecolor(NAVY)
    fig.add_artist(patches.Rectangle((0, 0.88), 1, 0.12, fc='#0B1526', ec='none', zorder=1))
    fig.text(0.5, 0.965, 'ROUND 24 — TIPS RESULTS', ha='center', fontsize=20, color=WHITE, fontweight='bold', zorder=2)
    fig.text(0.5, 0.925, 'SEASON 2026 · 147/207 (71.0%)', ha='center', fontsize=11, color='#8899AA', zorder=2)
    for i, (h, a, m, w, ok) in enumerate(tips):
        y = 0.865 - i * 0.086
        hn, an = TEAM_DATA[h]['name'], TEAM_DATA[a]['name']
        pick = hn if m >= 0 else an
        pc = team_color(h if m >= 0 else a)
        fig.text(0.10, y, f'G{i+1}', fontsize=10, color='#8899AA', va='center')
        fig.text(0.17, y, f'{hn} v {an}', fontsize=11.5, color=WHITE, va='center')
        fig.add_artist(patches.Rectangle((0.60, y - 0.028), 0.18, 0.056, fc=pc, ec='none', zorder=3))
        fig.text(0.69, y, pick.upper(), fontsize=9, color=WHITE, ha='center', va='center', zorder=4)
        fig.text(0.88, y, 'W' if ok else 'L', fontsize=12, color='#66BB6A' if ok else '#EF5350', ha='center', va='center', fontweight='bold')
    save(fig, 'DRAFT_C_tips.png')

# ============ STYLE D — DARK MODE ============
def style_d_matchup():
    fig = new_fig(); fig.patch.set_facecolor(DARK)
    fig.text(0.5, 0.945, 'MATCHUP', ha='center', fontsize=38, color=WHITE, fontproperties=FASTER)
    fig.text(0.5, 0.905, f'{HN.upper()}  VS  {AN.upper()}', ha='center', fontsize=18, color='#CCCCCC')
    fig.text(0.5, 0.878, f'R{24}  ·  RANK {R["home_rank"]} [{R["home_tier"]}]  vs  RANK {R["away_rank"]} [{R["away_tier"]}]',
             ha='center', fontsize=10.5, color='#888888')
    ax = fig.add_axes([0.08, 0.40, 0.84, 0.44])
    draw_field(ax, color='#555555')
    draw_arrows(ax, edges, HC, L_AC)
    draw_zones(ax, involved_nodes(edges), c='#AAAAAA')
    ax2 = fig.add_axes([0.08, 0.13, 0.84, 0.24]); ax2.axis('off')
    ax2.text(0, 1.0, 'TOP 10 TACTICAL BATTLES', fontsize=11, color='#DDDDDD', fontweight='bold')
    for i, (_, e, v) in enumerate(sorted(((abs(v), k, v) for k, v in delta.items()), reverse=True)[:10]):
        y = 0.87 - i * 0.081
        ax2.text(0, y, f'{split_edge(e)[0]} -> {split_edge(e)[1]}', fontsize=9, color='#AAAAAA')
        ax2.text(0.6, y, f'{v:+.3f}', fontsize=9, color=HC if v > 0 else L_AC, ha='right')
    banner(fig, f'{HN.upper()} WINNER', sub=f'MARGIN {R["margin"]:+.0f} PTS', y=0.055, h=0.065, bg=HC, fs=28, sub_fs=12)
    save(fig, 'DRAFT_D_matchup.png')

def style_d_tips():
    fig = new_fig(); fig.patch.set_facecolor(DARK)
    fig.text(0.5, 0.95, 'ROUND 24 TIPS', ha='center', fontsize=34, color=WHITE, fontproperties=FASTER)
    fig.text(0.5, 0.915, 'SEASON 2026 · 147/207 (71.0%)', ha='center', fontsize=12, color='#888888')
    for i, (h, a, m, w, ok) in enumerate(tips):
        y = 0.885 - i * 0.09
        hn, an = TEAM_DATA[h]['name'], TEAM_DATA[a]['name']
        pick = hn if m >= 0 else an
        pc = team_color(h if m >= 0 else a)
        fig.add_artist(patches.FancyBboxPatch((0.07, y - 0.072), 0.86, 0.078, boxstyle='round,pad=0.01',
                                              fc='#1E1E1E', ec='#333333', lw=1, zorder=2))
        fig.text(0.11, y - 0.033, f'G{i+1}', fontsize=9.5, color='#777777', va='center')
        fig.text(0.17, y - 0.033, f'{hn} v {an}', fontsize=11.5, color='#DDDDDD', va='center')
        fig.add_artist(patches.Rectangle((0.62, y - 0.064), 0.05, 0.052, fc=pc, ec='none', zorder=3))
        fig.text(0.70, y - 0.033, pick.upper(), fontsize=9, color='#EEEEEE', va='center', fontweight='bold')
        fig.text(0.90, y - 0.033, 'W' if ok else 'L', fontsize=14, color='#66BB6A' if ok else '#EF5350', ha='center', va='center')
    save(fig, 'DRAFT_D_tips.png')

if __name__ == '__main__':
    style_a_matchup(); style_a_tips()
    style_b_matchup(); style_b_tips()
    style_c_matchup(); style_c_tips()
    style_d_matchup(); style_d_tips()
    print('done ->', OUT)
