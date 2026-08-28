# FootyRecord Architecture Debt Closure — Implementation Plan

> **For Hermes:** implement task-by-task; each task is TDD (test first), verified, committed separately.

**Goal:** Close the 9 deferred architecture items from the 2026-08-26 review (items 1, 3, 4, 5, 6, 7, 10, 11, 12) plus 2 standing items, without changing a single prediction. The walk-forward record must stay byte-identical: 1,222 games, 813/1222 (66.5%), 2026 = 147/207 (71.0%).

**Architecture target:** strict layering — pure math (no I/O) → data access (repositories) → domain services → presentation → thin CLI. Each layer imports only from layers below it. No module-level mutable state.

**Tech stack:** Python 3.11, matplotlib, SQLite (one store at `~/footyrecord-results/footyrecord.db`), pytest (71 tests), ruff. Venv: `~/footy-venv/bin/python`. Repo: `/mnt/projects/FootyRecord`.

**Non-negotiable invariant for EVERY task:** after each change run
`~/footy-venv/bin/python evaluate.py` and confirm `1222 games | 813 correct (66.5%)` and `2026: 147/207 (71.0%)`. If the number moves, revert the task.

---

## Phase 0 — Safety net (do first, once)

### Task 0.1: Golden-record regression test

**Objective:** Lock the record so any refactor that changes a prediction fails loudly.

**Files:**
- Create: `tests/test_golden_record.py`

**Step 1: Write the test**

```python
"""Golden-record guard: the walk-forward record must never change during refactors."""
import pytest
from Core import results_db

GOLDEN = {
    'all': (813, 1222),
    2026: (147, 207),
}

@pytest.mark.skipif(not results_db.db_exists(), reason="results DB not present")
def test_record_unchanged():
    conn = results_db.connect()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(correct),0), COUNT(*) FROM predictions WHERE played=1"
        ).fetchone()
        assert (row[0], row[1]) == GOLDEN['all']
        s = conn.execute(
            "SELECT COALESCE(SUM(correct),0), COUNT(*) FROM predictions "
            "WHERE played=1 AND season=2026"
        ).fetchone()
        assert (s[0], s[1]) == GOLDEN[2026]
    finally:
        conn.close()
```

**Step 2:** Add `db_exists()` to `Core/results_db.py` if absent:

```python
def db_exists() -> bool:
    return os.path.exists(DB_PATH)
```

**Step 3: Run** → `~/footy-venv/bin/python -m pytest tests/test_golden_record.py -v` → expect 1 passed.

**Step 4: Commit** → `git commit -m "test: golden-record guard for refactor safety"`

---

## Phase 1 — Item 4: kill the `cal.current` global (highest bug-history value)

**Why first:** it is the smallest of the shaping items and the one that has actually caused bugs (the `config.config.window_size` class of error). 12 call sites, all mechanical.

Current state (verified): `Core/calibration.py:172` declares `current: Calibration = Calibration.fallback()`; assigned at `engine_data.py:115,189,232`; read at `compute_round.py:61,63`, `evaluate.py:39,42,72`, `predict_game.py:113,118`, `refit_hyperparams.py:70`.

### Task 1.1: Make `Calibration` reachable from the ingestor (no behaviour change)

**Files:** Modify `Core/engine_data.py`

**Step 1:** Confirm `self.calibration` is always set after `load_all_data()` on both paths (cold ingest + cache load). Add to `load_all_data()` end:

```python
assert self.calibration is not None, "calibration must be set on every load path"
```

**Step 2: Run** `~/footy-venv/bin/python -m pytest -q` → 72 passed.
**Step 3: Commit.**

### Task 1.2: Thread the ingestor's calibration into `compute_round.py`

**Files:** Modify `compute_round.py:61,63`

**Step 1: Write failing test** — `tests/test_no_global_calibration.py`:

```python
def test_compute_round_uses_ingestor_calibration(monkeypatch):
    """compute_round must read calibration from the ingestor, not the module global."""
    import Core.calibration as cal
    sentinel = object()
    monkeypatch.setattr(cal, 'current', sentinel)  # poison the global
    src = open('compute_round.py').read()
    assert 'cal.current' not in src, "compute_round still reads the module global"
```

**Step 2: Run** → FAIL.
**Step 3:** Replace `cal.current` with `ing.calibration` at both sites.
**Step 4: Run** → PASS. Then `~/footy-venv/bin/python compute_round.py --season 2026 --round 24` and confirm output identical to before.
**Step 5: Commit.**

### Task 1.3: Same for `predict_game.py` (lines 113, 118)
### Task 1.4: Same for `evaluate.py` (lines 39, 42, 72 — note this one MUTATES `decay_factor`; pass an explicit override parameter instead)
### Task 1.5: Same for `refit_hyperparams.py:70`

### Task 1.6: Delete the global

**Files:** Modify `Core/calibration.py` (remove line 172), add to test file:

```python
def test_calibration_has_no_module_global():
    import Core.calibration as cal
    assert not hasattr(cal, 'current'), "module-level mutable state reintroduced"
```

**Verify:** full suite + `evaluate.py` record check + one round render.
**Commit.**

