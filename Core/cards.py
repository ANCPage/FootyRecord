"""Canonical card payloads — the ONE place card content is assembled.

ONE-SYSTEM rule (2026-09-05): a card's numbers are either the SHIPPED
decision (the stored predictions row — winner/margin/projected/delta, E1
rule) or compute_matchup for unrecorded games. Chains come from
Core.chains. Nothing here invents arithmetic; `liquid/` only renders.

Payload is data-space: chain `seq` = collapsed zone lists in each team's own
attacking frame. liquid/geom maps zones to pixels.
"""
import json

import Core.chains as chains
import Core.state_store as state_store
from Core.mappings import get_full_name, worn_colours

# Card payload contract version (modularization audit 2026-09-05): the JSON
# between Core.cards and the liquid engine is versioned so drift (like the
# px-vs-data-space goals bug) is caught by the schema validator, never by
# eyeballing frames.
CARD_PAYLOAD_VERSION = 1


def _edge_tuple(k):
    return tuple(k.split('->'))


def _tup(e):
    return (e.source, e.target) if hasattr(e, 'source') else tuple(e)


def parse_delta(delta_json):
    """Stored delta JSON -> {(source, target): value} (row-home frame)."""
    if not delta_json:
        return {}
    return {_edge_tuple(k): v for k, v in json.loads(delta_json).items()}


def mirror_delta(delta):
    """The same net in the opposite team's frame (one source, two views).

    A-frame edge (u,v): x  =>  B-frame edge (rot u, rot v): -x
    terminal (u,'SCORE'): x => (rot u, 'SCORE'): -x
    """
    from Core.geometry import rotate_node
    out = {}
    for (u, v), x in delta.items():
        ru = rotate_node(u)
        if v == 'SCORE':
            out[(ru, 'SCORE')] = -x
        else:
            out[(ru, rotate_node(v))] = -x
    return out


def _stored_or_computed(ing, conn, season, round_slot, home, away, up_to,
                        elo_overrides):
    """Shipped row first (E1); compute_matchup only for unrecorded fixtures."""
    row = state_store.prediction_row(conn, season, round_slot, home, away)
    if row:
        h, a, hs, aw, margin, correct, winner, delta_json = row
        return {'winner': get_full_name(winner),
                'margin': round(abs(margin)),
                'proj_home': hs, 'proj_away': aw,
                'correct': correct,
                'delta': parse_delta(delta_json),
                'stored': True}
    if ing is None:
        raise ValueError('no stored prediction for that fixture and no ingestor')
    from Core.prediction import compute_matchup
    p = compute_matchup(ing, home, away, season, up_to + 1,
                        elo_overrides=elo_overrides)
    if p is None:
        raise ValueError('compute_matchup returned None')
    return {'winner': get_full_name(p.winner_id), 'margin': round(abs(p.margin_pred)),
            'proj_home': p.home_score, 'proj_away': p.away_score,
            'correct': None, 'delta': None, 'stored': False}


def _weight_end(sel, delta, mx):
    out = []
    for path, _w in sel:
        n = chains.chain_net(path, delta) / mx if mx else 0.0
        out.append({'seq': list(path), 'w': 1.0,
                    'w2': round(max(0.06, n), 4),
                    's2': round(max(0.15, n), 3),
                    'mS': round(n, 4), 'kind': 'own'})
    return out


def _colour_hex(c):
    return '#FFFFFF' if c == 'WHITE' else c


def _teams(a, b, home):
    hw, aw = worn_colours(home, b if a == home else a)
    top_col = hw if a == home else aw
    bot_col = aw if a == home else hw
    return {'top': {'name': get_full_name(a), 'colour': _colour_hex(top_col)},
            'bottom': {'name': get_full_name(b), 'colour': _colour_hex(bot_col)}}


def pred_payload(ing, conn, a, b, home, season, up_to, label=None,
                 elo_overrides=None):
    """Model projection card. A attacks the top goal; fixture home = `home`.

    Stored fixtures (round slot = up_to+1) show the exact shipped decision
    and weight chains from the STORED delta. Unplayed fixtures compute via
    compute_matchup (finals, futures) with post-window elos.
    """
    away = b if a == home else a
    slot = up_to + 1
    dec = _stored_or_computed(ing, conn, season, slot, home, away, up_to,
                              elo_overrides)
    sa = chains.top80(chains.window_counter(conn, season, up_to, a))
    sb = chains.top80(chains.window_counter(conn, season, up_to, b))
    if dec['stored']:
        d_home = dec['delta']
        if a == home:
            delta_top, delta_bot = d_home, mirror_delta(d_home)
        else:
            delta_bot, delta_top = d_home, mirror_delta(d_home)
    else:
        from Core.prediction import compute_matchup
        pa = compute_matchup(ing, a, b, season, slot, elo_overrides=elo_overrides)
        pb = compute_matchup(ing, b, a, season, slot, elo_overrides=elo_overrides)
        delta_top = {_tup(e): v for e, v in pa.delta.items()}
        delta_bot = {_tup(e): v for e, v in pb.delta.items()}
    mx = 1e-6
    for pth in sa:
        mx = max(mx, chains.chain_net(pth[0], delta_top))
    for pth in sb:
        mx = max(mx, chains.chain_net(pth[0], delta_bot))
    top = _weight_end(sa, delta_top, mx)
    bot = _weight_end(sb, delta_bot, mx)
    score_a = dec['proj_home'] if a == home else dec['proj_away']
    score_b = dec['proj_away'] if a == home else dec['proj_home']
    payload = {
        'version': CARD_PAYLOAD_VERSION,
        'mode': 'pred',
        'round_label': (label or f'ROUND {slot}') + ' \u00b7 PREDICTION',
        'teams': _teams(a, b, home),
        'verdict': {'winner': dec['winner'], 'margin': dec['margin'],
                    'projected': [score_a, score_b]},
        'result': {'home_name': get_full_name(home), 'away_name': get_full_name(away),
                   'home_score': None, 'away_score': None,
                   'model_winner_name': dec['winner'],
                   'pred_margin': dec['margin'], 'correct': dec['correct']},
        'ends': {'top': {'own': top}, 'bottom': {'own': bot}},
    }
    return payload, {'top': len(top), 'bottom': len(bot)}


