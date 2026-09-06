# Whole-system duplication audit — FootyRecord (2026-09-05)

Scope: every module (Core/, top-level scripts, liquid/) — not just the card
pipeline. Question: where does the same logic live twice?

## Verified clean (the architecture is mostly holding)

- **SQL has ONE home.** state_store.py (34 stmts) + results_db.py (11) are
  the only SQL-bearing modules; evaluate.py has 2 sanctioned write stmts.
  compute_round.py, predict_game.py, generate_round_images.py, scoring_graph.py
  carry ZERO SQL — the "no raw SQL outside Core" guard holds repo-wide.
- **compute_matchup is THE matchup entry.** 6 callers (cards, chains,
  prediction, compute_round, generate_round_images, predict_game); no script
  hand-rolls a delta. calculate_delta/fingerprint_overlay direct users are all
  Core modules that own that step.
- **Facades delegate.** engine_data.get_team_elo/tier/rankings/player_matrix
  all delegate to elo_engine/queries (checked bodies — no reimplementation).
- **Names + colours centralised** in Core/mappings (get_short_name + TEAM_DATA)
  — visualizers import, don't redefine.
- **Prior consolidations hold:** collapse_chain single impl (engine_core),
  old liquid exporters deleted, rotate_node central in Core/geometry.

## Findings

### 🟠 1. The winner-direction rule lives in TWO implementations
- `Core/engine_core.py home_favored()`: delta sign, Elo breaks dead-even.
- `Core/calibration.py align_margin()`: same rule re-encoded as
  `net_delta > 0 or (net_delta == 0 and elo_diff_hundreds >= 0)`.
- Both docstrings cite the same 2026-08-11 philosophy. This is the E1
  decision rule — if the two ever drift, predictions and visual verdicts can
  disagree on WHO WON a game without any test catching it (each module's own
  tests would stay green).
- **Fix:** one `decide_winner(net_delta, h_elo, a_elo)` helper in engine_core;
  `align_margin` delegates (it already holds the elo diff, sign is enough).

### 🟡 2. Delta-JSON reader triplicated
- `{TransitionEdge(*k.split('->')): v for k, v in json.loads(s).items()}`
  appears at state_store.py:74, state_store.py:196 (buckets), and
  results_db.py:142 — three copies of one format parse.
- **Fix:** one `delta_from_json(s)` in state_store; results_db + the bucket
  site import/call it.

### 🟡 3. The mirrored-position flip is inlined 5×
- `pos_neg = {k: (1.0 - x, 1.0 - y) ...}` at visualize_matchup.py:329, :605,
  :743, :898 and liquid/geom.py:34. Same projection flip, five spellings.
- **Fix:** add `flip_positions(pos)` to Core/geometry (sibling of rotate_node);
  all five call it. geom keeps its import (presentation may keep a thin alias).

### 🟡 4. The matchup-SQL clause is copy-pasted in state_store
- `AND ((home=? AND away=?) OR (home=? AND away=?))` + the 4-arg tuple in
  match_row, match_result, prediction_row, and at least one more — 4 copies
  of the same normalization.
- **Fix (optional, style):** private `_matchup_where(ta, tb)` returning
  (clause, args). Pure readability; SQL already sits in one file.

### 🟡 5. Name access is half-centralised
- cards.py rebuilds `NAMES = {k: v['name'] ...}` from TEAM_DATA instead of
  asking mappings; visualizers do `get_short_name(t_data['name'])` in-place.
- **Fix:** add `get_full_name(tid)` beside get_short_name in mappings; cards
  drops its dict; the `t_data['name']` chains collapse to one call.

### 🟢 6. API pair that reads as a duplicate (but isn't)
- `state_store.match_row` → `matches` table (ACTUAL scores, used by cards).
- `state_store.match_result` → `predictions` table (projection row incl.
  `correct` flag, used by compare_fingerprints).
- Same signature, same clause, different table — a future caller will get the
  wrong one. **Fix:** rename `match_result` → `prediction_result_row` (or
  docstring cross-reference each).

## Not worth touching
- `visualize_matchup._fallback_cal()` — one-line wrapper over
  Calibration.fallback; removing it saves nothing.
- Margin-size formula `cal.margin(net_delta, elo/100)` recomputed in draw
  paths — presentation calls with a passed-in cal; the DECISION comes from
  compute_matchup (finding #1 is the only real drift risk).
- Cards-era `_tup/_edge_tuple` string keys vs TransitionEdge keys — two
  representations of one edge, but they never meet in one function.

## Suggested order
1 → (winner rule; the only load-bearing one) then 2/3 (mechanical),
5/6 quick, 4 optional.
