#!/usr/bin/env python3
"""Fingerprint card — a team's movement fingerprint, or two overlaid
(2026-08-30, Austin's idea). Part of the one system: same ingestor facade,
same visualizer class, same theme, same output conventions.

Usage:
  python compare_fingerprints.py --team "Fremantle"            # single
  python compare_fingerprints.py --team-a "Fremantle" --team-b "Sydney Swans"
  ... --season 2026 --round 25 --out /tmp/fp.png

Output default: ROUND_IMAGES_UPDATE/<season>/ANALYSIS/ — the season-level
artifacts home (scoring graph, analysis charts).
"""
import argparse
import os

import Core.config as config
from Core.engine_core import fingerprint_overlay
from Core.engine_data import DataIngestor
from Core.mappings import TEAM_DATA
from Core.visualize_matchup import MatchupVisualizer

NAME_FIX = {'Adelaide': 'Adelaide Crows', 'Geelong': 'Geelong Cats',
            'Gold Coast': 'Gold Coast Suns', 'Greater Western Sydney': 'GWS Giants',
            'Sydney': 'Sydney Swans', 'West Coast': 'West Coast Eagles'}


def resolve_team(name: str) -> str:
    """Display name -> team id, with the usual short-name fixes."""
    full = NAME_FIX.get(name, name)
    for tid, data in TEAM_DATA.items():
        if data.get('name', '').lower() == full.lower():
            return tid
    raise SystemExit(f'Unknown team: {name!r}. Known: '
                     + ', '.join(sorted(d['name'] for d in TEAM_DATA.values())))


