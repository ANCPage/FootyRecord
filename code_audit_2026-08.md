# Code Audit Report — FootyRecord (AFL Tactical Prediction Engine)

**Date:** 2026-08-09
**Scope:** Full codebase review: `Core/` engine + visualizers, root scripts (predict/backtest/scraper/dashboard), data pipeline, docs.
**Method:** Line-by-line reading of all engine modules, empirical data verification (grid frame, scoring distributions), plus the resolved LFP→FB rendering-bug audit (see `audit_conclusion_table.py`).

---

## 0. Executive Summary

The architecture is genuinely good — a clean 4-layer pipeline (scraper → ingestion → graph engine → visualizers) with pure, unit-testable math at the core (`Graph`, `MatchupEngine`, `EloEngine`). The data frame model (team-relative 5×3 grid) is **empirically sound**: all scoring events in sampled matches land at the forward end for both teams in all quarters, so the 180° rotation scheme is legitimate. The vendor's y-axis (left/right) was never verified against ground truth, but it is prediction-neutral (a global mirror cancels in every delta) and no feature makes a directional claim — **closed as accepted risk (2026-08-11);** any future left/right feature verifies it with one known play.

The main findings, in order of importance:

1. **No version control.** This is the highest-risk gap. No history, no rollback, no CI. It also explains the `.bak` file and 24 one-off "fixer" scripts in `LegacyScripts/` — they exist because there was no way to recover from bad edits.
2. **Elo ratings are trained on the model's own output** (delta sign), not real match results. **Decision (2026-08-09): kept by design** — tactical-Elo semantics ("rate teams by model-measured dominance, not scoreboard luck"). Watch items: tier/ladder labels read as absolute strength while the model is attack-only; `elo_weight` blending double-counts the delta signal (see E1).
3. **No weight normalization** — transition matrices are raw decayed sums, so teams with more/longer scoring chains dominate deltas. Volume is conflated with efficiency.
4. **Only scoring chains are modeled** (~65–70% of chains dropped) — **kept by design (2026-08-09)**; opponent scoring chains are already embedded (negated) in profiles, so the true blind spot is pressure/tempo, not defence. See E3.
5. The rendering double-rotation bug (the "LFP→FB" phantom) was found and fixed during this audit; the fix is in `vector_renderer.py` / `visualize_matchup.py` / `visualize_story.py`. A regression test for it is specified in §3.
6. A test suite is very feasible — the mathematical core is pure functions with no I/O.

---

## 1. Q1 — Logical & Mathematical Errors

### 1.1 Open issues (by severity)

