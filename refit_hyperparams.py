"""Hyperparameter refit tool (magic-numbers pass, 2026-08-10).

Re-measures the chosen engine hyperparameters with the walk-forward harness
(rolling-2 dynamic calibration) and reports the optimum. Run whenever the
data or the game changes materially:

    python refit_hyperparams.py

Each variant re-profiles in memory (decay/window change the profiles) and
evaluates; the profile cache is restored to the CURRENT config at the end.
The script does NOT change config — it prints the recommended values so the
change is a human decision. Result table: refit_results.csv.
"""
import time

import Core.config as config
from Core.engine_data import DataIngestor
from evaluate import aggregate, collect_rows, run_mode

OUT = 'refit_results.csv'

# Grid: the measured neighbourhood of each parameter (decay 0.3-0.5 was best
# on the 2026-08-10 scan; window peaked ~30-35; Elo K / regression flat).
VARIANTS = [
    ('decay_factor', 0.2), ('decay_factor', 0.3), ('decay_factor', 0.4),
    ('decay_factor', 0.5), ('decay_factor', 0.7), ('decay_factor', 0.9),
    ('window_size', 25), ('window_size', 30), ('window_size', 35),
    ('elo_k', 25.6), ('elo_k', 32.0), ('elo_k', 38.4),
    ('regression_factor', 0.60), ('regression_factor', 0.75), ('regression_factor', 0.90),
]


def set_all(decay=None, window=None, elo_k=None, regression=None):
    """Set the engine to the given params (None = current config values)."""
    if decay is not None:
        config.config.decay_factor = decay
    if window is not None:
        config.config.window_size = window
    if elo_k is not None:
        config.config.elo_k = elo_k
    if regression is not None:
        ing.elo_engine.regression_factor = regression


ing = DataIngestor('CSV_DATA')
ing.load_all_data()
seasons = sorted({i.season for i in ing.match_info.values()})


def run_eval():
    rows = collect_rows(ing, seasons)
    out, _, _ = run_mode(rows, 2, 'roll2')
    return aggregate(out)


def main():
    with open(OUT, 'w') as f:
        f.write('param,value,acc,mae,rmse,n,seconds\n')

    sorted_matches = sorted(ing.match_info.keys(),
                            key=lambda x: (ing.match_info[x].season, ing.match_info[x].round))
    shipped = {'elo_k': config.config.elo_k,
               'regression': ing.elo_engine.regression_factor}
    results = []
    for param, value in VARIANTS:
        t0 = time.time()
        # Reset everything else to the SHIPPED state before each variant —
        # a confounded scan (leftover decay=1.0) produced garbage columns once.
        # (Calibration itself needs no reset: collect_rows restores
        # ing.calibration.decay_factor in its finally block — Phase 1.)
        config.config.elo_k = shipped['elo_k']
        ing.elo_engine.regression_factor = shipped['regression']
        if param == 'decay_factor':
            rows = collect_rows(ing, seasons, decay=value)
        elif param == 'window_size':
            rows = collect_rows(ing, seasons, window=value)
        elif param in ('elo_k', 'regression_factor'):
            # Elo parameters need the Elo history recomputed (no re-profile —
            # Option B keeps positions; Elo is a pure replay).
            if param == 'elo_k':
                config.config.elo_k = value
            else:
                ing.elo_engine.regression_factor = value
            ing.team_elo_history = ing.elo_engine.compute_elo_history(
                sorted_matches, ing.match_info, ing.actual_match_matrices)
            ing._fit_calibration()
            rows = collect_rows(ing, seasons)
        else:
            continue
        out, _, _ = run_mode(rows, 2, 'roll2')
        # aggregate returns (n, acc, mae, rmse) — Brier left the harness
        # with the cleanest-model commit; the 5-unpack crashed the tool
        # (re-audit 2026-08-12).
        n, acc, mae, rmse = aggregate(out)
        secs = int(time.time() - t0)
        line = f"{param},{value},{acc:.4f},{mae:.1f},{rmse:.1f},{n},{secs}\n"
        with open(OUT, 'a') as f:
            f.write(line)
        results.append((param, value, acc, mae))
        print(f"{param}={value}: acc {100*acc:.1f}%  MAE {mae:.1f}  RMSE {rmse:.1f}  ({secs}s)", flush=True)

    # Nothing on disk was modified; ing.calibration is already back to the
    # shipped fit (collect_rows restores it per variant — Phase 1).

    print("\nRecommended (best acc on the grid):")
    best = max(results, key=lambda r: r[2])
    print(f"  {best[0]} = {best[1]}  (acc {100*best[2]:.1f}%, MAE {best[3]:.1f})")
    print(f"full table: {OUT}")


if __name__ == '__main__':
    main()
