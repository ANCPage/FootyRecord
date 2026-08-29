#!/usr/bin/env python3
"""League scoring directed graph (2026-08-26, Austin).

Aggregates ALL scoring chains of a season into ONE signed directed graph
in the home frame — own chains +1, opponent chains rotated 180deg and -1 —
exactly the per-match delta convention, summed across every game.

Usage:  python scoring_graph.py --season 2026 [--out path.png]

Repeatable: pure DB read (chains + predictions tables), no profiling.
"""
import argparse
import sys
from collections import defaultdict

import matplotlib

matplotlib.use('Agg')
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager

sys.path.insert(0, '/mnt/projects/FootyRecord')
import Core.results_db as results_db
import Core.state_store as state_store
from Core.engine_core import collapse_chain
from Core.field_visualizer import FieldVisualizer
from Core.geometry import rotate_node

ROOT = '/mnt/projects/FootyRecord'
DB = '/home/austin/footyrecord-results/footyrecord.db'
fontManager.addfont(f'{ROOT}/downloaded_fonts/Roboto-Regular.ttf')
fontManager.addfont(f'{ROOT}/downloaded_fonts/FasterOne.ttf')
TITLE_F = FontProperties(fname=f'{ROOT}/downloaded_fonts/FasterOne.ttf')
BODY_F = FontProperties(fname=f'{ROOT}/downloaded_fonts/Roboto-Regular.ttf')

ATTACK_C = '#1B7A6E'    # teal — own scoring chains (+)
CONCEDE_C = '#B05040'   # terracotta — opponent chains (-)
BG = '#F4F1EA'
INK = '#3E3A35'
SUB = '#6A655F'


def load(season: int):
    # Phase 2 (2026-08-26): data access via the repositories, no inline SQL.
    conn = state_store.connect()
    homes = results_db.season_home_teams(conn, season)
    chains = state_store.scoring_chains(conn)
    conn.close()

    agg = defaultdict(float)
    n_chains = 0
    for (m_id, _cidx), evs in chains.items():
        if m_id not in homes:
            continue
        evs.sort()
        home = homes[m_id]
        cteam = evs[0][1]
        d = {'grids': [g for _, _, g in evs],
             'players': [None] * len(evs),
             'outcome': 'SCORE'}
        edges, _ = collapse_chain(d)
        if not edges:
            continue
        n_chains += 1
        for s, e in edges:
            if cteam == home:
                agg[(s, e)] += 1.0
            else:
                agg[(rotate_node(s), rotate_node(e))] -= 1.0
    return agg, n_chains


def draw(agg, n_chains, season, out):
    fv = FieldVisualizer()
    fig = plt.figure(figsize=(9, 12), facecolor=BG)
    fig.text(0.5, 0.955, 'SCORING GRAPH', ha='center', fontsize=30,
             color=INK, fontproperties=TITLE_F)
    fig.text(0.5, 0.92, f'SEASON {season}  ·  ALL SCORING CHAINS · HOME FRAME', ha='center',
             fontsize=11, color=SUB, fontproperties=BODY_F)

    ax = fig.add_axes([0.10, 0.13, 0.80, 0.74])
    ax.set_xlim(-100, 100); ax.set_ylim(-85, 85)
    ax.set_aspect('equal')
    ax.set_facecolor(BG)
    ax.axis('off')
    fv.draw_pitch(ax)
    fv.draw_zones(ax, active_only=False, font_scale=0.9)

    pos = fv.node_positions
    shots = {k: v for k, v in agg.items() if k[1] == 'SCORE'}
    prog = {k: v for k, v in agg.items() if k[1] != 'SCORE'}

    def pick_sign(d, n, positive):
        sel = [(k, v) for k, v in d.items() if (v > 0) == positive]
        sel.sort(key=lambda kv: -abs(kv[1]))
        return sel[:n]

    def draw_edges(edges, color, wmax):
        for (s, e), w in edges:
            p1, p2 = pos[s], pos[e]
            lw = max(0.8, 3.5 * (abs(w) / wmax) ** 0.5)
            ax.annotate('', xy=(p2[0] * 0.97, p2[1] * 0.97), xytext=p1,
                        arrowprops=dict(arrowstyle='-|>', color=color,
                                        lw=lw, shrinkA=6, shrinkB=2,
                                        alpha=0.85))

    wmax = max([abs(w) for _, w in pick_sign(prog, 8, True)]
               + [abs(w) for _, w in pick_sign(prog, 8, False)]
               + [abs(w) for _, w in pick_sign(shots, 6, True)]
               + [abs(w) for _, w in pick_sign(shots, 6, False)] or [1.0])
    draw_edges(pick_sign(prog, 8, True), ATTACK_C, wmax)
    draw_edges(pick_sign(prog, 8, False), CONCEDE_C, wmax)
    draw_edges(pick_sign(shots, 6, True), ATTACK_C, wmax)
    draw_edges(pick_sign(shots, 6, False), CONCEDE_C, wmax)

    # goal labels
    ax.text(85, 12, 'SCORE', ha='center', fontsize=9, color=INK, fontproperties=BODY_F)
    ax.text(0, -78, f'{n_chains:,} scoring chains aggregated', ha='center',
            fontsize=9.5, color=SUB, fontproperties=BODY_F)

    legend = [mpatches.Patch(color=ATTACK_C, label=f'ATTACK  (+{sum(v for v in agg.values() if v > 0):,.0f})'),
              mpatches.Patch(color=CONCEDE_C, label=f'CONCEDED  (−{sum(-v for v in agg.values() if v < 0):,.0f})')]
    ax.legend(handles=legend, loc='lower right', fontsize=9, framealpha=0.92,
              facecolor=BG, edgecolor=INK)

    fig.savefig(out, dpi=100, facecolor=BG, bbox_inches=None)
    plt.close(fig)
    print(f'wrote {out}  ({n_chains:,} chains, {len(agg)} signed edges)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    agg, n = load(a.season)
    out = a.out or f'/mnt/projects/FootyRecord/ROUND_IMAGES_UPDATE/{a.season}/ANALYSIS/SCORING_GRAPH_{a.season}.png'
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    draw(agg, n, a.season, out)
