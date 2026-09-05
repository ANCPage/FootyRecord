"""ONE-SYSTEM tests: liquid card payloads derive from the same store/decisions
as the record — never a second set of calculations.

Covered:
- recap/net payloads reproduce the stored/matches truth for a played game
- pred payload verdict == the SHIPPED predictions row (E1) incl. projected
- chain weighting uses the STORED delta when one exists
- colours follow the worn_colours policy
- canonical chain extraction is stable (golden counts guard regressions)
"""
import json

import Core.cards as cards
import Core.chains as chains
import Core.state_store as state_store
from Core.mappings import worn_colours


def _conn():
    return chains.connect()


# R24 2026: Sydney (home, CD_T160) 120-65 North Melbourne (CD_T100).
# Stored projection: Sydney by 23 (94-70). Gold recap grammar: BY = model margin.
def test_recap_r24_verdict_is_the_stored_model_call():
    conn = _conn()
    p, stats = cards.recap_payload(conn, 2026, 24, 'CD_T100', 'CD_T160',
                                   'CD_T160', label='ROUND 24')
    assert p['verdict']['winner'] == 'Sydney Swans'
    assert p['verdict']['margin'] == 23            # model margin, not 55
    assert p['result']['home_score'] == 120        # actuals from matches
    assert p['result']['away_score'] == 65
    assert p['result']['correct'] == 1


def test_net_r24_verdict_is_the_actual_result():
    conn = _conn()
    p, _ = cards.net_payload(conn, 2026, 24, 'CD_T100', 'CD_T160',
                             'CD_T160', label='ROUND 24')
    assert p['verdict']['winner'] == 'Sydney Swans'
    assert p['verdict']['margin'] == 55            # actual margin for the net card
    assert p['result']['home_score'] == 120


def test_pred_r24_matches_the_shipped_row_exactly():
    conn = _conn()
    p, _ = cards.pred_payload(None, conn, 'CD_T100', 'CD_T160', 'CD_T160',
                              2026, 23, label='ROUND 24')
    assert p['verdict']['winner'] == 'Sydney Swans'
    assert p['verdict']['margin'] == 23            # stored 23.1 -> 23
    assert p['verdict']['projected'] == [70, 94]   # stored projection, A-first


def test_pred_r12_stored_decision():
    # R12 2026: Carlton home; stored = Geelong by 24 (Carlton 70-94 proj).
    conn = _conn()
    p, _ = cards.pred_payload(None, conn, 'CD_T30', 'CD_T70', 'CD_T30',
                              2026, 11, label='ROUND 12')
    assert p['verdict']['winner'] == 'Geelong Cats'
    assert p['verdict']['margin'] == 24
    assert p['verdict']['projected'] == [70, 94]


def test_pred_weights_come_from_the_stored_delta():
    conn = _conn()
    p, _ = cards.pred_payload(None, conn, 'CD_T100', 'CD_T160', 'CD_T160',
                              2026, 23, label='ROUND 24')
    row = state_store.prediction_row(conn, 2026, 24, 'CD_T160', 'CD_T100')
    stored_delta = cards.parse_delta(row[7])
    assert stored_delta, 'stored delta should exist'
    # the model picks Sydney; Sydney's end must outweigh North's on the card
    wt = sum(c['mS'] for c in p['ends']['top']['own'])
    wb = sum(c['mS'] for c in p['ends']['bottom']['own'])
    assert wb > wt, 'bottom (Sydney) must outweigh top (North)'


def test_canonical_recap_chain_counts_golden():
    # canonical = collapsed; regression guard on the extraction path
    conn = _conn()
    gc, home = chains.game_chains(conn, 2026, 24, 'CD_T100', 'CD_T160')
    assert home == 'CD_T160'
    assert len(gc['CD_T100']) == 17
    assert len(gc['CD_T160']) == 31


def test_colour_policy():
    assert worn_colours('CD_T70', 'CD_T30') == ('#1C3C63', 'WHITE')   # Geelong home
    assert worn_colours('CD_T10', 'CD_T140') == ('#002B5C', '#C70136')  # Adelaide home
    assert worn_colours('CD_T160', 'CD_T20') == ('#ED171F', '#730040')  # no clash flip


def test_mirror_delta_flips_sign_and_rotates():
    d = {('C2', 'D2'): 0.5, ('E2', 'SCORE'): -0.2}
    m = cards.mirror_delta(d)
    from Core.geometry import rotate_node
    assert m[(rotate_node('C2'), rotate_node('D2'))] == -0.5
    assert m[(rotate_node('E2'), 'SCORE')] == 0.2
