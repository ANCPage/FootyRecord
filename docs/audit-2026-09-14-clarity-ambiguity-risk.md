# FootyRecord: clarity, ambiguity and risk audit — 2026-09-14

Scope: what is unclear, ambiguous or risky in the system as it stands. Every finding below
was verified by running something, not by reading. Verified-correct items are listed too,
so the report shows what was checked rather than only what was hunted.

---

## Status of each finding (updated 2026-09-14, same session)

| # | Severity | Status |
|---|---|---|
| 1 | 🔴 | **CLOSED by decision** — claim dropped; the real function (`state_store.verify_state`) stays |
| 2 | 🔴 | **FIXED** — extraction now uses the feed's `stat_teamId`; gate re-run below |
| 3 | 🔴 | **FIXED** — fails fast on an empty dir *and* on files that parse to zero matches, with the path and the env var named |
| 4 | 🔴 | **FIXED** — both sides use the same slot; a new test asserts consecutive windows differ by the games played |
| 5 | 🟠 | **FIXED (documentation)** — semantics written at the write site in `state_store.py`; the deeper question (do cross-team credits belong in a player profile?) is a decision |
| 6 | 🟠 | **FIXED** — `Settings.__setattr__` mirrors every assignment to the module constant, so the two reads can no longer disagree |
| 7 | 🟠 | **CLOSED as lost → durable versions live in `Core/tools/`** |
| 8 | 🟠 | **PARTIAL → reverted to a CHECK** — deriving seeds from the DB ladder turned out to corrupt the bracket (new finding 13), so the snapshot stays authoritative and a mismatch now warns instead |
| 9 | 🟡 | **FIXED — and the premise was WRONG** (see below): the blocks close the figure and **re-raise**, so nothing was ever silently blank. The bare-except fix is the whole fix |
| 10 | 🟡 | **FIXED** — data-dependent tests now FAIL with instructions instead of skipping, and carry a `needs_data` marker for deliberate deselection (`-m "not needs_data"`) |
| 11 | 🟡 | **FIXED** — goals cache is schema-versioned; `rows.json` now has a sidecar fingerprint and warns loudly when the code has moved on |
| 12 | 🟡 | **CLOSED by decision** — leave the `~/racing-model` coupling as documented |

### Effect of fixing finding 2 (feed-side team attribution)

Volume held at the actual team score, 2025–26, 828 team-games / 20,080 player-games:

| | before (inferred side) | after (feed `stat_teamId`) |
|---|---|---|
| model allocation, 1+ goals | 0.1975 | **0.1963** |
| player-history allocation, 1+ | 0.2236 | **0.2214** |
| model allocation, 2+ goals | 0.0917 | **0.0911** |
| player-history allocation, 2+ | 0.1015 | **0.1011** |

Both sides improve slightly and the gap barely moves (11.7% → 11.3% at 1+, 9.7% → 9.9% at 2+),
so **the conclusions are robust to the bug** — but the numbers quoted earlier carried the error
and these are the ones to use. The leverage diagnostic still passes on both markets
(2025 slope +0.0606 [+0.0429, +0.0781], 2026 +0.0699 [+0.0464, +0.0931]; quartiles rising
+0.079 → +0.118 → +0.140 → +0.206).

---

## Original findings (detail)

## 🔴 HIGH — findings that can produce a wrong answer or a silent dead end

### 1. The promised persistent state-sync test module does not exist — CLOSED by decision
- **Evidence:** `tests/persistent/` is absent; `git log --all -- tests/persistent` is empty;
  `git ls-files | grep -i 'persistent\|hidden'` is empty; no stash; no reference to
  `hidden_test` anywhere in the repo.
- **Precision (important, so nothing real is thrown away):** the state-sync *function* is real
  and is called on every load — `Core/state_store.verify_state()` (state_store.py:319), invoked
  from `engine_data.py` with the CSV fingerprint. What never existed is the *persistent hidden
  test module* that earlier notes described as written and committed.
- **Decision (Austin, 2026-09-14):** **drop the claim.** Do not rebuild it as a hidden module.
  If state-sync coverage is wanted later, it goes in as a normal, visible test.
- **Impact:** anyone reading the session history would have believed a gate existed that did not.
  The audit doc is now the record of what is real.

