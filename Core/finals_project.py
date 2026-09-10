"""Finals projector — walk the AFL final-ten bracket to the grand final.

2026-09-07 (Austin): project the remaining finals using REAL results where
they exist and the model's own projections elsewhere, carrying Elo forward
after each projected result with the engine's own update rule.

Format (AFL final ten, first used 2026):
  W1 wildcard : 7v10, 8v9 (sudden death; top six have the bye)
  W2          : QF1 (1v4), QF2 (2v3), EF1 (5v lowest-ranked wildcard winner),
                EF2 (6v highest-ranked wildcard winner)
  W3 semis    : SF1 = QF1 loser hosts EF1 winner; SF2 = QF2 loser hosts EF2 winner
  W4 prelims  : PF1 = QF1 winner hosts SF2 winner; PF2 = QF2 winner hosts SF1 winner
  W5          : GF = PF winners (neutral — the model has no venue term, b0=0)

Round slots in the source data: 25 wildcard, 26 week 2, 27 SF, 28 PF, 29 GF.
Real results are read from `matches`; anything missing is projected.
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Core.config import DATA_DIR, RESULTS_DB   # noqa: E402
from Core.engine_data import DataIngestor      # noqa: E402
from Core.elo_engine import EloEngine          # noqa: E402
from Core.mappings import get_full_name        # noqa: E402
from Core.prediction import compute_matchup    # noqa: E402
import Core.state_store as state_store         # noqa: E402

SEASON = 2026
# Seeds verified against the played finals (the games define the seeds:
# wildcard 7v10 = Melbourne v Carlton, 8v9 = Bulldogs v Collingwood;
# QF1 1v4 = Fremantle v Hawthorn, QF2 2v3 = Sydney v Brisbane;
# EF1 5v lowest wildcard winner = Geelong v Carlton, EF2 = Adelaide v Bulldogs).
SEEDS = {1: 'CD_T60', 2: 'CD_T160', 3: 'CD_T20', 4: 'CD_T80', 5: 'CD_T70',
         6: 'CD_T10', 7: 'CD_T90', 8: 'CD_T140', 9: 'CD_T40', 10: 'CD_T30'}


def real_result(conn, round_num, team_a, team_b):
    """(winner_id, margin, home, away) for a played finals game, else None."""
    row = state_store.match_row(conn, SEASON, round_num, team_a, team_b)
    if not row:
        return None
    _m_id, home, away, hs, as_ = row
    if hs is None or as_ is None:
        return None
    return (home if hs > as_ else away, abs(hs - as_), home, away, hs, as_)


def project(verbose=True):
    conn = state_store.connect(RESULTS_DB)
    ing = DataIngestor(DATA_DIR)
    ing.load_all_data(light=True)

    elos = {}          # carried ratings for projected games
    games = []         # (label, round, home, away, result dict)

    def play(label, round_num, home, away):
        """Real result if played, else the model's projection (+ Elo carry)."""
        real = real_result(conn, round_num, home, away)
        if real:
            winner, margin, rh, ra, hs, as_ = real
            h, a = rh, ra
            games.append({'label': label, 'round': round_num, 'home': h,
                          'away': a, 'winner': winner, 'margin': margin,
                          'projected': False, 'h_score': hs, 'a_score': as_})
            if verbose:
                print('%-14s %s %d v %s %d  -> %s by %d  [ACTUAL]' % (
                    label, get_full_name(h), hs, get_full_name(a), as_,
                    get_full_name(winner), margin))
            return winner
        h_elo = elos.get(home) or ing.get_team_elo(home, SEASON, round_num) or 1500.0
        a_elo = elos.get(away) or ing.get_team_elo(away, SEASON, round_num) or 1500.0
        p = compute_matchup(ing, home, away, SEASON, round_num,
                            elo_overrides={home: h_elo, away: a_elo})
        if p is None:
            raise SystemExit('no profile for %s v %s' % (home, away))
        margin = abs(p.margin_pred)
        winner = p.winner_id
        # carry Elo forward exactly as the engine does after a real result
        signed = p.margin_pred if winner == home else -abs(p.margin_pred)
        dh, da, _ = EloEngine.elo_update(
            h_elo, a_elo, signed,
            divisor=getattr(ing.calibration, 'margin_divisor', None))
        elos[home] = h_elo + dh
        elos[away] = a_elo + da
        games.append({'label': label, 'round': round_num, 'home': home,
                      'away': away, 'winner': winner, 'margin': margin,
                      'projected': True, 'h_score': p.home_score,
                      'a_score': p.away_score, 'grade_margin': p.margin_pred})
        if verbose:
            print('%-14s %s %d v %s %d  -> %s by %d  [MODEL %.0f-%.0f]' % (
                label, get_full_name(home), p.home_score, get_full_name(away),
                p.away_score, get_full_name(winner), round(margin),
                p.home_score, p.away_score))
        return winner

    # --- week 1: wildcard (7v10, 8v9) ------------------------------------
    wc1 = play('Wildcard 1', 25, SEEDS[7], SEEDS[10])
    wc2 = play('Wildcard 2', 25, SEEDS[8], SEEDS[9])
    seed_of = {t: s for s, t in SEEDS.items()}
    # ascending by seed: [highest-ranked, lowest-ranked]
    wc_winners = sorted([wc1, wc2], key=lambda t: seed_of[t])
    highest_ranked, lowest_ranked = wc_winners[0], wc_winners[-1]

    # --- week 2: QFs + EFs ----------------------------------------------
    qf1_w = play('QF1', 26, SEEDS[1], SEEDS[4])
    qf1_l = SEEDS[4] if qf1_w == SEEDS[1] else SEEDS[1]
    qf2_w = play('QF2', 26, SEEDS[2], SEEDS[3])
    qf2_l = SEEDS[3] if qf2_w == SEEDS[2] else SEEDS[2]
    ef1_w = play('EF1', 26, SEEDS[5], lowest_ranked)
    ef2_w = play('EF2', 26, SEEDS[6], highest_ranked)

    # --- week 3: semis ---------------------------------------------------
    # SF1 = QF1 loser hosts EF1 winner; SF2 = QF2 loser hosts EF2 winner
    sf1_w = play('SF1', 27, qf1_l, ef1_w)
    sf2_w = play('SF2', 27, qf2_l, ef2_w)

    # --- week 4: prelims -------------------------------------------------
    pf1_w = play('PF1', 28, qf1_w, sf2_w)
    pf2_w = play('PF2', 28, qf2_w, sf1_w)

    # --- week 5: grand final (neutral; model has no venue term) ----------
    gf_w = play('GRAND FINAL', 29, pf1_w, pf2_w)

    print()
    print('PREDICTED PREMIER: %s' % get_full_name(gf_w))
    return games


if __name__ == '__main__':
    project()
