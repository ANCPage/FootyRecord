"""Parallel full-season regen driver (perf 2026-08-12).

Loads the engine state ONCE (light load — chains skipped), then forks N
workers that each render whole rounds from the results DB. Renders are
read-only, so concurrent workers are safe (SQLite readers don't block).

Usage:
    ~/footy-venv/bin/python regen_season.py --season 2026            # R0..R22, 3 workers
    ~/footy-venv/bin/python regen_season.py --season 2026 --workers 4
    ~/footy-venv/bin/python regen_season.py --season 2026 --r0 15 --r1 22
    ~/footy-venv/bin/python regen_season.py --season 2026 --resume   # skip rendered rounds

Replaces the sequential `for r in $(seq 0 22)` loop: ~90 min -> ~30 min
on the Pi 4 (3 workers; memory-bound, do NOT go above 4 on 4GB).
"""
import argparse
import multiprocessing as mp
import os
import time

SEASON = 2026
ING = None  # module global — set in the parent, inherited by fork workers
FMTS = ['post']  # post-only default (2026-08-26); reel/desktop opt-in


def _render_round(rnd: int):
    from generate_round_images import render_round_from_db
    t0 = time.time()
    try:
        summary = render_round_from_db(SEASON, rnd, ingestor=ING, formats=FMTS)
        ok = summary is not None
    except Exception:  # keep the pool alive; report per-round
        import traceback
        traceback.print_exc()
        ok = False
    print(f"R{rnd} {'OK' if ok else 'FAILED'} ({time.time() - t0:.0f}s)", flush=True)
    return rnd, ok


def main():
    global SEASON, ING, FMTS
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--r0', type=int, default=0)
    parser.add_argument('--r1', type=int, default=None, help='default: last round in the DB')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--formats', type=str, default='post',
                        help='comma list of desktop,post,reel (default: mobile only)')
    parser.add_argument('--resume', action='store_true',
                        help='skip rounds whose first-format TIPS_RESULTS.png already exists')
    args = parser.parse_args()
    SEASON = args.season
    FMTS = args.formats.split(',')

    import Core.config as config
    from Core.engine_data import DataIngestor
    ING = DataIngestor(config.DATA_DIR)
    ING.load_all_data(light=True)
    if not ING.team_positions:
        ING.profile_all_teams()

    max_round = max(i.round for i in ING.match_info.values() if i.season == SEASON)
    r1 = args.r1 if args.r1 is not None else max_round
    rounds = list(range(args.r0, r1 + 1))
    if args.resume:
        # first-format output dir as the completion marker (default: post)
        marker_dir = 'Desktop' if 'desktop' in FMTS else (
            'Mobile/InstaPost' if 'post' in FMTS else 'Mobile/InstaReels')
        before = len(rounds)
        rounds = [r for r in rounds
                  if not os.path.exists(
                      f'ROUND_IMAGES_UPDATE/{SEASON}/R{r}/{marker_dir}/TIPS_RESULTS.png')]
        print(f"resume: {before} rounds -> {len(rounds)} to render")
    print(f"rendering {SEASON} R{args.r0}..R{r1} with {args.workers} workers "
          f"(state loaded once, light mode, formats={FMTS})")

    t0 = time.time()
    mp.set_start_method('fork', force=True)
    with mp.Pool(args.workers) as pool:
        results = pool.map(_render_round, rounds)
    fails = [r for r, ok in results if not ok]
    done = [r for r, ok in results if ok]
    print(f"done: {len(done)}/{len(results)} rounds OK in {time.time() - t0:.0f}s"
          + (f" — FAILED: {fails}" if fails else ""))


if __name__ == '__main__':
    main()