| # | Severity | Issue | Location | Impact | Fix |
|---|----------|-------|----------|--------|-----|
| E1 | INFO | Elo "winner" = sign of model `actual_delta`, not the real scoreboard result | `Core/elo_engine.py` | **Kept by design (2026-08-09):** deliberate tactical-Elo semantics. Watch items: (a) tier/ladder labels (`ELITE`…`REBUILDING`) present it as absolute strength while the model is attack-only (see E3) — **RESOLVED (2026-08-10):** tiers are now distribution-relative (top-4/next-4/next-5 cutoffs from the live Elo field, fitted on ingestion — see E4 dynamic calibration); (b) `elo_weight` blending partially double-counts the delta signal (Elo is a smoothed function of historical deltas) — **RESOLVED (2026-08-10):** the legacy blend was dead once the fitted logit became the decision path; `elo_weight` removed from config, server and dashboard entirely (reduce pass). **A/B (2026-08-10, CLOSED):** results-trained Elo (scoreboard winner + margin, own dynamic divisor) tested walk-forward against the delta-Elo — 66.3%/0.2110 vs 66.1%/0.2107, statistically indistinguishable (±0.3% run noise). The delta-Elo already embeds the scoreboard signal implicitly (scoring chains drive deltas), so training on results directly adds nothing. **Delta-Elo kept with evidence.** The `results_based` flag remains in `EloEngine` as a tested experimental path. | No action — accepted. |
| E2 | ~~MEDIUM-HIGH~~ **FIXED (2026-08-09)** | No normalization of edge weights | `Core/engine_data.py:159-171` (accumulate), `211-219` (average by match count only) | ~~A team with more scoring chains (or longer chains) gets larger absolute matrix values, so `delta` partly measures chain *volume* not *efficiency*. Also chain-length bias~~ — fixed by normalizing each match's matrix by `sum(abs(w))` at storage time. G6 net delta: +15.494 → +0.1238 (same winner). **Follow-on (CLOSED 2026-08-10, A/B tested):** "re-add volume as an explicit feature" — tested via `get_team_average_volume` (pre-normalization activity weight) + log-ratio feature in the fitted logit. Result: no improvement (65.6% vs 66.0% acc; 0.2068 vs 0.2059 Brier; slightly worse OOS), reverted. Root finding: each team's matrix embeds the whole match (own chains +, opponent −), so the normalization denominator is identical for both teams — E2 only removed match-length scale, and team-level volume already lives in the delta's sign structure (corr(net_delta, log home/away chain-weight ratio) = 0.997). | Done. |
| E3 | INFO | Only SCORE-outcome chains are profiled | `Core/engine_data.py:141-142` (`if not has_score: continue`) | **Kept by design (2026-08-09):** scoring chains are where tactical intent is clearest; modeling turnover/stoppage chains is a research project, not a bug. Note: the profile matrices already embed a defensive-against signal (opponent scoring chains are rotated + negated into each team's profile). True blind spot = pressure (forcing turnovers) and non-scoring-chain tempo (attack volume itself is NOT lost — it lives in the delta sign structure, see E2). Action: one-paragraph design note in README when #18 is done. | No action — accepted. |
| E4 | ~~MEDIUM~~ **FIXED (2026-08-09)** | Margin model is a magic constant | `server.py:481` | ~~Hardcoded ×12 scaling~~ — replaced with regression fitted on the exact features the server uses. **Consistency update (2026-08-10, audit #1):** refit with NO intercept — `margin = 70.98·net_delta + 4.88·elo_diff` (413 matches, MAE 26.42 fit / 27.1 walk-forward; the free-intercept fit's +6.2 home bias contradicted PROB_B0=0 — no venue advantage now holds in every calibrated model). `analyze_margins.py` emits both fits. **Dynamic calibration (2026-08-10):** decision coefficients (probability, margin, total) are now re-fitted automatically on ingestion (`Core/calibration.py`, stored in the cache, rolling 2-season window) — no frozen constants in config; fallback constants bootstrap rounds with <60 prior matches. Walk-forward A/B (rolling-2 vs expanding): 65.3%/0.2127 vs 65.7%/0.2116 — essentially tied; rolling-2 kept (user decision, meta-tracking rationale). Every evaluated match is now out-of-sample by construction — the 2024/25 in-sample asterisk is gone. **Also dynamic (same pass):** Elo margin divisor D = median|actual_delta|/1.1 fitted on ingestion (config value is bootstrap only), and tier cutoffs are top-4/next-4/next-5 percentiles of the live Elo field (fixes the E1 watch item). **Hyperparameters scan-fitted (2026-08-10):** walk-forward grid over 1,189 matches → decay_factor 0.9→0.3, window_size 25→30 (65.0%→66.4% acc, Brier 0.2125→0.2107). Elo K (25.6/32/38.4) and regression (0.6/0.75/0.9) were flat — left as-is. Refit tool: `refit_hyperparams.py` (reproduces the grid, never edits config itself). **Cleanest-model (2026-08-10):** the probability layer was REMOVED — the margin is the single calibrated output (winner = margin sign; any percentage shown is a display transform). Measured A/B: margin-sign 66.27% vs logit 65.85% vs raw delta 66.36% — the fitted probability was the weakest decision boundary. Brier removed from the harness (margin MAE/RMSE are the honest errors); margin bands are the confidence display (predicted ≥12 → 83% actual win rate). | Done. |
| E5 | **MEDIUM** | Cache can go silently stale | `Core/engine_data.py:55-57` | `ingestor_state.pkl` invalidates only when a CSV mtime changes. Changes to code or config (decay factor, window size, grid logic) reuse stale profiles with no warning. | Stamp a schema/version + config hash into the cache key; regenerate on mismatch. |
| E6 | ~~LOW-MEDIUM~~ **FIXED (2026-08-09)** | Backtest evaluation is weak | `backtest_2025.py`, `backtest_2026.py` | ~~Winner-only accuracy, tiny sample, no calibration~~ — replaced by `evaluate.py` (walk-forward 2021-26, accuracy + Brier + margin MAE/RMSE + calibration table, n reported). **Dynamic-calibration update (2026-08-10):** harness refits coefficients before every round (no leakage; no in-sample seasons). **Hyperparameter update (2026-08-10):** with scan-fitted decay 0.3 / window 30 the baseline is 66.4% acc / 0.2107 Brier / 27.1 MAE (rolling-2) over 1,189 matches. **Lookahead check (2026-08-10):** decay/window are fitted on the full sample; a conservative a-priori evaluation (decay 0.4 / window 25) scores 66.27%/0.2112 — hyperparameter optimism inflates the headline by ~0.2 pts, negligible (within run-to-run wobble). Coefficients/Elo/profiles are strictly walk-forward. | Done (#10). |
| E7 | ~~LOW~~ **CLOSED (2026-08-09)** | Pre-season (round 0) matches pollute history | `engine_scraper.py:165` (`range(0,25)`), `engine_data.py:81-82` (only `>24` excluded) | **No action — misunderstanding.** Round 0 is a real home-and-away round (AFL "Opening Round" fixture with premiership points), so it correctly belongs in team histories. Not a bug. | Closed. |
| E8 | ~~LOW~~ **FIXED (2026-08-09)** | `norm_x`/`norm_y` columns contain raw coordinates | `engine_scraper.py:139` (writes `sx, sy, sx, sy`) | ~~Columns mislabeled with zero consumers~~ — columns dropped entirely from the scraper (main: `norm_x`/`norm_y`; simple: `x_norm`/`y_norm`). No code read them. **Data note:** CSV_DATA was cleared for a fresh full re-scrape once the audit changes are complete — the new CSVs will be clean from the start. | Done (#9). |
| E9 | ~~LOW~~ **FIXED (2026-08-09)** | Draw handling inconsistencies | `Core/models.py:98-101` (`winner` returns home on tie); `backtest_*.py:40` (tie → away) | ~~Inconsistent tie semantics across code paths~~ — all predicted-winner paths now use `home_favored()` (dead-even delta → fitted Elo gap decides); `MatchInfo.winner` is strict (`None` on draw). | Done (#6). |
| E10 | ~~LOW~~ **FIXED (2026-08-09)** | Legacy HUD retains the old (buggy-class) goal handling | `Core/main.py` `predict` | ~~CLI `predict` drew through TacticalHUD (pre-fix goal-only swap, old tie rule)~~ — `main.py predict` now routes through `MatchupVisualizer.draw_full_matchup`; `Core/engine_visualizer.py` (TacticalHUD) deleted. One drawing system remains. | Done (#7). |
| E11 | **DRY** | Grid mapping ×3, rotation ×4 | `engine_data._get_grid_cell`, `engine_scraper.get_grid_cell`, `models.Coordinate.to_grid`; rotation inline in `engine_core.Graph`, `predict_game.py:133-140`, `visualize_story.py` (fixed), `vector_renderer.py` (fixed) | This duplication is exactly what produced the LFP→FB bug class: one copy got "fixed" differently. Any future change must be replicated 3–4 times. | Single `Core/geometry.py` with `xy_to_grid()` and `rotate_node()`; delete the copies. |

### 1.2 Verified correct (checked, no issue)

- **Team-relative data frame** — empirically confirmed: in G6 R21, every scoring stat for both teams has positive x in every quarter (forward end constant). The engine's A=defensive/E=forward convention is valid.
- **No lookahead leakage** — `profile_all_teams` computes expectations before appending the current match's matrices; `get_team_average_matrix(up_to_round=R)` excludes rounds ≥ R; backtests use the same guard.
- **Score dedup order** — dedup check precedes Goal/Behind counting (flaws-doc item D is fixed in current code).
- **Elo season handling** — inter-season regression-to-mean, season-start Elos, and the final `POST_` rating are all correctly implemented (flaws-doc items B/C/E fixed).
- **Rotation math** — `rotate(rotate(x)) == x` holds; `calculate_delta` is antisymmetric under team swap (good property-test target, §3).
- **Scraper resilience** — retries with exponential backoff, token refresh on 401, malformed-row skipping in ingestion.
- **Grid mapping boundaries** — clamping at the oval edges is correct.

---

## 2. Q2 — What Is Required to Professionalise the Code

Ranked roadmap:

1. **Version control (do first).** `git init`, sensible `.gitignore` (`.cache/`, `__pycache__/`, `*.pkl`, `ROUND_IMAGES_UPDATE/`), initial commit. Everything else builds on this. The `.bak` file and `LegacyScripts/` fixer scripts exist because this was missing.
2. **Packaging.** `pyproject.toml`, `pip install -e .`, package imports instead of `sys.path.append('Core')` (currently in ~8 scripts). Pin dependencies. This also fixes the "run from the project root only" fragility.
3. **Single geometry module** (`Core/geometry.py`): `xy_to_grid()`, `rotate_node()`, zone labels. Deletes E11.
4. **Logging + lifecycle hygiene.** Replace `print` with `logging`; wrap all matplotlib figure creation in `try/finally: plt.close(fig)` (flaws-doc 4.B still open — bulk runs leak handles on exception); structured error handling in `generate_round_images.py` (one bad round shouldn't abort the batch).
5. **Config discipline.** Freeze settings in a validated dataclass; remove the mutable global `config` object (server + CLI mutating shared state is a thread-safety hazard); allow env-var overrides; stop mixing module constants (`WINDOW_SIZE`) with the `Settings` object.
6. **Cache versioning** (fix E5) — schema stamp + config hash in the pickle key.
7. **Evaluation harness** (fix E4/E6) — walk-forward backtest with calibration metrics; wire the margin regression into `server.py`.
8. **Type safety & docs.** Complete type hints (a few `Any`s remain), docstrings on public methods, `mypy --strict` in CI. `TeamProfile` dead import removed (it is imported but never used in `engine_core.py`, twice).
9. **CI.** GitHub Actions: lint (ruff), format check (black), `pytest` (§3), on every push/PR.
10. **README + doc refresh.** Mark `production_scripts_flaws.md` items as FIXED/OPEN (several are fixed: Elo reset/season-lock, dedup order, paths, non-scoring short-circuit, roster fetching; several remain open: session reuse, figure leaks, CLI stubs, DRY).
11. **Housekeeping** — see §4.

---

## 3. Q3 — Automated Test Suite

Very feasible: the engine core has no I/O and the visualizer placement logic can be made pure with a small refactor.

### 3.0 Required enabler (small refactor)

Extract two pure functions so they can be tested without matplotlib or data:
- `geometry.xy_to_grid(x, y, venue_length, venue_width) -> str` (already exists in 3 places — consolidate).
- `visualizer.physical_placement(edge, score, frame) -> (phys_start, phys_end)` — the exact logic in `vector_renderer.render_vector`, as a pure function. **This is the regression target for the LFP→FB bug.**

### 3.1 Test plan (pytest)

**Unit (pure, fast, no data):**
- `Graph.rotate_node`: all 15 zones + `SCORE`; property `rotate(rotate(x)) == x`.
- `Graph.add_edge_score`: opponent edges rotated AND negated; home edges untouched.
- `MatchupEngine.calculate_delta`: antisymmetry — `delta(a,b)[K] == -delta(b,a)[rotate(K)]`; empty matrices; zero-value handling.
- `xy_to_grid`: centre → `C2`; corners; oval-boundary clamping; invalid input → `""`.
- Decay math: `decay_factor ** (n - i)` edge positions; short chains vs long chains.
- `EloEngine`: deterministic known sequence (hand-computed ratings), season rollover regression, `get_team_elo` round boundaries, `POST_` final entry, draw = no update.
- **Regression (today's fix):** `physical_placement(TransitionEdge('A2','SCORE'), -15.2, frame='home') == ('A2','AWAY_G')` — asserts the arrow stays at the full-back zone instead of being mirrored to `('E2','AWAY_G')`.

**Integration (synthetic fixtures, no real API):**
- Tiny committed CSVs (2 teams × 3 matches × a few chains) in `tests/fixtures/`; run `DataIngestor` end-to-end; assert matrix values, match scores, winners, Elo history, and cache round-trip (save → load → identical state).
- Scraper: mock `requests` (auth token flow, 401 refresh, 404 skip, retry backoff).

**Evaluation:**
- Walk-forward winner accuracy + Brier score on fixture seasons; margin regression slope/intercept sanity (monotonic relationship between net delta and margin).
- Golden-image tests for visualizers are possible but flaky across matplotlib versions — prefer testing `physical_placement` math; add a smoke test that renders one matchup to an in-memory buffer without error.

**Property tests** (Hypothesis): grid mapping round-trips within the oval; delta antisymmetry over random sparse matrices.

### 3.2 CI

GitHub Actions workflow: `ruff check`, `black --check`, `pytest -x -q`, optional `mypy`. Target ~90% coverage on `engine_core.py`, `elo_engine.py`, `geometry.py`.

---

## 4. Q4 — Keep vs Remove

### Keep (with fixes noted above)

| Item | Reason |
|------|--------|
| `Core/` engine + visualizers | The actual product. Post-fix renderer is correct. |
| `CSV_DATA/` (619 MB) | Raw data is the model's fuel. Consider moving older seasons to an archive path; keep `.cache/` out of VCS. |
| `docs/`, `architecture.md`, `assessment.md`, `modular_oop_assessment.md`, `production_scripts_flaws.md` | Valuable institutional memory — update flaws doc status table. |
| `downloaded_fonts/` | Required by the design system. |
| `index.html` + `server.py` | The web dashboard — reuses the engine correctly. Fix the ×12 margin magic (E4). |
| `Experiments/` | Active research (Elo variants) — keep, ideally behind a `tests/`-adjacent harness eventually. |
| `PLANNING/` | Reference material. |
| `predict_game.py`, `generate_round_images.py` | Production scripts. (Superseded by `evaluate.py`/dynamic calibration and archived 2026-08-10: `backtest_2025.py`, `backtest_2026.py`, `analyze_margins.py`, `fit_calibration.py`.) |

### Remove / archive

| Item | Action |
|------|--------|
| `LegacyScripts/` (24 one-off fixer scripts + `backtest_log.txt`) | Archive to a zip (or let git history preserve them) and delete from the tree. They exist only because there was no VCS. |
| `Core/engine_data.py.bak` | Delete (this is what git is for). |
| `__pycache__/`, `CSV_DATA/.cache/` | `.gitignore` (keep the cache on disk for speed, but out of VCS). |
| `.agent-shell/` | Agent scratch artifacts — delete. |
| `investigate_lfp_fb.py`, `verify_lfp_fb_render.py`, `verify_lfp_fb_focus.py`, `audit_conclusion_table.py` | Fold the assertions into `tests/` (§3) and remove the scratch copies; keep `audit_lfp_fb.py` / `audit_model_lfpfb.py` as data-audit tools under `tools/`. |
| `Core/engine_visualizer.py` (`TacticalHUD`) | Retire once `main.py predict` routes through `MatchupVisualizer` (E10). |
| One-off scripts (`print_r4_2025.py`, `check_profiles.py`) | Delete or archive if no longer used. |

---

## 5. Appendix — Snapshot

- **~4,300 LOC** Python total (Core ~1,600; server.py 735; visualizers ~900; scripts ~1,100).
- **No git repository** (verified).
- 3 copies of the grid mapper; 4 copies of rotation logic; 1 dead dataclass import.
- Prior flaw doc status: 8 of its listed issues are already fixed in current code; ~6 remain open (noted inline above).
- **Fixed during this audit:** the away-edge double-rotation rendering bug (LFP→FB phantom). Files: `Core/vector_renderer.py`, `Core/visualize_matchup.py`, `Core/visualize_story.py`. Before/after renders: `audit_G6_Hawthorn_Norf_BEFORE.png` / `_AFTER.png`.

=====================================================================
RE-AUDIT 2026-08-12 — three angles (A: magic numbers · B: math/logic flaws · C: consistency)
Status: FINDINGS ONLY — no code changed. Fixes pending Austin's picks.
Method: full read of Core + scripts, empirical probes on the live DB
        (~/footyrecord-results/footyrecord.db, 1,204 walk-forward rows), pytest run.
=====================================================================

A. MAGIC NUMBERS WORTH RECONSIDERING
A1 [MED] analysis_charts.py:108 hardcodes `(133/189)` in the arc endpoint label —
    silently drifts when the record changes. Derive from cum[-1] and len(rows26).
A2 [MED] predict_game.py hardcodes 2026 in 4 places (match-id format, compute_matchup
    season, both DB writes) + the id format assumes 2-digit round/game. Breaks any
    non-2026 live prediction.
A3 [LOW] engine_data.py:109 `if r_num > 24: continue` — literal 24; config.MAX_ROUNDS
    (24) and GAMES_PER_ROUND (9) are DEAD constants nothing consumes. Unify.
A4 [LOW] calibration.MARGIN_TO_PROB_SCALE=20.0 — "display-only" transform whose
    provenance comment is confusing ("probit fit of |margin| vs RMSE (~34)"); the only
    consumer (prob_home) is never displayed since the server died. Remove or re-derive.
A5 [LOW] analysis_charts tier-panel color rule: `AMBER if a >= 55 else RED` with legend
    "At chance level (≈50%)" — a tier at 51-54% renders RED (= "at chance") while being
    above chance. Threshold + legend semantics disagree.
A6 [keep] confidence_grade bands (4..70), MIN_FIT_MATCHES=60, WINDOW_SEASONS=2,
    ELO_K=32, regression 0.75, mean 1500, clamps 0.5/3.0, bootstrap decay 0.3 /
    divisor 0.3, _fit_decay grid — chosen/fitted/standard, documented. No action.

B. MATHEMATICAL / LOGICAL FLAWS
B1 [MED-HIGH] save_rows_to_db back-derives net_delta from the ALIGNED margin
    ((m - b2*elo/100)/b1) instead of storing the raw net (available at row index 10).
    VERIFIED: 59/1,204 rows corrupted (mean |err| 0.086, max 0.34 — up to ~24 margin
    pts). No sign flips today, so winner re-derivation is safe, but the stored value
    is wrong for 4.9% of the record and any net_delta SQL/display (story card) is a lie.
    Fix: store net directly.
B2 [MED] refit_hyperparams.py is BROKEN — `n, acc, brier, mae, _ = aggregate(out)`
    unpacks a 4-tuple into 5 names (ValueError on the first variant; Brier was removed
    from the harness 2026-08-10). CSV header also still says brier. The documented
    refit procedure is dead — verified by repro.
B3 [HIGH] NULL elos in the record crash the renderer -> matchup cards SILENTLY SKIPPED.
    save_rows_to_db writes home_elo/away_elo/tier/rank = None (VERIFIED: 1204/1204 rows);
    generate_round_images passes them into draw_full_matchup which computes
    (elo_a - elo_b)/100.0 -> TypeError -> caught by the broad per-game except -> every
    G/STORY/PLAYERS card skipped while TIPS/ladder/journeys still render. The cards on
    disk PREDATE the current DB (mtime Aug 11 vs DB Aug 12) — the documented stale-card
    regen (render_round.py for R0-R21) would produce NO matchup cards at all.
    Fix: fill elos in the save path (cheap get_team_elo calls — the open concern #4) or
    fall back to pred values in the renderer.
B4 [LOW-MED] compute_round writes PLAYED games with live-calibration picks in mixed
    rounds (any unplayed game in the round -> ALL games computed incl. played, with the
    CURRENT fit) -> overwrites walk-forward rows with lookahead picks until the next
    evaluate.py --save. Latent (0 unplayed rows in DB now).
B5 [LOW] results_db.team_records counts unplayed games as losses — filter is
    `correct IS NOT NULL` but unplayed rows have correct=0; should be
    actual_margin IS NOT NULL. Latent.
B6 [LOW] results_db.upsert_round's INSERT omits the delta column — live-round rows get
    NULL delta (renderer falls back to live recompute: acceptable for unplayed games,
    but the two writers are asymmetric and INSERT OR REPLACE erases an existing delta).
B7 [LOW] run_mode out rows are now 11-tuples (net at index 10); docstrings in run_mode
    and save_rows_to_db still describe the 9/10-tuple. Tuple-layout drift is exactly
    what bit the harness before — update the docs + the aggregate layout test's comment.

C. INCONSISTENT / SEPARATE-FROM-THE-REST LOGIC
C1 [LOW] analysis_charts.py:24 is the ONLY sys.path hack left in the tree (project
    convention: zero path manipulation, RRR pass 2) — added after the sweep, and
    vestigial (Core.* imports work from repo root). Same file has dead code: `conf`
    list (lines 86-89) and the `ALL` query (lines 49-51) are computed, never used.
C2 [LOW] prob_home/prob_from_margin is vestigial — computed in compute_matchup, never
    displayed (server decommissioned); kept alive only by tests.
C3 [LOW-MED] state_store.load_state builds team_positions in match_positions DICT
    order — relies on SQLite rowid order of an ORDER-BY-less SELECT. The dead
    `sorted_ms` var (the one F841 ruff error in the main tree) shows the intended
    chronological order was dropped. Works today; fragile. Delete the var + order the
    iteration (or ORDER BY in the SELECT).
C4 [LOW] Player credits don't mirror the matrix accumulation — opponent chains are
    rotated+negated into the edge matrices but player credits track only the team's OWN
    players (no rotation/negation). Intentional for the "key drivers" frame, but the
    asymmetry between model layer and display layer is undocumented.
C5 [LOW] visualize_tips.py:92-94 dead expressions (0.22/fig_w, 0.038/fig_h) + the
    explicit bbox_inches='tight' save — the ONLY visualizer still tight-cropping after
    the 2026-08-10 aspect-ratio fix.
C6 [LOW] Same card set shows two different net_deltas: draw_full_matchup recomputes it
    from the delta matrix (line 108) while the story card gets the DB row's back-derived
    value (B1). Fixing B1 fixes this.
C7 [LOW] load_state vs load_all_data asymmetry: scoreless matches get actual_winners
    'DRAW' in the live path but NO key on load (guard `if hs and as_:`). No real 0-0
    games; unplayed fixtures are filtered from TIPS_RESULTS anyway.
C8 [LOW] prediction.py MatchupPrediction.edge docstring still says "fitted logit" —
    stale since cleanest-model; the code comment below it says the right thing.
C9 [LOW] Experiments/ holds ~131 ruff errors (sys.path hacks, import sorting) — legacy
    sandbox outside the ruff gate; consider archiving (git history preserves).
C10 [LOW] get_team_average_matrix dilutes the profile with scoreless matches (empty
    matrices count toward len(history)). No real impact (played games always score).
C11 [LOW] physical_placement allocates a fresh Graph("util") (16 nodes) per edge per
    panel — renderer perf nit, not a bug.

VERIFIED CORRECT (checked, no issue found)
- Elo history ordering: m_id TEXT order == chronological order (ids zero-padded;
  POST_ sorts last) — tier cutoffs / last-entry reads are safe. VERIFIED on the DB.
- No-lookahead: expectations computed before the match is appended; fit rows exclude
  same-round and future matches; select_window(season-1..season) semantics match
  production. Draws included per policy B everywhere.
- Margin model feature scale: fit divides elo_diff/100 and margin() receives /100 —
  consistent; the parameter name elo_diff100 is misleading, the math is right.
- calculate_delta antisymmetry, rotation involutive, squircle grid mapping continuity,
  E2 normalization, decay recombination, collapse_chain, align_margin == home_favored
  dead-even rule, confidence ladder shared by compute+render, draw handling (draws =
  misses) consistent across eval/DB/cards.
- Determinism: sorted iteration in calculate_delta holds (no set-order wobble).
- Margin-band pick accuracy healthy: [-12,-4) 53%, [-4,4) 54%, [4,12) 68%, >=12 84%,
  <=-12 70% (pick accuracy, home frame) — the confidence ladder tells an honest story.
- Tests: 59 collected (skill says 61 — count drift, 2 fewer than recorded).

---------------------------------------------------------------------
EASY-WIN SWEEP — DONE 2026-08-12 (fixes committed; tests 59/59, ruff clean)
A1 ✅ analysis_charts endpoint now derives (c/t) from the data; x uses rnds[-1]
    (PNG verified byte-identical — the label already matched the record).
A2 ✅ predict_game.py season parameterized (--season, default current year)
    + timeout on the roster GET.
A3 ✅ GAMES_PER_ROUND removed (dead); engine_data guard uses config.MAX_ROUNDS.
A5 (no action — verified no tier in (50,55), rule never misfires in current data)
B2 ✅ refit_hyperparams resurrected: 4-unpack, run_mode 3-unpack (second latent
    breakage), brier columns -> mae/rmse. Smoke-ran 7 variants (~33s each,
    decay 0.4 -> 66.6%, sane). Full run ~8 min.
B4 ✅ compute_round skips PLAYED games in mixed rounds (lookahead guard).
B5 ✅ team_records filter -> actual_margin IS NOT NULL.
B6 ✅ upsert_round now writes the delta column (22 cols).
B7 ✅ run_mode/save_rows_to_db/evaluate docstrings match the 11-tuple layout.
C1 ✅ analysis_charts sys.path hack + dead code (conf list, ALL query) removed.
C3 ✅ state_store team_positions built in explicit (season, round) order;
    the F841 dead var gone (ruff fully clean on the main tree).
C6 ✅ (fixed by B1? no — B1 pending) — draw_full_matchup still recomputes net
    from the delta matrix; converges once the save path stores the raw net.
C8 ✅ prediction.py edge docstring -> aligned margin.
C11 ✅ physical_placement no longer allocates a Graph per call.
C18 ✅ visualize_tips dead expressions removed (bbox_inches left as-is — the
    approved look depends on it).

SAVE-PATH UNIT — DONE 2026-08-12 (evaluate.py, re-saved + verified):
B1 ✅ net_delta stores the RAW net (not back-derived). VERIFIED: 0 mismatches
    (was 59), per-season record byte-identical (799/1204, 2026 133/189).
B3 ✅ home_elo/away_elo/tier/rank filled from the pre-match histories (0 NULLs
    was 1204; h_elo - a_elo == elo_diff verified on all rows). Renderer no
    longer crashes: R22 smoke render = 0 errors, 9/9 games full cards,
    summary matches the DB. Full R0-R22 regen COMPLETE 2026-08-12: 23/23
    rounds, 0 errors, every card's round + cumulative summary verified equal
    to the DB record (R22 card: 133/189 70.4%); all G/STORY/PLAYERS/
    expectation cards present desktop + mobile (R0=5 games, bye rounds 7-8,
    R1/R5-R11+ 9 — natural round structure).

REMAINING (report to Austin):
A4/C2 [LOW] prob_home/MARGIN_TO_PROB_SCALE vestigial — decision: remove or keep.
A5 [LOW] tier-panel >=55 color rule vs legend wording (latent, no current misfire).
C4 [LOW] player-credit asymmetry (document or align).
C7 [LOW] load_state vs load_all_data actual_winners asymmetry (scoreless games).
C9 [LOW] Experiments/ ruff debt (~131 errors) — archive or accept.
C10 [LOW] scoreless-match profile dilution (zero real impact).
C13 [LOW] tests count drift: 59 collected vs 61 recorded in the skill.
