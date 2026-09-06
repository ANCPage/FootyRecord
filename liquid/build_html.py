#!/usr/bin/env python3
"""build_html — assemble the liquid render HTML (ONE build step).

Inlines theme.json + engine.js + choreography.js + the card JSON into
liquid/template.html's shell (slots __THEME__/__DATA__/__ENGINE__/__CHOREO__).
Output is a single self-contained HTML for the capture harness / browser.

Usage (repo root):
  python liquid/render_card.py  --mode recap --a CD_T100 --b CD_T160 ... (writes JSON)
  python liquid/build_html.py   --data /tmp/liquid_data.json --out /tmp/liquid_render.html

`--out` defaults to liquid/build/liquid_render.html (gitignored).
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from liquid import schema  # noqa: E402


def assemble(data: dict, template_dir: str = None) -> str:
    """theme + data + engine + choreography -> full render HTML."""
    d = template_dir or os.path.join(ROOT, 'liquid')
    theme = open(os.path.join(d, 'theme.json')).read()
    engine = open(os.path.join(d, 'engine.js')).read()
    choreo = open(os.path.join(d, 'choreography.js')).read()
    shell = open(os.path.join(d, 'template.html')).read()
    for token, body in (('__THEME__', theme), ('__DATA__', json.dumps(data)),
                        ('__ENGINE__', engine), ('__CHOREO__', choreo)):
        if token not in shell:
            raise SystemExit('build_html: %s slot missing from template.html' % token)
        shell = shell.replace(token, body)
    return shell


def main():
    ap = argparse.ArgumentParser(description='Assemble the liquid render HTML')
    ap.add_argument('--data', required=True, help='materialised card JSON (render_card --out)')
    ap.add_argument('--out', default=None, help='output html path')
    args = ap.parse_args()
    data = json.load(open(args.data))
    schema.validate_payload(data)          # fail fast on contract drift
    out = args.out or os.path.join(ROOT, 'liquid', 'build', 'liquid_render.html')
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    open(out, 'w').write(assemble(data))
    print('built %s (%d KB)' % (out, os.path.getsize(out) // 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
