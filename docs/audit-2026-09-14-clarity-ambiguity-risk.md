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

14. **🔴 The stored 2026 results are built from a partial scoring feed, so some "actuals" are wrong**
    (found chasing finding 13; 2026-09-14). Two AFL endpoints disagree about the same match:
    - `sapi.afl.com.au/afl/matchPlays/{m_id}` — what the project ingests. Its chain rows carry only
      player-attributed stats, so scoring events with no player (rushed behinds, and in at least one
      case a goal) never reach the CSV. R15 example, Gold Coast v Collingwood: chains give
      **15g 5b = 95** and **14g 7b = 91**.
    - `api.afl.com.au/cfs/afl/matchItem/{m_id}` — the AFL's own match score block for the same match:
      **15g 8b = 98** and **15g 14b = 104**.
    The DB matches the chain-derived numbers (95-91), so the model is graded against, and updates Elo
    from, the lower set. Measured over all 207 home-and-away matches, the **winner differs in 8 games
    (3.9%)** once the match score block is used, and the total shortfall averages ~3 points a match.
    Example: R4 Hawthorn v Geelong — chains 83-90 (Geelong), score block 92-91 (Hawthorn by 1).
    **What this means:** the 2026 accuracy numbers (71% tipping, 147/207), the margin/edge analysis and
    every 2026 backtest are measured against results that are wrong for roughly one game in 25.
    **Why it is not fixed here:** correcting the scores changes the actuals, therefore Elo, therefore
    calibration and every published figure — a model-changing re-ingest that needs its own validation
    pass, not a silent patch.
    **Verification still open:** the winner-change count (8) rests on the `matchItem` score block. The
    two endpoints disagree, so before any re-ingest, an independent check is needed that the score
    block is the authoritative one (per-period sums in the payload came back empty, so that route did
    not work). The *direction* of the gap (DB light) is consistent across every sample checked, so the
    finding's substance is not in doubt; its exact size is.
    **Tool:** `Core/tools/score_provenance.py` (default mode compares DB vs chains; `--ladder` rebuilds
    the season's ladder from the score block and tests it against the finals seeding).

15. **The finals seeding cannot be reproduced from the stored season** (this is finding 13, restated
    with its cause now known): the ladder derived from the DB's light scores puts Geelong 3rd (17W) and
    Brisbane 4th; the played finals were seeded Brisbane 3rd and Geelong 5th. Rebuilt from the match
    score block, the ladder matches the played seeding in **8 of 10 places** — only Geelong/Hawthorn
    are swapped at 4th/5th (both 15W; 122.3% v 120.1%, so a tiebreak, or one more light game).
    **Consequence:** `Core/finals_project.py` keeps the explicit seed snapshot and now *checks* the DB
    ladder and warns on disagreement rather than deriving from it.

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
