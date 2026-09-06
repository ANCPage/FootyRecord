# Library-ization / modularization audit — FootyRecord (2026-09-05)

Lens: what should become library-shaped so future iterations and
customisations are configuration, not surgery. Audited the Liquid canvas
engine (the named example) plus the Python side for the same disease.

## 1. The Liquid engine: one 395-line <script> fused five concerns

`liquid/liquid_template.html` (395 lines of JS; 419KB total = embedded
Playfair font) is genuinely well-written but monolith-fused. The seams:

| Layer (current, interleaved) | Line refs | What lives there |
|---|---|---|
| **Theme/config data** | 16–40 | canvas dims, CREAM/ink ramp (NAVYINK/TAUPE/MUTED/FAINT), faces, BEATS B1–B4 @30fps, PFRAMES/TRAIL, SOFT-per-mode, stale NAVY/RED fallbacks |
| **Pure helpers** (framework-free) | 32–77 | mulberry32 RNG, easing fns, clamp01, lighten, smoothPath (Catmull-Rom), poss |
| **Path maths** | 176–228 | pointAt/tangentAt/spawnEvery/drainE — pure functions of a route + frame |
| **Draw subsystems** | 96–172 | drawChrome/drawAnchors/drawStreak (canvas state, no domain logic) |
| **Simulation + choreography** | 230–393 | particle lifecycle, spawn cadence, stagger/settle, beat timeline, mode branches (RECAP/NET/SOFT), verdict entrance, plate2, chips |

Future iterations that are currently surgery:
- a new card mode, a dark theme, an interactive hover, a different
  chapter timing, a 16:9 variant — each means editing inside `step()` or
  the top constant block of one file, and the mode branches (`if (RECAP ||
  NET)…`) are scattered through the simulation.

**Target shape (4 layers, same output):**
1. `liquid/theme.json` — ALL presentation constants as data (ink ramp, faces,
   beats, SOFT per mode, cream). Consumed by the engine AND by Python where
   the renderer needs the same numbers (SOFT currently lives only in the
   template, though render_card knows the mode — the same fact in two files).
   Also kills the stale line-17 `NAVY/RED` fallbacks (leftovers from before
   the club-colour system — DATA now always supplies colours).
2. `liquid/engine.js` — the reusable core: pure helpers + path maths +
   particle system. Framework-free, no chrome, no mode knowledge. This is
   the "library" Austin asked about — one input (routes + weights + theme),
   one output (particles per frame). Unit-testable in any JS runner (no
   canvas needed for the math half).
3. `liquid/choreography.js` — the *story* layer: beat timeline, stagger,
   settle, verdict entrance. Card modes register here as
   `choreo.register('net', {…config…})` instead of `if (NET)` branches.
4. `liquid/template.html` — thin shell: canvas + font embedding + the
   `__DATA__` slot + `engine(choreo, theme).play(DATA)`.

**Payload contract first:** the data JSON between `Core.cards` and the
engine is implicit dict keys. It already drifted once (verdict.projected was
added; template guarded with `|| []`). A card payload `version` field + a
schema check in render_card.py (assert the payload shape before it reaches
the template) is the glue that makes the split safe.

## 2. Python: three clusters, one big OOP win, two honest "keep functional"

**Visualizer family (`Core/visualize_matchup.py`, 1,305 LOC) — the win.**
Four draw_* functions (recap/prediction/net/full-matchup) share ~80%
scaffolding: layout constants repeated per function
(`gx, gy, gy2 = 0.5, 0.92, 0.08; R = 0.42; cx, cy = 0.5, 0.5`), axes
setup, the pos/pos_neg pair (pos_neg was 4 inline copies until today),
colour/normalisation blocks, label plumbing. This is where a class pays:
state + lifecycle + variance cluster together. Target: one
`MatchupCanvas` (or `FieldLayout`) object owning ax/fig/pos/palette/
normalisation, with `draw_*` becoming thin methods/strategies. Same
render output, no maths change.

**Honest "keep functional":** `Core/chains.py`, `Core/state_store.py`,
`Core/cards.py`, `liquid/geom.py` are stateless pure pipelines (input →
dict). Wrapping them in classes would add ceremony without state to hold.
They're already library-shaped as modules; cards payloads are plain JSON-
ready dicts by design (one-system + media path). Don't convert.

**Already class-shaped (keep):** `DataIngestor` (facade), `Calibration`,
`EloEngine`, `MatchupEngine` — the codebase already uses OOP where lifecycle
exists.

## 3. Cross-cutting restructure candidates

- **One field-geometry spec for both renderers.** `liquid/geom.py`
  (arc/funnel whorl) and `Core/geometry.py` (node_positions grid) are two
  projections of the same 15-zone field; the matplotlib visualizers and the
  canvas engine can never agree on a layout because neither reads the
  other. A single `field spec → positions` module (the Voronoi/web idea
  Austin floated lands HERE) would let one geometry drive every renderer.
  Bigger job; natural follow-on to the shared-web thread.
- **Packaging boundary (TODO #12).** pyproject declares `packages = ["Core"]`
  but scripts (evaluate.py, render_card.py…) run from the repo root and
  import Core as a flat namespace. Decide: `footyrecord` pip package ships
  Core + liquid (render_card, geom, capture); top-level *.py stay thin
  entrypoints/CLIs. This is what makes "a library" installable at all.
- **Theme duplication** (point 1): mode constants (SOFT, RECAP/NET
  semantics) exist in the template AND conceptually in render_card — theme.json
  + payload version closes it.

## 4. Durability (already good, verify only)

cdp_capture.py IS in the repo (not tmp-only); render_card.py is the one CLI;
the template + fonts committed. /tmp retains only session scratch.

## Suggested order
1. Payload version + schema assert (cheap, makes every later split safe).
2. theme.json extraction (pure data move; no visual change).
3. Engine/choreography JS split behind the same inline build step (fonts
   already inline; the build just concatenates three files).
4. visualize_matchup → MatchupCanvas class (biggest Python LOC win).
5. Geometry unification (follow-on, tied to the shared-web decision).
6. Packaging boundary decision (independent).

Rule for the whole programme: **no render output changes** — every step is
verifiable by identical frames from the capture harness.

## Resolutions applied (2026-09-05, commits 6ff + 37e2aef)
Slices 1-3 done + the contract-drift bug they were designed to catch:
- **Bug found first**: materialise emits goals in PX but the template
  re-projected them as data-space -> anchors + score plates ~188k px off-
  canvas since the one-system switch. Fixed; plates/anchors restored.
- **Slice 1**: CARD_PAYLOAD_VERSION stamped by cards, passed through geom,
  liquid/schema.validate_payload() guards materialised shape in render_card
  + build_html + tests (golden validate; tampered raises).
- **Slice 2**: liquid/theme.json (canvas/cream/ink/faces/beats/SOFT/field/
  seed); template reads THEME; stale NAVY/RED fallbacks removed; decay fill
  derived from CREAM.
- **Slice 3**: engine.js (reusable core) + choreography.js (story layer) +
  template.html thin shell + liquid/build_html.py (ONE build step).
- Verified PIXEL-IDENTICAL to the pre-split baseline (ImageChops diff None).
Slice 4 (MatchupCanvas in visualize_matchup) + packaging decision: pending.
