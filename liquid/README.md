# Liquid — particle-flow card renderer (FootyRecord)

The "Liquid" visualisation: scoring chains as particle-flow streams on the
fingerprint oval. The game-level media language (accepted direction, Sep 2026).

## One-system architecture (2026-09-05, level 1)

The card's numbers ARE the model's numbers — there is no second set of
calculations:

- **Core/state_store.py** — the only place SQL lives. Liquid accessors:
  `match_row`, `game_chain_rows`, `window_scoring_rows`, `prediction_row`
  (returns the STORED per-edge delta — the exact object that made the call),
  `latest_elo`.
- **Core/chains.py** — canonical chain extraction + route weighting. The only
  way cards obtain chains: collapsed like the model's own edges, rotated into
  each team's attacking frame, decayed window counter + top80 selection.
- **Core/cards.py** — canonical payloads. Verdict/projected scores are the
  SHIPPED predictions row (E1 rule) when the fixture was recorded, else
  `compute_matchup`. Chain weights come from the STORED delta (`mirror_delta`
  gives the away frame's view of the same net). Nothing invents arithmetic.
- **Core/mappings.py** — club colours + `worn_colours(home, away)` policy.
- **liquid/geom.py** — presentation only: arc/funnel geometry, outward bow,
  arc-length resample, data→px map, `materialise()` (payload → template JSON).
- **liquid/render_card.py** — the ONE CLI entry (imports Core; no SQL).
- **liquid/liquid_template.html** — canvas particle engine (900×1200, inlined
  `__DATA__` JSON). cdp_capture.py captures frames; ffmpeg encodes.

Tests: `tests/test_liquid_cards.py` (one-system + golden counts + colour
policy); `tests/test_data_access.py` now scans `liquid/` — no SQL outside Core.

## Render a card

Run from the repo root (a full engine state is only needed for prediction
cards with no stored row, i.e. finals/futures):

```bash
# recap of a played game (uses the stored decision + matches actuals)
python liquid/render_card.py --mode recap --a CD_T100 --b CD_T160 \
    --home CD_T160 --season 2026 --round 24 --label 'ROUND 24'

# prediction: stored fixtures show the shipped call; unplayed ones compute
python liquid/render_card.py --mode pred --a CD_T10 --b CD_T140 \
    --home CD_T10 --season 2026 --up-to 24 --label 'FINALS WEEK 1'

# actual net of a played game
python liquid/render_card.py --mode net --a CD_T100 --b CD_T160 \
    --home CD_T160 --season 2026 --round 24
```

Then inline + capture (deterministic, 480 frames @30fps ≈ 4 min):

```bash
python3 -c "
import json
t = open('liquid/liquid_template.html').read()
d = open('/tmp/liquid_data.json').read()
open('/tmp/liquid_render.html','w').write(t.replace('__DATA__', d))"
~/footy-venv/bin/python liquid/cdp_capture.py file:///tmp/liquid_render.html /tmp/liqOUT 480
ffmpeg -y -v error -framerate 30 -i /tmp/liqOUT/f%05d.png -c:v libx264 -pix_fmt yuv420p -crf 20 card.mp4
```

## Honesty rules (audited — do not regress)

- `predictions` = the model's PROJECTED scoreline; `matches` = actual. Recap
  verdict shows the model margin (gold grammar); net card = actual margin;
  result payloads always read `matches` for actuals.
- Winner must be readable from the picture alone; the lean comes from the
  delta arithmetic, never a fake flourish.
- Club colours: home always primary; away flips to its real clash colour only
  when primaries clash (CIELAB dE < 60). White away guernseys render as
  ink-outlined white ribbons.
- The original template died in a /tmp wipe (2026-09-04); the session DB
  truncates big records — pipeline code lives HERE, committed, and any
  renderer work must never live in /tmp only.