def main():
    ap = argparse.ArgumentParser(description='Team fingerprint card(s)')
    ap.add_argument('--team', help='single-team fingerprint')
    ap.add_argument('--game-a', help='GAME MODE: team A of the single game')
    ap.add_argument('--game-b', help='GAME MODE: team B of the single game')
    ap.add_argument('--recap', action='store_true',
                    help='GAME MODE: post-game recap (the actual chains of the match)')
    ap.add_argument('--team-a', help='overlay: team A')
    ap.add_argument('--team-b', help='overlay: team B')
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--round', type=int, default=25,
                    help='fingerprint through this round (default 25 = end of H&A)')
    ap.add_argument('--out', help='output path (default: ROUND_IMAGES_UPDATE/<season>/ANALYSIS/)')
    ap.add_argument('--animate', action='store_true',
                    help='also render the animated "press" as MP4 (same path, .mp4)')
    ap.add_argument('--ink', type=float, default=26.0,
                    help='equal-ink budget: total ridge length per colour '
                         '(higher = denser whorl)')
    a = ap.parse_args()

    single = a.team is not None
    game = bool(a.game_a or a.game_b)
    if game and not (a.game_a and a.game_b):
        ap.error('--game mode needs BOTH --game-a and --game-b')
    if single and (a.team_a or a.team_b):
        ap.error('use --team OR --team-a/--team-b, not both')
    if game and single:
        ap.error('--game mode is exclusive with --team')
    if not single and not game and not (a.team_a and a.team_b):
        ap.error('need --team, or --team-a AND --team-b')

    ing = DataIngestor(config.DATA_DIR)
    ing.load_all_data(light=True)
    from Core import results_db, state_store
    sz_conn = results_db.connect()
    start_zones = state_store.scoring_chain_start_zones(
        sz_conn, a.season, a.round)
    sz_conn.close()
    v = MatchupVisualizer()

    if a.game_a and a.game_b:
        ta, tb = resolve_team(a.game_a), resolve_team(a.game_b)
        conn = results_db.connect()
        res = state_store.prediction_result_row(conn, a.season, a.round, ta, tb)
        conn.close()
        model_winner = None
        if res:
            home, away, hs, aw, margin, correct = res
            home_n = TEAM_DATA.get(home, {}).get('name', home)
            away_n = TEAM_DATA.get(away, {}).get('name', away)
            # E1/E2 (2026-09-02 audit): the model's pick is the SHIPPED
            # decision = stored margin sign (home - away), never the actual
            # score. The card's verdict must match the walk-forward record.
            model_winner = home if margin > 0 else away
            pick_n = home_n if margin > 0 else away_n
            result_line = (f'R{a.round}: {home_n} {hs}–{away_n} {aw} · '
                           f'model {"correct" if correct else "wrong"} · picked {pick_n}')
        else:
            result_line = f'R{a.round} · model prediction pending'
        out = a.out or os.path.join(
            config.OUTPUT_DIR, str(a.season), 'ANALYSIS',
            f'FINGERPRINT_GAME_{a.game_a.replace(" ", "")}_vs_'
            f'{a.game_b.replace(" ", "")}_R{a.round}.png')
        anim = out.replace('.png', '.mp4') if a.animate else None
        if a.recap:
            conn = results_db.connect()
            chains = state_store.match_scoring_chains(conn, a.season, a.round,
                                                     ta, tb)
            conn.close()
            ca, cb = chains.get(ta, []), chains.get(tb, [])
            if not ca and not cb:
                raise SystemExit(f'no scoring chains for R{a.round} {a.season}')
            v.draw_game_fingerprint(ta, tb, ca, cb, a.season, a.round, out,
                                    result_line=result_line, anim_path=anim,
                                    ink=a.ink)
        else:
            # PREDICTION card: the model's information set is R-1 (walk-forward)
            pre_round = max(a.round - 1, 0)
            m_a = ing.get_team_average_matrix(ta, up_to_season=a.season,
                                              up_to_round=pre_round)
            m_b = ing.get_team_average_matrix(tb, up_to_season=a.season,
                                              up_to_round=pre_round)
            if not m_a or not m_b:
                raise SystemExit(f'no pre-game fingerprint for R{a.round} {a.season}')
            v.draw_game_delta(ta, tb, m_a, m_b, a.season, a.round, out,
                              result_line=result_line, anim_path=anim,
                              ink=a.ink, model_winner=model_winner)
        print(f'wrote {out}' + (f' + {anim}' if anim else ''))
        return

    if single:
        tid = resolve_team(a.team)
        m = ing.get_team_average_matrix(tid, up_to_season=a.season, up_to_round=a.round)
        if not m:
            raise SystemExit(f'no fingerprint for {a.team} through R{a.round} {a.season}')
        out = a.out or os.path.join(config.OUTPUT_DIR, str(a.season), 'ANALYSIS',
                                    f'FINGERPRINT_{TEAM_DATA[tid]["name"].replace(" ", "")}_R{a.round}.png')
        anim = out.replace('.png', '.mp4') if a.animate else None
        v.draw_fingerprint(tid, None, m, {}, a.season, a.round, out, single=True,
                           animate=a.animate, anim_path=anim, ink=a.ink,
                           start_zones=start_zones)
    else:
        ta, tb = resolve_team(a.team_a), resolve_team(a.team_b)
        m_a = ing.get_team_average_matrix(ta, up_to_season=a.season, up_to_round=a.round)
        m_b = ing.get_team_average_matrix(tb, up_to_season=a.season, up_to_round=a.round)
        if not m_a or not m_b:
            raise SystemExit(f'no fingerprint for one of {a.team_a} / {a.team_b} '
                             f'through R{a.round} {a.season}')
        delta, net_a, net_b = fingerprint_overlay(m_a, m_b)
        out = a.out or os.path.join(config.OUTPUT_DIR, str(a.season), 'ANALYSIS',
                                    f'FINGERPRINT_{TEAM_DATA[ta]["name"].replace(" ", "")}'
                                    f'_vs_{TEAM_DATA[tb]["name"].replace(" ", "")}_R{a.round}.png')
        anim = out.replace('.png', '.mp4') if a.animate else None
        v.draw_fingerprint(ta, tb, m_a, m_b, a.season, a.round, out,
                           single=False, net_a=net_a, net_b=net_b, delta=delta,
                           animate=a.animate, anim_path=anim, ink=a.ink,
                           start_zones=start_zones)
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
