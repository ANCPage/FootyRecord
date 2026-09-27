# Calibration & magic-number audit — 2026-09-14

Scope: every constant that can move a model output — what it is, where it lives, whether it is
fitted, derived, or hardcoded, and what happens when it goes stale. Verified by reading the code
AND running queries against the live DB; measurements are labelled.

---

## 1. What is fitted at ingest (self-updating)

`Core/calibration.py` + `Core/profiler.py:fit_calibration()`, run from
`engine_data.profile_all_teams()` on every ingest. Six values, no hand-tuning:

| value | how it is fitted | live value (post score-correction) |
|---|---|---|
| `margin_b1` | least squares on `[net_delta, elo_diff/100]`, **no intercept** (deliberate: the AFL "home" label is unreliable, user decision 2026-08) | **113.172** (was 110.030) |
| `margin_b2` | same fit | **3.692** (was 3.476) |
| `total_mean` | mean actual match total over the window | **173.708** (was 164.877) |
| `margin_divisor` | `median(|actual_delta|) / 1.1` | **0.2702** (was 0.2708) |
| `decay_factor` | scan-fitted walk-forward grid (config comment; refit via `refit_hyperparams.py`) | 0.5 |
| `tier_cutoffs` | midpoints between the tier boundaries of the live Elo field | [1681.8, 1554.3, 1388.8] |

Provenance travels with them (`fit_fingerprint`, `fit_n_matches`, `source`) and is verified on
every load by `state_store.verify_state()`.

## 2. What is hardcoded but presented as "the shipped constants"

`Core/calibration.py:36-38`, `MIN_FIT_MATCHES = 60`, `WINDOW_SEASONS = 2`:

```python
FALLBACK_MARGIN = (70.9755, 4.8817)   # b1(net), b2(elo/100)
FALLBACK_TOTAL  = 159.26
```

Comment says: *"Shipped constants (fit on 2024-25, 2026-08-09/10) — bootstrap fallback only."*
They were fitted **before** the scoreboard correction, and being constants they cannot
self-update. Against the live fit they are now materially wrong:

- margin per unit delta: **70.98 vs 113.17** → a 40-point projection becomes **25.1**
- total: **159.26 vs 173.71** → scorelines 14.5 points light

## 3. What is hardcoded and consumed in production (no fit provenance)

| constant | value | where | note |
|---|---|---|---|
| score floor | `max(10, ...)` | `prediction.py:88-89` | measured: **never fires** (0 of 1,232 projections) |
| divisor factor | `/ 1.1` | `calibration.py:98` | chosen to reproduce a 2026-08-09 hand-fit |
| tier sizes | top-4 / next-4 / next-5 | `calibration.py:130` (indices 3,4 / 7,8 / 12,13) | 18-team assumption |
| tier thresholds (fallback) | 1600 / 1550 / 1450 | `calibration.py:78-81` | absolute Elo, used only when cutoffs are absent |
| Elo | `elo_k = 32` | `config.py:29` | documented as scan-flat |
| Elo regression | `regression_factor = 0.75` | `elo_engine.py:7` | 25% pull to the mean each season; **not in config, not fitted** |
| Elo mean | `mean_rating = 1500.0` | `elo_engine.py:8` | standard |
| Elo margin divisor bootstrap | `0.3` | `config.py:39`, `calibration.py:98-100` | pre-fit placeholder |
| matrix window | `window_size = 30` **games** | `config.py:28` | see finding 4 |
| fit window | `WINDOW_SEASONS = 2` **seasons** | `calibration.py:34` | see finding 4 |
| points per goal | `PPG = 6.71` **×2 files** | `player_props.py:30`, `tools/props_backtest.py:37` | duplicated; derived from pre-correction data |

## 4. Removed by design (so nobody "restores" them)

The win-probability layer and its scale factor (`prob_from_margin`, `MARGIN_TO_PROB_SCALE`) were
removed 2026-08-10/12: *"the margin is the single calibrated output; winner = margin sign"*.
`calibration.py:14-18` records it. There is therefore **no probability calibration to audit** —
Brier-style checks are gone by decision, and margin MAE is the honest error.

---

## Findings

### 🔴 1. The stale fallback is reachable from the production prediction path
`Core/prediction.py:81`: `cal = getattr(ingestor, 'calibration', None) or Calibration.fallback()`.
Five more sites default to it (`engine_data.py:70,153`, `elo_engine.py:202`, `profiler.py:187`,
`visualize_matchup.py:26`). With the corrected data the fallback is ~37% low on margin scaling and
14.5 points light on totals — and it applies **silently**, producing plausible-looking wrong cards.
**Fix:** fail loudly (raise) when a prediction path has no fitted calibration, keeping the
constants only for the earliest rounds where `MIN_FIT_MATCHES` is genuinely unmet (where they must
first be re-derived from corrected data).

