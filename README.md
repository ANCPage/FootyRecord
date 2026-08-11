# FootyRecord — AFL Tactical Prediction Engine

Spatial chain analysis for Australian Rules Football: scrapes play-by-play
tracking data, models each team's ball movement as a directed graph over a
5×3 tactical grid, and predicts match winners, margins and probabilities.

## Quickstart

```bash
# install (Python 3.10+)
pip install -e ".[dev]"

# 1. fetch match data (fresh scrape — CSV_DATA is intentionally empty,
#    see "Fresh start" below)
python Core/main.py update                # 2026 only
python Core/main.py update --force        # full rebuild of 2026

# 2. predict a matchup (uses historical profiles)
python Core/main.py predict CD_T80 CD_T100
python Core/main.py predict_full CD_T80 CD_T100

# 3. evaluate the model walk-forward over all seasons
python evaluate.py

# 4. web dashboard
python server.py                          # http://localhost:8080

# 5. tests + lint
pytest
ruff check Core/ *.py --exclude LegacyScripts
```

> Note: the repo root and `Core/` must be on `sys.path` (flat imports).
> The venv handles this via a `footyrecord_paths.pth` in site-packages —
> if you recreate the venv, recreate that two-line file.

## Architecture

```
engine_scraper.py   AFL API -> flattened CSVs (per-team spatial frame)
engine_data.py      CSV -> per-match transition matrices (decayed, normalized)
engine_core.py      Graph + MatchupEngine (delta = tactical advantage per edge)
elo_engine.py       delta-based Elo ratings (winner = delta sign, margin-scaled K)
geometry.py         grid mapping + 180° rotation (single source of truth)
visualize_*.py      matchup/story/ladder/tips graphics
server.py           web dashboard (predictions, ladder, parameter sweep)
evaluate.py         walk-forward evaluation (accuracy, Brier, margin MAE/RMSE)
```

## Design decisions (deliberate — see code_audit_2026-08.md for the full audit)

- **Scoring chains only.** Profiles are built from chains that end in a score;
  turnover/stoppage chains are excluded. Opponent scoring chains are embedded
  (rotated + negated) into each team's profile, so defensive leakage *is*
  visible — pressure and tempo are not.
- **Delta-based Elo.** Ratings follow the tactical delta, not the scoreboard
  (a team can win the scoreboard and lose the rating). No venue advantage
  term — the AFL "home" label is unreliable across shared/neutral grounds.
- **Round 0 is a real home-and-away round** (AFL Opening Round) and is
  correctly included in history.
- **Normalized matrices.** Each match's matrix is divided by its total weight,
  so deltas measure pattern, not attack volume.
- **All calibrations are fitted from data — automatically.** Probability,
  margin, total and the Elo margin divisor are re-fitted on ingestion
  (`Core/calibration.py`, rolling 2-season window, stored in the profile
  cache). No manual refit, no numbers to copy; the historical fit tools
  (`analyze_margins.py`, `fit_calibration.py`) are archived in git history.
- **Hyperparameters are scan-fitted.** `decay_factor` (0.3) and `window_size`
  (30) were chosen by a walk-forward grid over 1,189 matches (2026-08-10:
  65.0% → 66.4% acc, Brier 0.2125 → 0.2107; Elo K and off-season regression
  were flat and left alone). Re-run with `python refit_hyperparams.py` when
  the game or data changes materially.

## Fresh start (data)

`CSV_DATA/` is empty by design (post-audit). Re-scrape all seasons:

```bash
python - <<'EOF'
from Core.engine_scraper import update_all_data
from Core.config import DATA_DIR
for year in range(2021, 2027):
    update_all_data(DATA_DIR, year=year)
EOF
```

Expect a long run (6 seasons × ~200 matches, rate-limited). The scraper
skips already-downloaded matches, so it can be resumed safely.

## Project layout

```
Core/          engine, Elo, geometry, visualizers, config
CSV_DATA/      raw match CSVs (gitignored, regenerable) + profile cache
tests/         47 pytest tests (unit + integration, no real data needed)
docs/          architecture/design assessments
*.py           tools: predict_game, evaluate, generate_round_images, server
```

See `code_audit_2026-08.md` for the full audit trail (issues found, fixed,
and kept-by-design), and `production_scripts_flaws.md` (historical, largely
resolved).