### 2. Per-player goal attribution in `Core/tools/goals_extract.py` can put goals on the wrong side
- **Evidence:** `player_history` contains **5,734 (match, player) pairs carrying two teams**
  across 1,206 matches (9.7% of its 59,042 rows). Arbitrating each pair by which team's chains
  carry the player's credit mass: the tool's "last row wins" mapping agrees in only **49.3%**
  of cases, and **1,173 of 29,605 goals (3.96%)** sit on a mis-mapped pair.
- **Impact:** team goal totals (`vol_actual`) and per-player club membership in the props
  backtest are wrong for ~4% of goals. The headline gate numbers (0.1975 vs 0.2236 at 1+)
  carry that error bar.
- **Fix:** the raw CSV rows already carry `stat_teamId` — the authoritative side. Capture it in
  the extractor and re-run; that removes the arbitration problem entirely.

### 3. An empty/missing data directory fails silently, then crashes downstream
- **Evidence:** `python Core/finals_project.py` without `FOOTYRECORD_DATA_DIR` produced
  `match_info 0 | positions 0 | chains 0`, then died with
  `SystemExit('no profile for CD_T80 v CD_T20')`. `Core/config.py` defaults `DATA_DIR` to the
  repo's `CSV_DATA`, which does not exist on the code mirror.
- **Impact:** the error names neither the cause (no data) nor the fix (env var). Two runs
  wasted today chasing a "model bug" that was an empty input. An empty engine is a valid
  state everywhere and is never reported as one.
- **Fix:** fail fast in `DataIngestor.load_all_data()` — if zero matches load, raise with the
  data dir path printed. Cheap, and it converts a confusing crash into an instruction.

### 4. `tests/test_window_alignment.py::test_window_counter_uses_only_window_games` is broken
- **Evidence:** the test compares `window_counter(round 23)` = **673** chains against the
  chain count of the **round 24** window = **679**. Against its own window (673) the engine
  matches exactly.
- **Impact:** the engine is right and the test is wrong, so the suite has a **permanent
  failure** — which trains everyone to ignore red in the test output, hiding real breakage.
- **Fix:** make both sides use the same round (a one-line change), and assert separately that
  consecutive rounds' windows differ by exactly the games played.

---

## 🟠 MEDIUM — ambiguity that will bite the next person

### 5. `player_history` mixes a player's own-team and opposition-chain credits
- **Evidence:** the same player appears under both team labels in 5,734 match-player pairs;
  the mislabelled side carries tiny mass (e.g. `{"D3->C2": 0.0625}`) while his own side carries
  his real profile (`{"E2->SCORE": 2.0, ...}`).
- **Impact:** any player-level consumer keyed on `(team, player)` silently includes opposition
  possessions in that player's credit. Shares are diluted; nothing documents this. The model's
  team matrices are unaffected (they key on the chain's team), but the data-layer semantics are
  ambiguous as written.
- **Fix:** document the semantics in `state_store.py` where the rows are written, and decide
  explicitly whether cross-team credits belong in a player's profile (they probably belong to
  a separate "defensive involvement" field).

### 6. Two ways to read configuration, with different behaviour
- **Evidence:** `config.config.data_dir` (the mutable `Settings` object) appears 18 times;
  `config.DATA_DIR` (the module constant) appears 26 times. Runtime mutation of
  `config.config.data_dir` does not affect the module constant. This bit us today:
  `AttributeError: module 'Core.config' has no attribute 'data_dir'`.
- **Impact:** "which one is live?" is unanswerable from the call site. Tests or scripts that
  override one and read the other get a silently different path.
- **Fix:** one accessor (`config.data_dir()` or the settings object only), module constants
  private, and a test that asserts an override propagates.

### 7. Scratch analysis now lives in two places
- **Evidence:** the props work is committed under `Core/tools/`, but the illustrative scripts
  (`/tmp/examples.py`, `/tmp/h2h.py`, `/tmp/validate_players.py`, `/tmp/matchup_slice.py`,
  `/tmp/blend_step.py`, `/tmp/gate1_props.py`, `/tmp/edge_analysis.py`) are still in `/tmp`
  and will vanish on reboot.
- **Impact:** results in the session log become unreproducible.
- **Fix:** promote the ones worth keeping (each is small) or delete them deliberately.

### 8. Hardcoded season fixtures in the model path
- **Evidence:** `Core/finals_project.py:36` hardcodes `SEEDS = {1: 'CD_T60', ... 10: 'CD_T30'}`;
  `fingerprint_export.py:127` hardcodes six fixtures.
- **Impact:** next season the finals projector would silently project a bracket built on this
  season's seeds. It fails loudly only if the ids happen to be absent.
