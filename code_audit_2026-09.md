# Code & maths audit — Liquid one-system integration (2026-09-05)

Scope: the level-1 one-system build (Core/cards.py, Core/chains.py, the
state_store liquid accessors, Core/mappings colour policy, liquid/geom.py +
render_card.py, tests/test_liquid_cards.py) plus the maths it carries
(stored-delta weighting, mirror frames, net traffic, colour clash rule).
Full suite: 124 green (canonical SMB repo).

## Findings (severity-ranked)

### 🔴 1. Single-zone scoring chains are dropped from every card (one-system violation)
- **Issue:** `Core/chains.py` `game_chains()` and `window_counter()` require
  `len(zs) >= 2` AFTER collapsing consecutive same-zone events. Chains that
  collapse to ONE zone (repeated touches in one spot, then the shot — goal-
  square snaps) are discarded.
- **Evidence:** 1,533 of 10,040 (15.3%) of all 2026 SCORE chains collapse to
  a single zone. The engine's own `collapse_chain` (engine_core.py:151)
  explicitly keeps them: "A single-node chain yields one edge to SCORE (a
  direct shot)" — and the profiler counts those edges in the matrices.
- **Impact:** cards under-draw real scoring chains; the picture's weight
  diverges from the model's own matrix — exactly the two-systems drift the
  integration exists to prevent. Some games are unaffected (R24 Sydney had no
  len-1 chains), others lose several.
- **Fix:** gate on `len(zs) >= 1` (drop only empty chains); the shot edge is
  appended downstream anyway. Re-pin the golden counts in test_liquid_cards.

### 🟠 2. Compute path (finals/futures predictions) has no automated test
- **Issue:** `cards.pred_payload`'s non-stored branch (compute_matchup +
  elo_overrides) is exercised only by manual renders (EF, Adelaide-Bulldogs).
- **Evidence:** probe 2 proved the stored delta is byte-reproducible by
  compute (`mirror(stored)` ≡ `compute_matchup` on all 168 keys, 0 diffs) —
  the maths is sound, but nothing pins it.
- **Fix:** SMB-only test (skipif CSV fingerprint mismatch) asserting a stored
  fixture's compute payload equals the shipped row (winner/margin/projected),
  plus a mirror-equivalence assertion.

### 🟠 3. `chains.weight_chains` is dead duplicate code
- **Issue:** `Core/chains.py` defines `weight_chains()` (unused); cards.py
  has its own `_weight_end()` with identical logic and calls `chain_net`
  3× per chain (w2/s2/mS recompute the same mean).
- **Fix:** delete `weight_chains` OR make cards call it; compute the net once
  per chain. One weighting implementation, one home.

### 🟡 4. Error handling asymmetry in recap/net cards
- `recap_payload` silently falls back to actuals-as-verdict when the matchup
  has no stored prediction; `net_payload` raises. Add an explicit
  `match_row` existence check with clear errors (recap/net are played-game
  cards only).

### 🟡 5. `render_card --up-to` footgun: recorded games can silently COMPUTE
- Stored-row lookup happens at round `up_to + 1`. A caller passing
  `--up-to 24` for R24 gets slot 25 → no stored row → the card silently shows
  a fresh computation instead of the SHIPPED decision (E1). For recorded
  rounds the shipped call is the truth.
- **Fix:** auto-detect: when a stored row exists at `up_to + 1` use it (current
  behaviour); add `--slot` override + a warning when computing a fixture that
  IS in the record (i.e., when a row exists at some round ≤ 24 for the same
  teams — suggest that round instead).

### 🟡 6. Open content decisions (tracked, not bugs — need Austin's ruling)
- Recap cards show the MODEL margin (BY 23 on a game won by 55) — flagged to
  Austin 2026-09-05, not yet ruled on.
- No confidence/grade signal on near-even tips (BY 2 sits in the model's
  worst band).
- "FINALS WEEK 1" is Squiggle's flat label; the EF card wasn't named an
  elimination final.

## Verified correct (checked, not just hunted)

- **mirror_delta ≡ recompute:** `mirror(stored-home-delta)` matched
  `compute_matchup(away, home).delta` exactly on 168/168 union keys (>1e-9:
  0) — the single-source delta approach and the rotation/negation maths are
  sound, and the engine reproduces the stored record byte-for-byte.
- **Shipped-verdict rule:** pred payloads on recorded fixtures equal the
  stored predictions row exactly (winner, margin, projected A-first) — pinned
  in tests for R24 + R12.
- **Net card honesty:** canonical R24 net totals lean the actual winner
  (bottom Sydney 11.73 vs top North 1.50 mS); verdict = actual margin 55.
- **Colour policy:** worn_colours triples pinned (Geelong-Carlton → white
  away; Adelaide-Bulldogs → red away; Sydney-Brisbane → no flip).
- **One-system guards:** data-access tests now scan liquid/; recap/net (and
  pred-on-recorded) need no CSV engine load — they read state_store directly.
- **Geometry determinism:** materialise is seeded; renders byte-stable.
- Engine `collapse_chain` (single-node → shot edge) matches chains.py's
  intent except for the len gate in finding #1.

## Housekeeping (no action)
- state_store liquid accessors appended at file end — fine.
- Overlapping window queries (window_scoring_rows vs
  scoring_chain_start_zones) are separate outputs — fine.
- Template `verdict.projected || []` guard makes recap/net payloads without
  projected safe — intentional (scoreline is a pred-only reveal).

## Resolutions applied (2026-09-05, commits after aa823cc)
- **Item 1 (🔴):** chain gates now `len >= 1` in game_chains + window_counter.
  Recap R24 counts restored to exactly 20/38 (the 17/31 shortfall WAS the
  dropped direct shots). Golden test re-pinned.
- **Item 3 (🟠):** deleted dead chains.weight_chains; cards weights compute
  chain_net once per chain (_weight_end + net build).
- **Item 2 (🟠):** SMB-only tests added — compute reproduces the stored delta
  exactly (168-key equivalence pin) + finals compute-path verdict test.