### 🔴 2. The fallback constants are pre-correction and cannot self-update
`FALLBACK_MARGIN`/`FALLBACK_TOTAL` were fitted 2026-08-09/10 on the light-era scores. Every fitted
value moved when the scores were corrected (finding 1's table); the fallbacks did not. They need a
deliberate re-derivation, with the fit date and data identity recorded next to them.

### 🟠 3. The production fit is in-sample on the season it predicts
`profiler.fit_calibration()` sets `cur_season = max(season)` and then
`select_window(rows, cur_season, 2)` — so the coefficient is fitted over the **last two seasons
including the target season's own games**, then applied to every round of it. `calibration.py`'s
docstring says fits use *"only matches strictly BEFORE the round being predicted (no leakage)"* —
true for the per-round walk-forward path (`evaluate.py`), **not** for the ingest path that
produces the live calibration. Consequence: stored-record accuracy is mildly optimistic (2
parameters over ~424 games, so small but real), and the documentation contradicts the behaviour.
**Fix:** either fit per round in the record path (the walk-forward already exists in `evaluate.py`),
or correct the docstring and state the in-sample caveat where the numbers are reported.

### 🟠 4. "window" carries three different meanings
`config.window_size = 30` (games, for the team matrix), `calibration.WINDOW_SEASONS = 2` (seasons,
for the fit), and the DB's `calibration.window` label (`'roll2'`/`'fallback'`). `calibration.py`
itself references the historical bug family this caused. **Fix:** rename to `matrix_window_games`
and `fit_window_seasons`; the label stays a label.

### 🟠 5. The projected total is a constant, so totals bias is definitional
`prediction.py:87`: `total = cal.total_mean`. Measured against the corrected results, the rebuilt
bias equals *anchor − season mean* in every season: 2021 159.2 → **+14.8**, 2022 166.1 → **+7.4**,
2023 167.4 → **+6.2**, 2024 168.7 → **+4.9**, 2025 168.6 → **+4.8**, 2026 178.6 → **−5.1**. Not a
bug — a design limit: totals accuracy cannot improve without a trailing or conditional estimate.
**Fix (optional):** projected total = recent-window scoring level (e.g. last N rounds, cross-season),
which removes the 2026 −5 immediately.

### 🟡 6. Hardcoded values with no fit provenance
`regression_factor = 0.75` (season rollover), `mean_rating = 1500`, the `/1.1` divisor factor, the
tier sizes 4/4/5, and the absolute tier thresholds. Each is either a reasonable convention or a
hand-fit; none records which, and none has a re-fit trigger. **Fix:** one comment block per
constant stating fitted-vs-convention and what invalidates it.

### 🟡 7. `PPG = 6.71` is duplicated across two files
`Core/player_props.py` and `Core/tools/props_backtest.py` both hardcode it, and the value came from
the pre-correction data. If it is a definitional constant (points per scoring pattern) say so once
and import it; if it is data-derived, fit it.

### 🟡 8. The score floor is a dead rail
`max(10, ...)` never fires in the current record (0 of 1,232). Harmless, but it means no projection
is ever lopsided enough to test it — either it is protective for future inputs or it is noise.

---

## Verified correct (checked, not assumed)

- **One grade ladder**, in `calibration.confidence_grade()` only; no second copy in the card or DB code.
- **No module-global calibration**: it travels on the ingestor (`ing.calibration`), guarded by
  `tests/test_no_global_calibration.py` — the old "two places disagree" bug class is closed.
- **One winner rule**: `align_margin` delegates to `engine_core.home_favored` (direction from the raw
  signal, Elo only sets size; dead-even → Elo side).
- **Provenance is enforced**: `source` distinguishes `fitted` from `fallback`, and
  `verify_state()` checks the fit fingerprint on load.
- **Tier cutoffs are derived**, not guessed, with midpoint boundaries that cannot equal a team's own
  rating (a real display bug fixed 2026-08-26).

## Suggested order

1. Findings 1 and 2 together — fail loudly, then re-derive the fallbacks from corrected data.
2. Finding 3 — decide per-round fitting vs documenting the in-sample caveat (this affects how every
   accuracy number should be read).
3. Finding 5 — trailing totals estimate if the 2026 scorelines matter for display.
4. Findings 4, 6, 7, 8 — naming and provenance tidy-up, one pass.
