"""Re-record the season projections against the corrected results.

WHY: the stored `predictions` were made while the stored scores were light (audit
finding 14) — the model was graded against, and its ratings updated from, results
that were wrong in 8 games and low in almost all. Scores are fixed now; this
rebuilds the projections themselves so the record reflects the corrected history.

HOW, and why it is one process: the expensive part of this codebase is the data
layer, not the maths. A full state load costs ~101s (73s light) and one matchup
takes 0.03s, so a whole six-season rebuild is ~40s of compute. Running this as a
dozen script invocations would pay the load a dozen times; this pays it once.

NON-DESTRUCTIVE: results land in `predictions_rebuilt`, never in `predictions` —
the historical record is evidence, and swapping it is a deliberate act, not a side
effect of a rebuild. Verify with `--verify` (tipping, margin bias, MAE, totals bias
for the rebuilt set vs the stored set).

Usage:
  FOOTYRECORD_DATA_DIR=/mnt/projects/FootyRecord/CSV_DATA \
    ~/footy-venv/bin/python -m Core.tools.rerecord [--verify] [--table predictions_rebuilt]
"""
import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import Core.calibration as calibration  # noqa: E402
import Core.chains as chains  # noqa: E402
import Core.config as config  # noqa: E402
import Core.results_db as results_db  # noqa: E402
from Core.engine_data import DataIngestor  # noqa: E402
from Core.prediction import compute_matchup  # noqa: E402

DEFAULT_TABLE = 'predictions_rebuilt'


def rebuild(ing, conn, seasons=None, table=DEFAULT_TABLE, limit_rounds=None, verbose=True):
    """Walk every season/round in order and write a fresh set of projections."""
    results_db.ensure_predictions_table(conn, table)
    fitted_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    # ONE fit row set, reused per round (cheap), so each round is fitted only on
    # matches STRICTLY BEFORE it (calibration audit finding 3): the ingest fit sees
    # the whole season it predicts, which flatters a re-record.
    fit_rows = ing._build_fit_rows()
    per_round_fits = {}
    # Decay and tier cutoffs come from the ingest fit, NOT from the per-round fit:
    # they shape the engine's MATRICES, and a re-record must change only the
    # margin/total calibration. Dropping them silently changed every delta and the
    # fingerprint gate caught it (2026-09-14).
    base_decay = getattr(ing.calibration, 'decay_factor', None)
    base_tiers = getattr(ing.calibration, 'tier_cutoffs', ())

    by_slot = defaultdict(list)
    for m_id, info in ing.match_info.items():
        if m_id.startswith('POST_'):
            continue
        if seasons and info.season not in seasons:
            continue
        if limit_rounds and info.round > limit_rounds:
            continue
        by_slot[(info.season, info.round)].append(m_id)

    written = skipped = 0
    per_round = []
    for (season, rnd) in sorted(by_slot):
        cal_r = calibration.fit_walk_forward(fit_rows, season, rnd)
        if base_decay is not None:
            cal_r.decay_factor = base_decay
        if not cal_r.tier_cutoffs:
            cal_r.tier_cutoffs = base_tiers
        ing.calibration = cal_r          # the prediction path reads this
        per_round_fits[(season, rnd)] = (cal_r.margin_b1, cal_r.margin_b2,
                                         cal_r.projected_total(), cal_r.source)
        games = []
        for m_id in sorted(by_slot[(season, rnd)]):
            info = ing.match_info[m_id]
            pred = compute_matchup(ing, info.home, info.away, season, rnd)
            if pred is None:
                skipped += 1
                continue
            # played=True so the rebuilt row carries the grade/actual/correct
            # computed against the CORRECTED results — that is the whole point.
            played = bool(info.home_score or info.away_score)
            games.append(results_db.game_row_from_prediction(
                pred, info, season, rnd, cal_r, m_id, played=played))
        if games:
            snapshot = results_db.build_calibration_snapshot(cal_r, fitted_at)
            results_db.upsert_round(conn, season, rnd, games, snapshot, table=table,
                                    log_calibration=False)
            written += len(games)
            per_round.append((season, rnd, len(games)))
            if verbose and len(per_round) % 20 == 0:
                print('  ... %d rounds, %d games written' % (len(per_round), written))
    return {'written': written, 'skipped': skipped, 'rounds': len(per_round),
            'table': table, 'fits': per_round_fits}


