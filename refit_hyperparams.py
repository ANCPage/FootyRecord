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
import sys
import time

sys.path.insert(0, '/mnt/projects/FootyRecord')
sys.path.insert(0, '/mnt/projects/FootyRecord/Core')
import config
from engine_data import DataIngestor

from evaluate import aggregate, collect_rows, run_mode

OUT = 'refit_results.csv'

# Grid: the measured neighbourhood of each parameter (decay 0.3 was the best
# point on the 2026-08-10 scan; window peaked ~30-35; Elo K / regression flat).
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
    out, _ = run_mode(rows, 2, 'roll2')
    return aggregate(out)[:4]


with open(OUT, 'w') as f:
    f.write('param,value,acc,brier,mae,n,seconds\n')

results = []
for param, value in VARIANTS:
    t0 = time.time()
    # Reset every other param to the CURRENT config before each variant —
    # a confounded scan (leftover decay=1.0) produced garbage columns once.
    set_all(decay=config.config.decay_factor,
            window=config.config.window_size,
            elo_k=config.config.elo_k,
            regression=ing.elo_engine.regression_factor)
    if param == 'decay_factor':
        set_all(decay=value)
    elif param == 'window_size':
        set_all(window=value)
    elif param == 'elo_k':
        set_all(elo_k=value)
    elif param == 'regression_factor':
        set_all(regression=value)
    ing._skip_profiling = False
    ing.profile_all_teams()          # decay/window change the profiles
    n, acc, brier, mae = run_eval()
    secs = int(time.time() - t0)
    line = f"{param},{value},{acc:.4f},{brier:.4f},{mae:.1f},{n},{secs}\n"
    with open(OUT, 'a') as f:
        f.write(line)
    results.append((param, value, acc, brier))
    print(f"{param}={value}: acc {100*acc:.1f}%  Brier {brier:.4f}  MAE {mae:.1f}  ({secs}s)", flush=True)

# Restore the current config's profiles (leave the cache clean).
ing._skip_profiling = False
ing.profile_all_teams()

print("\nRecommended (best acc on the grid):")
best = max(results, key=lambda r: r[2])
print(f"  {best[0]} = {best[1]}  (acc {100*best[2]:.1f}%, Brier {best[3]:.4f})")
print(f"full table: {OUT}")
