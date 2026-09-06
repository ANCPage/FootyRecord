#!/usr/bin/env python3
"""framecheck — visual regression harness for liquid cards.

Renders key frames of a fixture through the full pipeline (render_card ->
build_html -> chromium capture) and compares them against committed baseline
PNGs, so renderer refactors are provably pixel-safe.

Usage (repo root; needs the results DB reachable from Core.config):
  python liquid/framecheck.py                 # check against baseline (default R24 recap)
  python liquid/framecheck.py --fixture pred  # check the pred fixture
  python liquid/framecheck.py --update        # re-baseline after an APPROVED visual change
  python liquid/framecheck.py --frames 199,449

Exits 1 on any pixel drift. Baselines: liquid/regress/<fixture>_f<frame>.png
(committed). Captures are deterministic (seeded engine, frame-stepped CDP).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'liquid'))

FIXTURES = {
    # name: (mode, a, b, home, season, round/up-to, label)
    'recap': ('recap', 'CD_T100', 'CD_T160', 'CD_T160', 2026, 24, 'ROUND 24'),
    'pred': ('pred', 'CD_T100', 'CD_T160', 'CD_T160', 2026, 23, 'ROUND 24'),
    'net': ('net', 'CD_T100', 'CD_T160', 'CD_T160', 2026, 24, 'ROUND 24'),
}
BASE = os.path.join(ROOT, 'liquid', 'regress')
PY = sys.executable


def _capture(html_path, frames_dir, frames):
    out = subprocess.run([PY, os.path.join(ROOT, 'liquid', 'cdp_capture.py'),
                          'file://' + html_path, frames_dir, '1'] +
                         [str(f) for f in frames],
                         capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise SystemExit('cdp_capture failed: ' + out.stderr[-500:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixture', default='recap', choices=list(FIXTURES))
    ap.add_argument('--frames', default='199,449')
    ap.add_argument('--update', action='store_true', help='write new baselines')
    args = ap.parse_args()
    frames = [int(f) for f in args.frames.split(',')]
    mode, a, b, home, season, slot, label = FIXTURES[args.fixture]

    from liquid import build_html, schema
    from liquid.geom import materialise
    import Core.cards as cards
    import Core.chains as chains

    conn = chains.connect()
    kw = {'a': a, 'b': b, 'home': home, 'season': season, 'label': label}
    if mode == 'pred':
        payload, _st = cards.pred_payload(None, conn, **kw, up_to=slot)
    elif mode == 'recap':
        payload, _st = cards.recap_payload(conn, **kw, round_num=slot)
    else:
        payload, _st = cards.net_payload(conn, **kw, round_num=slot)
    out = materialise(payload)
    schema.validate_payload(out)

    os.makedirs(BASE, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        html_path = os.path.join(td, 'render.html')
        open(html_path, 'w').write(build_html.assemble(out))
        frames_dir = os.path.join(td, 'f')
        os.makedirs(frames_dir, exist_ok=True)
        _capture(html_path, frames_dir, frames)
        drift = False
        for f in frames:
            got = os.path.join(frames_dir, 'f00000.png')
            base = os.path.join(BASE, '%s_f%d.png' % (args.fixture, f))
            if args.update:
                subprocess.run(['cp', got, base], check=True)
                print('baseline updated: %s' % base)
                continue
            if not os.path.exists(base):
                print('NO BASELINE for %s (run --update first)' % base)
                drift = True
                continue
            from PIL import Image, ImageChops
            a_img = Image.open(base).convert('RGB')
            b_img = Image.open(got).convert('RGB')
            bb = ImageChops.difference(a_img, b_img).getbbox()
            if bb:
                print('DRIFT %s frame %d: diff bbox %s' % (args.fixture, f, bb))
                drift = True
            else:
                print('ok  %s frame %d: identical' % (args.fixture, f))
        sys.exit(1 if drift else 0)


if __name__ == '__main__':
    main()