STAT_COLUMNS = ('season', 'margin', 'total', 'winner', 'home', 'away', 'match_id')


def _rows(conn, table):
    cols = [d[1] for d in conn.execute('PRAGMA table_info(%s)' % table)]
    if not cols:
        return []
    cur = conn.execute('SELECT %s FROM %s' % (', '.join(STAT_COLUMNS), table))
    return [dict(zip(STAT_COLUMNS, r)) for r in cur.fetchall()]


def verify(conn, table=DEFAULT_TABLE, reference='predictions'):
    """Score both sets against the CORRECTED results, per season."""
    actual = {r[0]: (r[1], r[2], r[3], r[4]) for r in conn.execute(
        'SELECT m_id, home_score, away_score, home, away FROM matches')}
    out = []
    for season in sorted({r['season'] for r in _rows(conn, table)} or {0}):
        line = {'season': season}
        for label, tbl in (('rebuilt', table), ('stored', reference)):
            ok = n = 0
            bias = []
            mae = []
            tbias = []
            for r in _rows(conn, tbl):
                if r['season'] != season:
                    continue
                m = actual.get(r['match_id'])
                if not m or not m[0] or not m[1]:
                    continue
                hs, as_, home, away = m
                if r['home'] not in (home, away):
                    continue
                # predictions store the HOME-relative margin
                sign = 1 if r['home'] == home else -1
                act = (hs - as_) * sign
                n += 1
                pred_winner_ok = ((r['margin'] or 0) > 0) == (act > 0)
                ok += pred_winner_ok
                bias.append((r['margin'] or 0) - act)
                mae.append(abs(abs(r['margin'] or 0) - abs(act)))
                if r['total']:
                    tbias.append((r['total'] or 0) - (m[0] + m[1]))
            if n:
                line[label] = {
                    'n': n,
                    'tipping': 100.0 * ok / n,
                    'margin_bias': sum(bias) / len(bias),
                    'margin_mae': sum(mae) / len(mae),
                    'totals_bias': (sum(tbias) / len(tbias)) if tbias else float('nan'),
                }
        out.append(line)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--table', default=DEFAULT_TABLE)
    ap.add_argument('--seasons', type=int, nargs='*', default=None)
    ap.add_argument('--limit-rounds', type=int, default=None)
    ap.add_argument('--verify-only', action='store_true')
    ap.add_argument('--no-verify', action='store_true')
    args = ap.parse_args(argv)

    t0 = time.time()
    conn = chains.connect()

    if not args.verify_only:
        print('loading engine state once (the expensive step: ~100s) ...')
        ing = DataIngestor(config.DATA_DIR)
        ing.load_all_data(light=True)
        print('loaded %d matches in %.0fs | calibration total_mean=%.1f'
              % (len(ing.match_info), time.time() - t0, ing.calibration.total_mean))

        t1 = time.time()
        result = rebuild(ing, conn, seasons=args.seasons, table=args.table,
                         limit_rounds=args.limit_rounds)
        print('rebuilt %d games across %d rounds (%d skipped) in %.1fs -> %s'
              % (result['written'], result['rounds'], result['skipped'],
                 time.time() - t1, result['table']))
        # Evidence the fit is walk-forward: it should move as rounds pass.
        fits = result.get('fits') or {}
        keys = sorted(fits)
        if keys:
            for k in (keys[0], keys[len(keys) // 2], keys[-1]):
                b1, b2, tot, src = fits[k]
                print('    fit for %s R%s: margin_b1 %.2f b2 %.2f total %.1f (%s)'
                      % (k[0], k[1], b1, b2, tot, src))

    if not args.no_verify:
        print()
        print('%-6s %-9s %8s %9s %11s %9s %11s' % (
            'season', 'set', 'games', 'tipping', 'margin bias', 'margin MAE', 'totals bias'))
        for line in verify(conn, table=args.table):
            for label in ('rebuilt', 'stored'):
                s = line.get(label)
                if not s:
                    continue
                print('%-6s %-9s %8d %8.1f%% %+10.2f %9.1f %+10.2f' % (
                    line['season'], label, s['n'], s['tipping'], s['margin_bias'],
                    s['margin_mae'], s['totals_bias']))
    print()
    print('total %.0fs' % (time.time() - t0))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
