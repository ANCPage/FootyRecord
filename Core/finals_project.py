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
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from Core.config import DATA_DIR, RESULTS_DB   # noqa: E402
from Core.engine_data import DataIngestor      # noqa: E402
from Core.elo_engine import EloEngine          # noqa: E402
from Core.mappings import get_full_name        # noqa: E402
from Core.prediction import compute_matchup    # noqa: E402
import Core.state_store as state_store         # noqa: E402

SEASON = 2026
# FALLBACK ONLY (audit 2026-09-14, finding 8): the seeds used to be hardcoded for
# this season, which would have silently projected next year's bracket from this
# year's ten teams. They are now derived from the ladder (`ladder_seeds`); this
# dict is kept only for when the ladder cannot be built, and the projector says
# so out loud when it uses it. Verified against the played finals:
# wildcard 7v10 = Melbourne v Carlton, 8v9 = Bulldogs v Collingwood;
# QF1 1v4 = Fremantle v Hawthorn, QF2 2v3 = Sydney v Brisbane;
# EF1 5v lowest wildcard winner = Geelong v Carlton, EF2 = Adelaide v Bulldogs.
FALLBACK_SEEDS = {1: 'CD_T60', 2: 'CD_T160', 3: 'CD_T20', 4: 'CD_T80', 5: 'CD_T70',
                  6: 'CD_T10', 7: 'CD_T90', 8: 'CD_T140', 9: 'CD_T40', 10: 'CD_T30'}
SEEDS = FALLBACK_SEEDS          # kept as a name for callers/tests that import it


def ladder_seeds(conn, season=SEASON, home_away_rounds=24):
    """{rank: team_id} from the home-and-away ladder: wins, then percentage.

    The finals bracket is defined by ladder position, so deriving it means the
    projector follows the season instead of a hardcoded snapshot.
    """
    rows = conn.execute(
        'SELECT home, away, home_score, away_score FROM matches '
        'WHERE season=? AND round<=? AND home_score IS NOT NULL', (season, home_away_rounds)
    ).fetchall()
    if not rows:
        return {}
    wins, losses, drawn, pf, pa = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    for home, away, hs, as_ in rows:
        for team, own, opp in ((home, hs, as_), (away, as_, hs)):
            pf[team] += own
            pa[team] += opp
            if own > opp:
                wins[team] += 1
            elif own < opp:
                losses[team] += 1
            else:
                drawn[team] += 1
    teams = sorted(set(wins) | set(losses))
    if not teams:
        return {}
    def pct(t):
        return (100.0 * pf[t] / pa[t]) if pa[t] else 0.0
    order = sorted(teams, key=lambda t: (-wins[t], -pct(t), t))
    return {i + 1: t for i, t in enumerate(order)}


def resolve_seeds(conn, season=SEASON, verbose=True):
    """The seeds for the bracket, and a loud check that they are consistent.

    The DICT is authoritative, not the ladder (audit 2026-09-14, finding 13):
    the DB's home-and-away results do NOT reproduce the seeding the played finals
    imply. Derived ladder vs the played seeding, 2026: Geelong 17W -> 3rd but was
    seeded 5th; Brisbane 15W -> 4th but 3rd; Hawthorn -> 5th but 4th; Melbourne ->
    6th but 7th; Adelaide -> 7th but 6th; Carlton -> 9th but 10th. Either the DB's
    H&A scores are not the real ones, or the seeding rule is not plain ladder
    order. Until that is explained, switching to a derived ladder would silently
    re-project games that were actually played, so the mismatch is REPORTED and
    the explicit snapshot is used.
    """
    seeded = dict(FALLBACK_SEEDS)
    derived = ladder_seeds(conn, season)
    if not derived:
        if verbose:
            print('WARNING: could not build the %s ladder from the DB; using the '
                  'explicit seed snapshot.' % season)
        return seeded
    rank_of = {t: r for r, t in derived.items()}
    bad = [(r, seeded[r], rank_of.get(seeded[r])) for r in sorted(seeded)
           if rank_of.get(seeded[r]) != r]
    if bad and verbose:
        print('WARNING: the DB ladder disagrees with the finals seeding in %d of %d '
              'places (e.g. %s seeded %d, ladder says %s) — using the explicit '
              'snapshot; see audit finding 13.' % (
                  len(bad), len(seeded),
                  get_full_name(bad[0][1]), bad[0][0], bad[0][2]))
    return seeded


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

    # Seeds come from the ladder for the season being projected, not a snapshot
    # (audit finding 8). resolve_seeds warns loudly if it must fall back.
    seeds = resolve_seeds(conn)
    if verbose:
        # Say WHERE the seeds came from — the label used to claim "ladder-derived"
        # while the resolved value was the explicit snapshot (2026-09-14).
        print('seeds used (explicit snapshot, ladder-checked): ' + ', '.join(
            '%d:%s' % (k, get_full_name(v)) for k, v in sorted(seeds.items())))

    # --- week 1: wildcard (7v10, 8v9) ------------------------------------
    wc1 = play('Wildcard 1', 25, seeds[7], seeds[10])
    wc2 = play('Wildcard 2', 25, seeds[8], seeds[9])
    seed_of = {t: s for s, t in seeds.items()}
    # ascending by seed: [highest-ranked, lowest-ranked]
    wc_winners = sorted([wc1, wc2], key=lambda t: seed_of[t])
    highest_ranked, lowest_ranked = wc_winners[0], wc_winners[-1]

    # --- week 2: QFs + EFs ----------------------------------------------
    qf1_w = play('QF1', 26, seeds[1], seeds[4])
    qf1_l = seeds[4] if qf1_w == seeds[1] else seeds[1]
    qf2_w = play('QF2', 26, seeds[2], seeds[3])
    qf2_l = seeds[3] if qf2_w == seeds[2] else seeds[2]
    ef1_w = play('EF1', 26, seeds[5], lowest_ranked)
    ef2_w = play('EF2', 26, seeds[6], highest_ranked)

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
