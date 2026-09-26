"""How much does the scoreboard error move the model's report card?

The DB's 2026 winners are wrong in 8 games and its margins are light almost
everywhere. This re-grades the stored 2026 predictions twice - once against the
DB's results (what we have been quoting) and once against the official results -
so the "so what" has a number attached.
"""
import sys
import os
from collections import defaultdict

sys.path.insert(0, '/home/austin/footyrecord-local')

import requests  # noqa: E402
import Core.chains as chains  # noqa: E402
from Core.mappings import get_full_name  # noqa: E402

def _word(name):
    return (name or '').split()[0].lower() if name else ''

r = requests.get('https://api.squiggle.com.au/', params={'q': 'games', 'year': 2026},
                 headers={'User-Agent': 'footyrecord-audit/1.0'}, timeout=30)
games = (r.json() or {}).get('games') or []
official = {}
for g in games:
    official[(int(g['round']), _word(g['hteam']), _word(g['ateam']))] = g

conn = chains.connect()
preds = conn.execute(
    'SELECT season, round, home, away, margin FROM predictions WHERE season=2026 '
    'ORDER BY round').fetchall()
db = {r[0]: r for r in conn.execute(
    'SELECT m_id, round, home, away, home_score, away_score FROM matches '
    'WHERE season=2026').fetchall()}

by_round = defaultdict(list)
for m_id, rnd, home, away, hs, as_ in db.values():
    by_round[rnd].append((m_id, home, away, hs, as_))

def grade(use_official):
    ok = wrong = skipped = 0
    margin_err = []
    per_game = {}
    for _s, rnd, home, away, margin in preds:
        if rnd is None or rnd < 1 or rnd > 24:
            continue
        m = next((x for x in by_round.get(rnd, []) if {x[1], x[2]} == {home, away}), None)
        if not m:
            continue
        m_id, h, a, hs, as_ = m
        if use_official:
            g = official.get((rnd, _word(get_full_name(h)), _word(get_full_name(a))))
            if not g:
                skipped += 1
                continue
            hs, as_ = int(g['hscore']), int(g['ascore'])
        if hs is None or as_ is None:
            skipped += 1
            continue
        actual_winner = h if hs > as_ else (a if as_ > hs else 'DRAW')
        # stored margin is HOME-relative (documented): >0 means the home side won
        model_winner = h if (margin or 0) > 0 else (a if (margin or 0) < 0 else 'DRAW')
        if actual_winner == 'DRAW':
            skipped += 1
            continue
        per_game[(rnd, h, a)] = (model_winner == actual_winner)
        if model_winner == actual_winner:
            ok += 1
        else:
            wrong += 1
        margin_err.append(abs(abs(margin or 0) - abs(hs - as_)))
    total = ok + wrong
    return {'n': total, 'correct': ok,
            'acc': 100.0 * ok / total if total else float('nan'),
            'margin_mae': sum(margin_err) / len(margin_err) if margin_err else float('nan'),
            'skipped': skipped, 'per_game': per_game}


a = grade(False)
b = grade(True)
print('2026 home-and-away, %d predictions graded' % a['n'])
print('%-34s %-6s %-10s %s' % ('graded against', 'games', 'tipping', 'margin MAE (pts)'))
print('%-34s %-6d %-10.1f %.1f' % ("the DB's stored results (quoted so far)",
                                   a['n'], a['acc'], a['margin_mae']))
print('%-34s %-6d %-10.1f %.1f' % ('the OFFICIAL results', b['n'], b['acc'], b['margin_mae']))
print()
# like-for-like: only the games both gradings cover
shared = sorted(set(a['per_game']) & set(b['per_game']))
ok_db = sum(1 for k in shared if a['per_game'][k])
ok_off = sum(1 for k in shared if b['per_game'][k])
print('LIKE-FOR-LIKE on the %d games covered by both gradings:' % len(shared))
print('  against the DB results     : %.1f%% (%d/%d)' % (
    100.0 * ok_db / len(shared), ok_db, len(shared)))
print('  against the OFFICIAL results: %.1f%% (%d/%d)' % (
    100.0 * ok_off / len(shared), ok_off, len(shared)))
print('  change: %+.1f points' % (100.0 * (ok_off - ok_db) / len(shared)))
flips = [k for k in shared if a['per_game'][k] != b['per_game'][k]]
print('  games where the VERDICT on the model changes: %d' % len(flips))
for k in flips:
    print('     R%-3s %s v %s: DB says %s, official says %s' % (
        k[0], get_full_name(k[1]), get_full_name(k[2]),
        'model right' if a['per_game'][k] else 'model wrong',
        'model right' if b['per_game'][k] else 'model wrong'))
