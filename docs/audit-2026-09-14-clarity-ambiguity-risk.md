# FootyRecord: clarity, ambiguity and risk audit — 2026-09-14

Scope: what is unclear, ambiguous or risky in the system as it stands. Every finding below
was verified by running something, not by reading. Verified-correct items are listed too,
so the report shows what was checked rather than only what was hunted.

---

## 🔴 HIGH — findings that can produce a wrong answer or a silent dead end

### 1. `tests/persistent/` (the state-sync gate) does not exist and was never committed
- **Evidence:** `tests/persistent/` is absent; `git log --all -- tests/persistent` is empty;
  `git ls-files | grep -i 'persistent\|hidden'` is empty; no stash; no reference to
  `hidden_test` anywhere in the repo.
- **Impact:** the calibration/state-sync protection that earlier work in this session
  described as written and committed **is not in the repository**. Anyone reading the
  session history would believe the gate exists. It does not.
- **Fix:** either commit the gate as a normal (not hidden) module, or delete the claim.
  A gate nobody can find is worse than no gate, because it stops other work.

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

9. **Ten bare `except:` clauses**, all in `Core/visualize_*.py`. Rendering failures are
   swallowed to a blank or partial image. Visuals are model output, so a silent failure here
   is a trust problem: catch the specific exception and draw an error state instead.
10. **17 `pytest.skip` calls** across the suite. Most are legitimate environment guards, but
    each one is an untested claim that can go stale unnoticed (the gate tests skip when the
    row cache is missing).
11. **Cache staleness in the new tools.** `~/.cache/footy-props/goals.json` and `rows.json`
    have no version or input fingerprint, so they survive code changes — the exact failure mode
    this project was already bitten by with pickle caches. Add a fingerprint (source hash +
    engine settings) or regenerate unconditionally in CI.
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