---

## Phase 2 — Items 3 + 12: repository layer and paths from config

### Task 2.1: Inventory raw SQL outside `Core/`

Run: `grep -rn "execute(\|sqlite3.connect" *.py | grep -v test`
Expected sites: `scoring_graph.py`, `analysis_charts.py`, plus any backtest scripts kept in-repo.

### Task 2.2: Add the missing repository functions

**Files:** Modify `Core/results_db.py` and/or `Core/state_store.py`

Add (TDD each, in-memory SQLite fixtures — pattern already in `tests/test_results_summary.py`):

```python
def scoring_chains(conn, season: int):
    """All SCORE-outcome chain rows for a season, ordered for grouping."""

def season_predictions(conn, season: int):
    """All prediction rows for a season (for analysis scripts)."""
```

### Task 2.3: Point `scoring_graph.py` at the repository
### Task 2.4: Point `analysis_charts.py` at the repository

### Task 2.5: Paths from config (item 12)

**Files:** Modify `Core/config.py`, then `compute_round.py:25,76`, `evaluate.py:211`, `predict_game.py:28`, `refit_hyperparams.py:45`, `regen_season.py:57`, `generate_round_images.py:376`, `analysis_charts.py:34`

**Step 1:** `Core/config.py` already has `DATA_DIR` and `OUTPUT_DIR`. Add:

```python
RESULTS_DB = os.environ.get('FOOTYRECORD_DB', os.path.expanduser('~/footyrecord-results/footyrecord.db'))
```

**Step 2: Write test** `tests/test_config_paths.py`:

```python
def test_no_hardcoded_csv_data_literal():
    import glob
    offenders = []
    for f in glob.glob('*.py'):
        src = open(f).read()
        if "DataIngestor('CSV_DATA')" in src:
            offenders.append(f)
    assert not offenders, f"hardcoded CSV_DATA in {offenders}"
```

**Step 3:** Replace literals with `config.DATA_DIR` / `config.OUTPUT_DIR` / `config.RESULTS_DB`.
**Step 4:** Verify record + one render. **Commit.**

---

## Phase 3 — Item 1: split `engine_data.DataIngestor` (480 LOC, 5 responsibilities)

**Approach:** extract by responsibility into modules that `DataIngestor` composes. `DataIngestor` stays as the public facade so no caller changes — this is the key to zero risk.

Verified current members: load (`load_all_data`, `_cache_fingerprint`, `_csv_fingerprint`) · profile (`profile_all_teams`, `_accumulate_positions`, `_recombine`, `_bake_players`) · calibration (`_fit_decay`, `_build_fit_rows`, `_fit_calibration`) · queries (`get_team_average_matrix`, `get_team_player_matrix`, `get_team_elo`, `get_team_tier`, `get_league_rankings`).

### Task 3.1: Extract the query methods → `Core/team_queries.py`

**Objective:** move the 5 read-only query methods to a `TeamQueries` class taking the loaded state.

**Step 1: Write the characterization test FIRST** (`tests/test_team_queries.py`) — call each of the 5 methods on a real loaded ingestor, snapshot the outputs to constants, assert they match. This is the safety net for the move.
**Step 2:** Create `Core/team_queries.py` with `TeamQueries`; move the methods verbatim.
**Step 3:** In `DataIngestor.__init__`, build `self._queries = TeamQueries(self)`; make the 5 old methods one-line delegations.
**Step 4:** Run the characterization test + full suite + record check.
**Step 5: Commit.**

### Task 3.2: Extract profiling → `Core/profiler.py` (same pattern, characterization test on `profile_all_teams` output first — compare a team's baked matrix before/after)
### Task 3.3: Extract calibration fitting → `Core/calibration_fitter.py` (assert fitted `decay`, `margin_b1`, `margin_b2` identical)
### Task 3.4: Extract cache load/save → `Core/cache_loader.py`

**After each:** `evaluate.py` record must be byte-identical. Any drift = revert that task.

---

## Phase 4 — Item 5: split `generate_round_images.py` (454 LOC orchestrator)

### Task 4.1: Extract the card-rendering loop → `Core/round_renderer.py`
### Task 4.2: Leave `generate_round_images.py` as a thin CLI/orchestrator (<150 LOC)
### Task 4.3: Verify by re-rendering R24 and diffing the PNG set (filenames + dimensions; content hash will differ only if layout changed — it must not)

---

## Phase 5 — Items 6, 10, 11: inversions, grab-bags, names

### Task 5.1 (item 6a): `models.py` must not import `theme`

Verified: `Core/models.py:39` does `from Core.theme import is_dark_color` inside a method. Move that presentation concern to the visualizer that needs it; `models` becomes import-free of presentation.

### Task 5.2 (item 6b): `state_store` → `results_db` DB_PATH inversion

Verified: `state_store.py:16-18` imports `results_db` purely for `DB_PATH`. Move `DB_PATH` to `Core/config.py` (Task 2.5 already adds `RESULTS_DB`); both stores import from config. Deletes the inversion.