def recap_payload(conn, season, round_num, a, b, home, label=None):
    """The ONE game's real scoring chains + the model's shipped call.

    Verdict = the model margin (accepted recap grammar); chains uniform
    (SOFT layering in the template). result carries the ACTUAL scores from
    `matches` and whether the model was right.
    """
    away = b if a == home else a
    gc, _h = chains.game_chains(conn, season, round_num, a, b)
    uniform = [{'seq': zs, 'w': 1.0, 'w2': 1.0, 's2': 1.0, 'mS': 1.0,
                'kind': 'own'} for zs in gc.get(a, [])]
    bottom = [{'seq': zs, 'w': 1.0, 'w2': 1.0, 's2': 1.0, 'mS': 1.0,
               'kind': 'own'} for zs in gc.get(b, [])]
    mrow = state_store.match_row(conn, season, round_num, home, away)
    prow = state_store.prediction_row(conn, season, round_num, home, away)
    actual_home = mrow[3] if mrow else None
    actual_away = mrow[4] if mrow else None
    if prow:
        w_id, margin, correct = prow[6], round(abs(prow[4])), prow[5]
    else:
        w_id = home if (actual_home or 0) >= (actual_away or 0) else away
        margin = abs((actual_home or 0) - (actual_away or 0))
        correct = None
    payload = {
        'version': CARD_PAYLOAD_VERSION,
        'mode': 'recap',
        'round_label': (label or f'ROUND {round_num}') + ' \u00b7 RECAP',
        'teams': _teams(a, b, home),
        'verdict': {'winner': get_full_name(w_id), 'margin': margin},
        'result': {'home_name': get_full_name(home), 'away_name': get_full_name(away),
                   'home_score': actual_home, 'away_score': actual_away,
                   'model_winner_name': get_full_name(w_id),
                   'pred_margin': margin, 'correct': correct},
        'ends': {'top': {'own': uniform}, 'bottom': {'own': bottom}},
    }
    return payload, {'top': len(uniform), 'bottom': len(bottom)}


def net_payload(conn, season, round_num, a, b, home, label=None):
    """The ACTUAL net of a played game: game chains, per-edge net traffic.

    Verdict = the ACTUAL winner + margin (net cards read `matches`).
    """
    from collections import Counter
    from Core.geometry import rotate_node
    away = b if a == home else a
    gc, _h = chains.game_chains(conn, season, round_num, a, b)
    ca, cb = gc.get(a, []), gc.get(b, [])

    def edges_of(chains_list):
        c = Counter()
        for zs in chains_list:
            for i in range(len(zs) - 1):
                c[(zs[i], zs[i + 1])] += 1
            c[(zs[-1], 'SCORE')] += 1
        return c

    def flip_edge(e):
        u, v = e
        return (rotate_node(u), 'SCORE') if v == 'SCORE' \
            else (rotate_node(u), rotate_node(v))

    ea, eb = edges_of(ca), edges_of(cb)
    net_top = {e: v - eb.get(flip_edge(e), 0) for e, v in ea.items()}
    net_bot = {e: v - ea.get(flip_edge(e), 0) for e, v in eb.items()}
    mx = max([max(0, v) for v in net_top.values()]
             + [max(0, v) for v in net_bot.values()] + [1])

    def build(zs_list, netmap):
        out = []
        for zs in zs_list:
            n = chains.chain_net(zs, netmap) / mx
            out.append({'seq': zs, 'w': 1.0,
                        'w2': round(max(0.06, n), 4),
                        's2': round(max(0.15, n), 3),
                        'mS': round(n, 4),
                        'kind': 'own'})
        return out

    top, bot = build(ca, net_top), build(cb, net_bot)
    mrow = state_store.match_row(conn, season, round_num, home, away)
    if not mrow:
        raise ValueError('net card needs a played game')
    actual_home, actual_away = mrow[3], mrow[4]
    w_id = home if actual_home >= actual_away else away
    prow = state_store.prediction_row(conn, season, round_num, home, away)
    model_winner = get_full_name(prow[6]) if prow else None
    pred_margin = round(abs(prow[4])) if prow else None
    payload = {
        'version': CARD_PAYLOAD_VERSION,
        'mode': 'net',
        'round_label': (label or f'ROUND {round_num}') + ' \u00b7 THE ACTUAL NET',
        'teams': _teams(a, b, home),
        'verdict': {'winner': get_full_name(w_id),
                    'margin': abs(actual_home - actual_away)},
        'result': {'home_name': get_full_name(home), 'away_name': get_full_name(away),
                   'home_score': actual_home, 'away_score': actual_away,
                   'model_winner_name': model_winner,
                   'pred_margin': pred_margin, 'correct': prow[5] if prow else None},
        'ends': {'top': {'own': top}, 'bottom': {'own': bot}},
    }
    return payload, {'top': len(top), 'bottom': len(bot)}