- **Fix:** derive seeds from the ladder in the DB; keep the hardcoded set only as a `__main__`
  demo.

---

## 🟡 LOW — housekeeping / decisions to make explicit

9. **Ten bare `except:` clauses**, all in `Core/visualize_*.py`. **CORRECTION (verified after
   the first pass): the premise of this finding was wrong.** Every one of those blocks does
   `plt.close(fig); raise` — the figure is closed and the exception propagates, so no visual was
   ever silently blank. The real (smaller) issue was only that a bare `except` also catches
   `KeyboardInterrupt`/`SystemExit`; that is fixed by narrowing them to `except Exception:`.
   No error-state drawing is needed. A repo-wide scan found **zero** swallow-and-pass sites in
   `Core/`.
10. **17 `pytest.skip` calls** across the suite. Most are legitimate environment guards, but
    each one is an untested claim that can go stale unnoticed (the gate tests skip when the
    row cache is missing).
11. **Cache staleness in the new tools.** `~/.cache/footy-props/goals.json` and `rows.json`
    have no version or input fingerprint, so they survive code changes — the exact failure mode
    this project was already bitten by with pickle caches. Add a fingerprint (source hash +
    engine settings) or regenerate unconditionally in CI.
13. **🔴 The DB's 2026 ladder does not reproduce the finals seeding** (found while trying to make
    finding 8 dynamic; 2026-09-14). Ranking the 207 home-and-away matches in `matches` gives
    Geelong **17W → 3rd** and Brisbane **15W → 4th**, but the played finals were seeded
    Brisbane 3rd and Geelong 5th (QF1 Fremantle v Hawthorn, QF2 Sydney v Brisbane). Same for
    Hawthorn (5th vs seeded 4th), Melbourne (6th vs 7th), Adelaide (7th vs 6th), Carlton
    (9th vs 10th). No ordering of the DB's numbers — wins or percentage — reproduces the
    seeding the games imply, so either the 2026 H&A scores in the DB are not the real ones or
    the seeding rule is not plain ladder order. **This matters well beyond the bracket:** the
    2026 accuracy numbers (71% tipping, the margin/edge analysis, the props backtest) are all
    measured against these same results. Needs explaining before 2026 numbers are quoted as
    fact. Attempting the dynamic switch silently re-projected played games (PF1 became
    Fremantle v Sydney, premier flipped from Fremantle to Geelong) — which is exactly why the
    change was reverted.