### Task 5.3 (item 10): split visualizer grab-bags
- `Core/visualize_ladder.py` (ladder + journey + accuracy) → `visualize_ladder.py`, `visualize_journey.py`, `visualize_accuracy.py`
- `Core/visualize_story.py` (story + players) → `visualize_story.py`, `visualize_players.py`
- Verify: re-render R24, same filenames + dimensions.

### Task 5.4 (item 11): rename confusable modules

Candidates (needs decision — see open questions): `engine_core.py` / `engine_data.py` / `engine_scraper.py`, and `predict_game.py` / `prediction.py`. Renames touch imports everywhere; do last, one at a time, `git mv` + grep-replace + full suite.

---

## Phase 6 — Item 7: config schema

### Task 6.1: Add a typed, validated config

**Files:** Modify `Core/config.py`, create `tests/test_config_schema.py`

Use a dataclass with `__post_init__` range checks (no new dependency — the project has no pydantic and YAGNI says don't add one):

```python
@dataclass(frozen=True)
class EngineConfig:
    window_size: int = 25
    decay_factor: float = 0.5
    elo_k: float = 24.0
    def __post_init__(self):
        if not 1 <= self.window_size <= 200:
            raise ValueError(f"window_size out of range: {self.window_size}")
        if not 0.0 < self.decay_factor <= 1.0:
            raise ValueError(f"decay_factor out of range: {self.decay_factor}")
```

Test: valid config constructs; each invalid field raises `ValueError`.

---

## Phase 7 — Standing items

### Task 7.1: Run `refit_hyperparams.py` full 15-variant sweep
Fixed since the easy-wins commit, never run. Background job (`terminal(background=True, notify_on_complete=True)`), results to CSV. **Report only — do not adopt any variant without Austin's sign-off** (changing hyperparameters changes the record, which Phase 0's golden test will correctly block).

### Task 7.2: Verify or retire the desktop format
Verified still wired (`render_round.py:20`, `generate_round_images.py:104`). Either render one desktop round and vision-check it against the Option A changes, or delete the desktop path entirely. **Needs Austin's decision.**

---

## Files likely to change

**Core:** `engine_data.py` (split), `calibration.py` (global removed), `results_db.py` (+repo fns), `state_store.py` (inversion), `models.py` (theme import), `config.py` (paths + schema), `visualize_ladder.py` + `visualize_story.py` (splits), new: `team_queries.py`, `profiler.py`, `calibration_fitter.py`, `cache_loader.py`, `round_renderer.py`
**Scripts:** `compute_round.py`, `evaluate.py`, `predict_game.py`, `refit_hyperparams.py`, `regen_season.py`, `generate_round_images.py`, `scoring_graph.py`, `analysis_charts.py`
**Tests (new):** `test_golden_record.py`, `test_no_global_calibration.py`, `test_config_paths.py`, `test_team_queries.py`, `test_config_schema.py`

## Validation (every task)

1. `~/footy-venv/bin/python -m ruff check .` → clean
2. `~/footy-venv/bin/python -m pytest -q` → all pass
3. `~/footy-venv/bin/python evaluate.py` → `1222 games | 813 (66.5%)`, `2026 147/207 (71.0%)`
4. Phase 3+ only: `render_round.py --season 2026 --round 24` → 58 PNGs, all 900×1200, summary `6/9 | SEASON: 147/207 (71.0%)`

## Risks and tradeoffs

- **Facade-delegation (Phase 3) leaves indirection** — `DataIngestor` becomes a thin passthrough. Acceptable: it keeps every caller working and can be flattened later.
- **Renames (5.4) are the highest-churn, lowest-value item.** Consider skipping.
- **Phase 3/4 are the only tasks that could silently change output** — mitigated by characterization tests written *before* each move.
- **Effort:** Phase 1 ~1h, Phase 2 ~1.5h, Phase 3 ~3h, Phase 4 ~2h, Phase 5 ~2h, Phase 6 ~45m, Phase 7 variable. Total ~10-11h. Phases are independent and stoppable.
- **Doing nothing is defensible** — no bugs are open, 71 tests pass, and at 5.8k LOC the debt is not yet painful. This plan is insurance against the *next* engine bug, not a fix for a current one.

## Open questions (need Austin's answers before/at execution)

1. **How far do you want to go?** Phases 1-2 alone (~2.5h) close the two items with real bug history and leave the code measurably better. Phases 3-4 are the real restructuring (~5h). Phase 5.4 (renames) I'd skip.
2. **Item 11 renames — worth the churn?** My read: no. Every import in the repo changes for a readability gain. Confirm skip or give preferred names.
3. **Desktop format (7.2) — verify or delete?** Nothing has rendered desktop since the Option A work; keeping it means testing a layout you may never use.
4. **`refit_hyperparams` sweep (7.1) — run it?** If a variant beats the current fit, adopting it *changes the record* and every card. Run for information only, or not at all?
5. **Sequencing preference:** all-in-one session, or one phase at a time with a review between each? (Phases are designed to be independently stoppable.)
6. **New-module naming:** I've used `team_queries.py`, `profiler.py`, `calibration_fitter.py`, `cache_loader.py`, `round_renderer.py`. Any preference, or shall I follow the existing `engine_*` prefix convention instead?
