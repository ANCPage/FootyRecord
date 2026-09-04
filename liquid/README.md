# Liquid — particle-flow card renderer (FootyRecord)

The "Liquid" visualisation: possession chains as particle-flow streams on the
fingerprint oval. Accepted direction for the delta-as-flow card (Sep 2026).

## Files

- `liquid_template.html` — canvas-2D particle engine. Reads a single inlined
  `__DATA__` JSON blob (chain paths + text layer). 900×1200 portrait.
- `export_game_recap.py` — exports a game's ACTUAL scoring chains (from the
  `chains` table) to the recap JSON, using the recovered goal-centred arc
  geometry (`arc_seg.py`). Data source: the honest matches table.
- `export_game_net.py` — exports the model's predicted scoring routes (net
  delta) for the pre-game card.
- `arc_seg.py` — goal-centred arc/funnel geometry (zones radiate from the
  goal, wide at the defensive end, converging at the pole). **Recovered from
  session records after a /tmp wipe destroyed the only copy — the original
  byte-exact template is NOT recoverable, this is the reconstruction.**
- `cdp_capture.py` — headless-Chromium CDP frame capture.

## Render a recap card (Sydney v North, R24 2026)

```bash
# 1. export chain geometry -> /tmp/liquid_data_recap.json
python3 liquid/export_game_recap.py

# 2. inline the JSON into the template (placeholder __DATA__)
python3 -c "
t = open('liquid/liquid_template.html').read()
d = open('/tmp/liquid_data_recap.json').read()
open('/tmp/liquid_render.html','w').write(t.replace('__DATA__', d))"

# 3. capture 480 frames @30fps (16s) then encode
~/footy-venv/bin/python liquid/cdp_capture.py file:///tmp/liquid_render.html /tmp/liqOUT 480
ffmpeg -y -v error -framerate 30 -i /tmp/liqOUT/f%05d.png -c:v libx264 -pix_fmt yuv420p -crf 20 recap.mp4
```

## History / honesty notes

- 2026-09-04 reboot wiped /tmp where the working renderer lived. The session
  DB kept only truncated (214-char) records of the final template, so the
  original is byte-unrecoverable. Rebuilt on: the recovered `arc_seg.py`
  geometry, pixel-measured typography vs the shipped video, and iterated web
  parameters. Visually close; the original's exact per-chain bow/weave
  texture is approximated.
- The `predictions` table stores the model's PROJECTED scoreline; `matches`
  stores the ACTUAL result — prediction cards and recap cards must read the
  right table (this is enforced per card type, never mixed).
- GitHub backup of this directory was the trigger for preserving it here.
