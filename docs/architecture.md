# Architecture (2026-08-11 — current)

The engine's data flow, decision path, and the provenance of every number it
uses. Written to match the code as it stands; if something disagrees with the
code, the code wins and this doc is stale.

## Pipeline (one cache build)

```
CSV match data (6 seasons)
  └─ DataIngestor.load_all_data()          raw ingestion, fingerprint check
  └─ profile_all_teams()
       ├─ Pass 1: per-position accumulation (decay-independent)
       │    each scoring chain → collapsed edges → distance-from-end bucket
       │    (12 buckets, tail lumped) → ±1.0 raw weights per edge
       ├─ Decay fit: grid over candidates on delta-sign agreement vs actual
       │    winners (Elo-free, ~2s) → fitted decay (stored in calibration)
       ├─ Pass 2: at the fitted decay — pre-match expected deltas, actual
       │    matrices, player histories (all recombined from positions)
       ├─ Elo history: sequential, delta-trained (tactical-Elo, E1 kept by
       │    design — A/B vs results-Elo measured a tie, 66.3 vs 66.1)
       └─ Calibration fit (rolling-2 window, data strictly before the round)
  └─ cache: ingestor_state.pkl (v6) — positions, elo, calibration
```

## Decision path (one calibrated output)

The margin model is THE model. Everything else is derived:

```
match → team profiles (positions recombined at the fitted decay)
      → net_delta = Σ calculate_delta(home, away)
      → margin = margin_b1·net_delta + margin_b2·(elo_diff/100)   [fit, no intercept]
      → winner      = margin > 0 (Elo decides the rare dead-even)
      → confidence  = |margin| bands (whole points)
      → probability = display-only transform (sigmoid(margin/scale), not fitted)
      → total       = fitted league-mean total; predicted scores split from it
```

The probability layer (logit/Brier) was REMOVED on 2026-08-10 — measured to
add nothing to picks (65.9% vs 66.3%) while being the weakest output. Metrics
are accuracy + margin MAE/RMSE.

## What's dynamic (fitted on ingestion, stored in the cache)

| Number | How |
|---|---|
| margin_b1, margin_b2 | least squares, rolling-2 seasons, no intercept |
| total_mean | mean actual match total |
| margin_divisor (Elo) | median\|actual_delta\|/1.1 |
| decay | grid on delta-sign agreement (~2s) |
| tier cutoffs | top-4 / next-4 / next-5 percentiles of live Elo |
| window (30) | query-time filter; default scan-fitted 2026-08-10 |

Bootstrap values live in `Core/calibration.py` (used only when <60 prior
matches). `Core/config.py` holds only: window default, Elo K (measured flat),
regression factor (measured flat), margin-divisor bootstrap.

## Evaluation

`evaluate.py` — walk-forward over 1,189 matches: calibration refit before
every round on strictly prior data (same-round matches excluded). Reports
rolling-2 vs expanding windows, per season, plus margin bands (calibration
table). Hyperparameter optimism measured: ~0.2 pts (lookahead check
2026-08-10). `refit_hyperparams.py` re-scans decay/window/K/regression
(recombination makes variants instant for decay/window).

## Key modules

- `Core/engine_data.py` — ingestion, profiling, per-position storage, decay
  fit, calibration fit, cache (v6)
- `Core/calibration.py` — Calibration dataclass, fits, active holder
- `Core/elo_engine.py` — tactical Elo (delta-trained), tiers, `results_based`
  A/B flag
- `Core/engine_core.py` — delta math, `home_favored` (margin sign),
  `collapse_chain` (shared chain→edges)
- `Core/prediction.py` — `compute_matchup()`: one shared matchup computation
  used by server + image generator
- `evaluate.py` — the honest walk-forward harness
- `generate_round_images.py` — the 2026 round cards
- `server.py` — local dashboard (sims use `compute_matchup`)

## Compute / render separation (2026-08-11)

- `compute_round.py --season 2026 --all` — Path A: computes every game's
  decisions (winner, margin, grade, elos, tiers, ranks) and writes them to
  the results DB with the calibration provenance that produced them. ~30s
  for a whole season. No matplotlib.
- `render_round.py --season 2026 --round 22` — Path B: renders the cards
  from the results DB; decisions come ONLY from the DB (verified
  byte-identical to the old combined pipeline).
- `generate_round_images.py` — convenience wrapper (compute then render),
  or `--compute-only` / `--render-only` for the separate paths.

The results DB is **local** (`~/footyrecord-results/footyrecord.db`) —
SQLite needs byte-range locks that the SMB mount can't provide. It's the
**one store**: engine state tables (matches, chains, positions, performance,
matrices, elo, players, calibration — see `Core/state_store.py`) live in the
same file as `predictions` + `calibration_log` (the results). The pickle cache
is gone (2026-08-11); state loads from SQLite (fingerprint-gated, ~30s) and
rebuilds from the CSVs only when the config or data identity changes. Analysis
= SQL, e.g. residual analysis:

```sql
SELECT * FROM predictions WHERE correct = 0 AND margin > 30;
```

## Known limits (measured)

- Winner picks: 66.3% (margin-sign) — Elo and fitted layers add ~nothing over
  the raw delta sign; they buy margins/ties/context
- Margin MAE ±27 pts (r≈0.54) — the margin is honest but coarse
- Naive results rule (last-10 win rate) reaches 65.2% — scoreboard form is
  strong; the engine's edge over it is small but real
- Lookahead: none beyond ~0.2 pts hyperparameter optimism (documented)
