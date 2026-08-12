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

# 4. compute + render a round (two paths, one DB)
python compute_round.py --season 2026 --round 23   # live round -> results DB
python render_round.py --season 2026 --round 22    # cards from the DB

# 5. tests + lint
pytest
ruff check Core/ *.py --exclude LegacyScripts
```

> Core is a proper package (`Core.*` imports) — no sys.path tricks needed;
> `python script.py` from the repo root just works.

## Architecture

```
engine_scraper.py   AFL API -> flattened CSVs (per-team spatial frame)
engine_data.py      CSV -> per-match transition matrices (decayed, normalized)
engine_core.py      Graph + MatchupEngine (delta = tactical advantage per edge)
elo_engine.py       delta-based Elo ratings (winner = delta sign, margin-scaled K)
geometry.py         grid mapping + 180° rotation (single source of truth)
visualize_*.py      matchup/story/ladder/tips graphics
server.py           web dashboard (DECOMMISSIONED 2026-08-11 — see git history)
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
- **All calibrations are fitted from data — automatically.** The margin
  model, total, Elo margin divisor and decay are re-fitted on ingestion
  (`Core/calibration.py`): margin is the ONE calibrated output — winner =
  margin sign, confidence = margin size. The probability layer was removed
  2026-08-10 (a monotone transform that added zero pick accuracy; any
  percentage shown is a display transform of the margin). Rolling 2-season
  fit window, stored in the profile cache. No manual refit, no numbers to
  copy; the historical fit tools (`analyze_margins.py`, `fit_calibration.py`)
  are archived in git history.
- **Hyperparameters are scan-fitted.** `decay_factor` (fitted on ingestion,
  Option B per-position storage) and `window_size`
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
Core/          engine, Elo, geometry, visualizers, config, results_db
CSV_DATA/      raw match CSVs (source format; regenerable)
               + engine-state tables in the one-store SQLite DB (local)
tests/         58 pytest tests (unit + integration, no real data needed)
docs/          architecture, layperson guide
*.py           tools: compute_round, render_round, generate_round_images,
               predict_game, evaluate, refit_hyperparams, server
```

`compute_round.py` + `render_round.py` are the two paths (results DB →
images); `generate_round_images.py` runs both. See `code_audit_2026-08.md` for the full audit trail (issues found, fixed,
and kept-by-design), and `docs/architecture.md` for how the engine works now.
