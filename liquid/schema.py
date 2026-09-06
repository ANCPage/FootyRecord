"""Payload contract schema for the liquid card JSON (modularization audit
2026-09-05, slice 1).

`Core.cards` produces a data-space payload; `liquid.geom.materialise` turns
it into the template JSON (goals + px chains). This module validates the
MATERIALISED shape — the exact object the canvas engine consumes — so drift
between cards/geom and the template is caught with a clear error instead of
silent visual bugs (the goals px-vs-data-space regression, 2026-09-05).

The template is the contract's other half: every key it reads must exist.
"""
import re

MODES = ('pred', 'recap', 'net')
HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _err(msg):
    raise ValueError('liquid payload schema: ' + msg)


def validate_payload(p):
    """Assert `p` (the materialised payload) is safe for the template. Raises
    ValueError with the first violation; returns True."""
    if not isinstance(p, dict):
        _err('not a dict')
    if not isinstance(p.get('version'), int):
        _err("'version' missing (cards must stamp CARD_PAYLOAD_VERSION)")
    if p.get('mode') not in MODES:
        _err("'mode' not in %s" % (MODES,))
    if not isinstance(p.get('round_label'), str) or not p['round_label']:
        _err("'round_label' missing")
    for end in ('top', 'bottom'):
        t = p.get('teams', {}).get(end)
        if not isinstance(t, dict) or not isinstance(t.get('name'), str) or not t['name']:
            _err("'teams.%s.name' missing" % end)
        col = t.get('colour', '')
        if not HEX.match(col):
            _err("'teams.%s.colour' not a #RRGGBB hex (got %r)" % (end, col))
    v = p.get('verdict') or {}
    if not isinstance(v.get('winner'), str) or not v['winner']:
        _err("'verdict.winner' missing")
    if not isinstance(v.get('margin'), (int, float)):
        _err("'verdict.margin' missing")
    if 'grade' in v and not isinstance(v['grade'], str):
        _err("'verdict.grade' must be a string like 'D' (got %r)" % (v['grade'],))
    if p['mode'] == 'pred':
        proj = v.get('projected')
        if not (isinstance(proj, list) and len(proj) == 2
                and all(isinstance(x, (int, float)) for x in proj)):
            _err("pred cards need 'verdict.projected' = [a, b] scores")
    r = p.get('result')
    if not isinstance(r, dict) or not isinstance(r.get('home_name'), str):
        _err("'result.home_name' missing")
    if not isinstance(r.get('away_name'), str):
        _err("'result.away_name' missing")
    for end in ('top', 'bottom'):
        g = p.get('goals', {}).get(end)
        if not (isinstance(g, list) and len(g) == 2
                and all(isinstance(x, (int, float)) for x in g)):
            _err("'goals.%s' must be a px [x, y] pair (geom contract)" % end)
    total = 0
    for end in ('top', 'bottom'):
        own = p.get('ends', {}).get(end, {}).get('own')
        if not isinstance(own, list):
            _err("'ends.%s.own' missing" % end)
        for ch in own:
            pts = ch.get('pts')
            if not (isinstance(pts, list) and len(pts) >= 2
                    and all(isinstance(q, list) and len(q) == 2 for q in pts)):
                _err('a chain in ends.%s has no >=2-point px path' % end)
            for k in ('w2', 's2', 'mS'):
                if not isinstance(ch.get(k), (int, float)):
                    _err('a chain in ends.%s lacks numeric %s' % (end, k))
        total += len(own)
    if total == 0:
        _err('payload has no chains at all (both ends empty)')
    return True
