"""Path A: compute + save round results to the SQLite store.

No matplotlib. Loads the profile cache once, computes every game's decision
outputs (the same values the cards show), writes them to results/footyrecord.db
with the calibration provenance that produced them.

Usage:
    python compute_round.py --season 2026 --round 22
    python compute_round.py --season 2026 --all
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))

import Core.calibration as cal
import Core.config as config
import Core.results_db as results_db
from Core.engine_data import DataIngestor
from Core.prediction import compute_matchup

DATA_DIR = config.DATA_DIR


def load_ingestor():
    ing = DataIngestor('CSV_DATA')
    ing.load_all_data()
    if not ing.team_positions:
        ing.profile_all_teams()  # live path needs profiles (regression: was missing)
    return ing


def compute_round(ing, conn, season: int, round_num: int) -> int:
    """Compute one round's predictions and upsert them. Returns game count.

    LIVE rounds only: if every match in the round already has scores, the
    walk-forward record owns it (use `evaluate.py --save`) and nothing is
    written.
    """
    matches = sorted(
        (m for m, i in ing.match_info.items()
         if i.season == season and i.round == round_num and not m.startswith('POST_')),
        key=lambda m: m)
    if not matches:
        return 0
    if all(ing.match_info[m].home_score + ing.match_info[m].away_score > 0
           for m in matches):
        return 0  # played round — not the live path's job
    games = []
    for m_id in matches:
        info = ing.match_info[m_id]
        pred = compute_matchup(ing, info.home, info.away, season, round_num)
        if pred is None:
            continue
        played = info.home_score + info.away_score > 0
        actual_margin = info.home_score - info.away_score if played else None
        correct = 1 if (played and actual_margin != 0
                        and (actual_margin > 0) == (pred.winner_id == info.home)) else 0
        if actual_margin == 0:
            correct = 0  # draws are not tip wins (matches eval semantics)
        games.append({
            'season': season, 'round': round_num, 'match_id': m_id,
            'home': info.home, 'away': info.away,
            'net_delta': pred.net_delta, 'elo_diff': pred.elo_diff,
            'margin': pred.margin_pred, 'winner': pred.winner_id,
            'home_elo': pred.h_elo, 'away_elo': pred.a_elo,
            'home_tier': pred.h_tier, 'away_tier': pred.a_tier,
            'home_rank': pred.h_rank, 'away_rank': pred.a_rank,
            'total': pred.home_score + pred.away_score,
            'home_score': info.home_score,
            'away_score': info.away_score,
            'grade': cal.confidence_grade(pred.margin_pred),
            'delta': results_db.serialize_delta(pred.delta),
            'actual_margin': actual_margin, 'correct': correct,
        })
    snapshot = {
        'decay': cal.current.decay_factor,
        'margin_b1': cal.current.margin_b1,
        'margin_b2': cal.current.margin_b2,
        'total_mean': cal.current.total_mean,
        'divisor': cal.current.margin_divisor,
        'window': cal.WINDOW_SEASONS,
        'fitted_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    results_db.upsert_round(conn, season, round_num, games, snapshot)
    return len(games)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--round', type=int, default=None)
    parser.add_argument('--all', action='store_true', help='compute every round in the season')
    args = parser.parse_args()

    t0 = time.time()
    ing = DataIngestor('CSV_DATA')
    ing.load_all_data()
    if args.all:
        rounds = sorted({i.round for i in ing.match_info.values() if i.season == args.season})
    elif args.round is not None:
        rounds = [args.round]
    else:
        parser.error('pass --round N or --all')

    # Live-round guard: compute_round owns UNPLAYED rounds only. Played rounds
    # are the walk-forward record — populate them with `evaluate.py --save`.
    rounds = [r for r in rounds
              if not all(i.home_score > 0 or i.away_score > 0
                         for i in (ing.match_info[m] for m in ing.match_info
                                   if ing.match_info[m].season == args.season
                                   and ing.match_info[m].round == r
                                   and not m.startswith('POST_')))]
    if not rounds:
        raise SystemExit("no unplayed rounds to compute — played rounds come "
                         "from `evaluate.py --save` (walk-forward record)")
    conn = results_db.connect()
    total = 0
    for r in rounds:
        n = compute_round(ing, conn, args.season, r)
        total += n
        correct, played = results_db.cumulative_record(conn, args.season, r)
        print(f"R{r}: {n} games | season through R{r}: {correct}/{played} ({100*correct/played:.1f}%)")
    conn.close()
    print(f"done — {total} games written in {time.time()-t0:.0f}s")


if __name__ == '__main__':
    main()