14. **🔴 CONFIRMED against an independent source: the stored 2026 scores are not the official
    scores, and 8 games have the wrong winner.** Verified 2026-09-14 by comparing all 207 DB
    home-and-away matches with the AFL's public results (Squiggle API, `?q=games&year=2026`):
    - **181 of 184 matched fixtures (98.4%) have a score that is not the official one**, and the
      stored figure is always **lower** — the DB is systematically light.
    - **8 games (4.3%) have the wrong winner:**

      | round | fixture | DB | official |
      |---|---|---|---|
      | R4 | Hawthorn v Geelong | 83-90 (Geelong) | 92-91 (Hawthorn by 1) |
      | R6 | Melbourne v Brisbane | 100-100 (draw) | 104-102 (Melbourne) |
      | R8 | Collingwood v Hawthorn | 92-89 (Collingwood) | 93-93 (draw) |
      | R13 | Adelaide v Geelong | 69-69 (draw) | 75-74 (Adelaide) |
      | R17 | Geelong v Brisbane | 95-89 (Geelong) | 101-123 (Brisbane by 22) |
      | R17 | Gold Coast v Collingwood | 95-91 (Gold Coast) | 98-104 (Collingwood) |
      | R22 | Adelaide v Richmond | 47-51 (Richmond) | 63-54 (Adelaide by 9) |
      | R23 | Hawthorn v Collingwood | 91-90 (Hawthorn) | 92-92 (draw) |
    - **Cause (two parts, both upstream of the model):** the ingested `matchPlays` feed carries
      only player-attributed stats, so scoring nobody is credited with (rushed behinds) never
      reaches the CSV; and in some matches whole goals are absent too (R22 is missing ~19 points
      ≈ 3 goals), which means those matches' *chains* are short — not just their scoreboard.
    - **What it invalidates:** the "actuals" the model is graded against and updates Elo from, so
      the 2026 accuracy figures (71% tipping = 147/207), the margin/edge analysis and the props
      backtest are all measured against results that are wrong for roughly one game in 25, and low
      by a few points in almost every game. For matches with missing goals, the model's *inputs*
      (positions, matrices, ratings) are short too.
    - **FIXED 2026-09-14 (same day).** Scores now come from the official score block, fetched per
      season into `<data dir>/official_scores_<season>.json` (`Core/tools/official_scores.py`) and
      applied during ingest (`engine_data.load_all_data`, falling back to chain-derived scores when
      a match is missing from the sidecar). Chains remain the spatial truth — the engine keeps
      empty-player rows out of the grid/player arrays, so positions and matrices are unchanged.
      `Core/tools/reingest.py [--force]` does ingest + profile + save and then VERIFIES against the
      official feed, so "re-ingested" cannot be mistaken for "done".
      **Verified after the re-ingest:** 2021 179/179, 2022 180/180, 2023 184/184, 2024 183/183,
      2025 184/184 exact against the official scores with **0 winner flips**; 2026 has zero stored
      matches differing from its sidecar (the only two without an official score are the unplayed
      round-28 preliminary finals).
      **What it changed in the model (refit at ingest):** totals baseline **164.9 -> 173.7** (+8.8
      points — the old "+6.2 totals bias" was the light data, not the model), margin slope
      **110.03 -> 113.17**, Elo term 3.48 -> 3.69. 2026 tipping measured on corrected results:
      **72.9%** (quoted as ~71%); margin bias **−6.5** points (was −7.0, so the shrinkage is real and
      slightly less severe than measured); margin MAE 21.8.
      **Consequence for the cards:** projected scorelines have been ~9 points light; the next
      render will move.
      **Still outstanding:** the stored projections were made with the old history. They have been
      re-graded, but rebuilding them means re-running the season's predictions end to end — a
      separate, larger job.
    - **Tool:** `Core/tools/score_provenance.py` — default mode compares DB against the chain feed;
      `--ladder` rebuilds the ladder from the match score block; `--squiggle` compares against the
      official results and lists the flipped winners (the verification above).

15. **The finals seeding now has an explanation** (this was finding 13): with the *official*
    scores the ladder's top three match the played seeding (Fremantle, Sydney, Brisbane), which the
    stored scores could not produce (they put Geelong 3rd on 17 wins). Geelong/Hawthorn remain
    swapped at 4th/5th in both third-party ladders and the 8-10 tail still differs slightly from
    the seeding's Bulldogs/Collingwood/Carlton order — a small, still-unexplained residual
    (tiebreak detail, or further missing scoring). `Core/finals_project.py` keeps the explicit seed
    snapshot and warns when the DB ladder disagrees instead of deriving from it.

12. **Cross-project coupling for odds credentials:** `Core/tools/odds_fetch.py` reads the
    Betfair cert, key and creds from `~/racing-model/`. Documented in the file, but this repo
    now depends on another project's config living where it does.

---

## ✅ Verified correct (checked, not assumed)

- **Determinism, including the projection path:** two runs under `PYTHONHASHSEED=0` and `=1`
  produced byte-identical bracket output, both with the data mounted (PF1 Hawthorn 85–80,
  PF2 Fremantle 79–85, Grand Final Fremantle 82–83) and on the played-results path.
- **Engine window convention:** `chains.window_counter(2026, 23, 'CD_T100')` = 673 chains,
  exactly equal to the chains in that team's round-23 window. The docstring ("strictly before
  the slot") matches behaviour.
- **`import Core` resolves to the working repo**, not the SMB share:
  `/home/austin/footyrecord-local/Core/state_store.py`. The editable-install hazard found
  earlier today is fixed.
- **The props layer is read-only:** model tables hash identically before and after use
  (`tests/test_player_props.py::test_layer_is_read_only`), and the estimator refuses to invent
  a team total (prior-average fallback, never the model's projected score).
- **Git state is clean:** no untracked files, no `.bak`/`.orig`/`.patch` graveyards, three
  coherent commits for the player-markets work.

---

## Suggested order

1. Findings 2 and 3 (wrong-side goals; silent empty data) — both are small fixes that remove
   an error bar from published numbers and a class of wasted debugging.
2. Finding 1 (the missing gate) — decide: commit it or stop claiming it.
3. Finding 4 (the always-failing test) — one line, and the suite goes green, which makes the
   next real failure visible.
4. Findings 5–8 — documentation and accessor cleanups, best done in one pass.
5. Findings 9–12 — park or fold into the next touch of those files.
