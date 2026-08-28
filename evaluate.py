"""Walk-forward evaluation harness (audit E6; dynamic calibration 2026-08-10).

Measures the model with DYNAMIC calibration: at every round, the decision
coefficients are re-fitted on matches strictly before that round (no leakage),
so every match is out-of-sample by construction. Two fit windows are A/B'd:
rolling last 2 seasons vs expanding (all history). Reports per-season and
overall winner accuracy, margin MAE/RMSE, and a margin-band calibration table
(Brier was removed 2026-08-10 — the margin is the single calibrated output).

Run:  python evaluate.py [season ...]
"""
import json
import math
import sys

from Core.calibration import align_margin, fit_or_fallback, select_window
from Core.engine_data import DataIngestor


def collect_rows(ing, seasons, decay=None, window=None):
    """(season, round, net_delta, elo_diff_raw, home_won, actual_margin,
    total, actual_delta, match_id, home, away) — REUSES ingestor._build_fit_rows()
    (reuse pass #6): expected net deltas, Elo diffs and actuals are already
    stored in match_performance + Elo history. No per-match re-computation.

    `decay`/`window` (refit tool): recompute expected net deltas at the given
    params (Option B — recombination only, no re-profiling needed)."""
    if decay is None and window is None:
        rows = []
        for (s, r, net, elo, marg, tot, act, m_id, home, away) in ing._build_fit_rows():
            if s not in seasons:
                continue
            rows.append((s, r, net, elo, marg > 0.0, marg, tot, act, m_id, home, away))
        return rows

    import Core.config as cfg
    from Core.engine_core import MatchupEngine
    # Calibration travels with the ingestor (no module global — Phase 1).
    # The decay override is temporary and restored in the finally block.
    saved_decay = ing.calibration.decay_factor
    saved_window = cfg.config.window_size
    if decay is not None:
        ing.calibration.decay_factor = decay
    if window is not None:
        cfg.config.window_size = window
    try:
        rows = []
        for m_id, info in ing.match_info.items():
            if info.season not in seasons or m_id.startswith('POST_'):
                continue
            if info.home_score == 0 and info.away_score == 0:
                continue
            # draws included (policy B): margin-0 outcome, miss for the pick
            ma = ing.get_team_average_matrix(info.home, window=window,
                                             up_to_season=info.season,
                                             up_to_round=info.round)
            mb = ing.get_team_average_matrix(info.away, window=window,
                                             up_to_season=info.season,
                                             up_to_round=info.round)
            if not ma or not mb:
                continue
            net = sum(MatchupEngine.calculate_delta(ma, mb).values())
            eh = ing.get_team_elo(info.home, info.season, info.round)
            ea = ing.get_team_elo(info.away, info.season, info.round)
            act = ing.match_performance.get(m_id, {}).get('actual', net)
            rows.append((info.season, info.round, net, eh - ea,
                         info.home_score > info.away_score,
                         info.home_score - info.away_score,
                         info.home_score + info.away_score, act,
                         m_id, info.home, info.away))
        return rows
    finally:
        ing.calibration.decay_factor = saved_decay
        cfg.config.window_size = saved_window


def run_mode(rows, window_seasons, label):
    """Walk forward: fit calibration on prior rows at each round boundary.

    Returns (out, fallback_hits, cals) — out rows are
    (season, round, margin_pred, home_won, margin_pred, actual_margin,
    match_id, home, away, elo_diff, net_delta) — 11-tuple, NET_DELTA AT
    INDEX 10 (re-audit 2026-08-12: docstrings must match the layout);
    cals maps (season, round) -> Calibration.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        groups[(r[0], r[1])].append(r)
    ordered = sorted(groups.items())

    prior = []
    out = []
    cals = {}
    fallback_hits = 0
    for (season, rnd), group in ordered:
        sel = select_window(prior, season, window_seasons)
        cal = fit_or_fallback(sel, label)
        if cal.window == 'fallback':
            fallback_hits += 1
        cals[(season, rnd)] = cal
        for (s, r, net, elo, won, marg, tot, act, m_id, home, away) in group:
            m = align_margin(cal.margin(net, elo / 100.0), net, elo / 100.0)
            out.append((s, r, m, won, m, marg, m_id, home, away, elo, net))
            # FitRow format for the calibration fit: (season, round, net,
            # elo_diff, margin, total, actual_delta, ...) — NOT the collect_rows
            # layout; identity fields are irrelevant to the fit.
            prior.append((s, r, net, elo, marg, tot, act))
    return out, fallback_hits, cals


def aggregate(rows):
    """Accuracy + margin error only (Brier removed 2026-08-10 — the margin is
    the single calibrated output; winner = margin sign)."""
    n = len(rows)
    acc = sum(1 for r in rows if r[3] == (r[2] > 0)) / n
    mae = sum(abs(r[4] - r[5]) for r in rows) / n
    rmse = math.sqrt(sum((r[4] - r[5]) ** 2 for r in rows) / n)
    return n, acc, mae, rmse


def save_rows_to_db(out_rows, cals, ing, db_path=None):
    """Write walk-forward (no-lookahead) predictions to the results DB.

    The single source of truth: renderer and analysis read these rows.
    out_rows: (season, round, margin_pred, home_won, margin_pred,
    actual_margin, match_id, home, away, elo_diff, net_delta) — 11-tuple
    (net_delta at index 10); cals: (season, round) -> Calibration.
    """
    import Core.results_db as results_db
    from Core.calibration import confidence_grade

    conn = results_db.connect() if db_path is None else results_db.connect(db_path)
    # Orphan cleanup: predictions must refer to matches in the current state
    # (a state rebuild can leave stale rows with old/different ids behind).
    conn.execute("DELETE FROM predictions WHERE match_id NOT IN (SELECT m_id FROM matches)")
    rounds = {}
    for r in out_rows:
        rounds.setdefault((r[0], r[1]), []).append(r)
    games, snaps = [], []
    # Elo BEFORE each match, by match id (same source _build_fit_rows uses —
    # guarantees the stored home_elo/away_elo difference equals elo_diff).
    elo_at = {}
    for team, hist in ing.team_elo_history.items():
        for mid, elo_val in hist:
            if not mid.startswith('POST_'):
                elo_at.setdefault(mid, {})[team] = elo_val
    for (s, rnd), group in sorted(rounds.items()):
        cal = cals[(s, rnd)]
        # Ranks from the Elo field BEFORE the round (re-audit 2026-08-12,
        # concern #4: fills the NULL columns the renderer needs).
        rankings = ing.get_league_rankings(s, rnd)
        for r in group:
            m, won, marg, m_id, home, away, elo, net = r[2], r[3], r[5], r[6], r[7], r[8], r[9], r[10]
            # winner = RAW delta sign (no fitted layer overrides the signal);
            # Elo only breaks exact dead-evens — matches home_favored()
            winner = home if (net > 0 or (net == 0 and elo >= 0)) else away
            correct = 1 if won == (winner == home) else 0
            total = cal.total_mean
            h_elo = elo_at.get(m_id, {}).get(home)
            a_elo = elo_at.get(m_id, {}).get(away)
            if h_elo is None or a_elo is None:
                h_elo = a_elo = 0.0  # unreachable — rows came from these histories
            h_tier = ing.calibration.tier(h_elo) if getattr(ing, 'calibration', None) else cal.tier(h_elo)
            a_tier = ing.calibration.tier(a_elo) if getattr(ing, 'calibration', None) else cal.tier(a_elo)
            # The pre-match delta matrix that produced this pick (walk-forward
            # consistent by construction — stored at profile time).
            delta = ing.match_performance.get(m_id, {}).get('expected_delta')
            games.append({
                'season': s, 'round': rnd, 'match_id': m_id, 'home': home,
                'away': away,
                # RAW net delta — NOT back-derived from the aligned margin
                # (the old derivation corrupted 59/1,204 override games;
                # re-audit 2026-08-12, B1).
                'net_delta': net,
                'elo_diff': elo, 'margin': m, 'winner': winner,
                'home_elo': h_elo, 'away_elo': a_elo, 'home_tier': h_tier,
                'away_tier': a_tier, 'home_rank': rankings.get(home, 99),
                'away_rank': rankings.get(away, 99),
                'total': total, 'home_score': round((total + m) / 2),
                'away_score': round((total - m) / 2),
                'grade': confidence_grade(m),
                'actual_margin': marg, 'correct': correct,
                'delta': results_db.serialize_delta(delta),
            })
        snap = results_db.build_calibration_snapshot(cal, 'walk-forward')
        # the PROFILE decay (what the matrices were actually built with), not
        # the fit's config default (provenance fix)
        snap['decay'] = getattr(ing.calibration, 'decay_factor', cal.decay_factor)
        snap['season'], snap['round'] = s, rnd
        snaps.append(snap)
    for g in games:
        results_db.upsert_prediction(conn, g)
    for sn in snaps:
        results_db.upsert_calibration(conn, sn['season'], sn['round'], sn)
    # record_fingerprint: the state fingerprint the record was saved against —
    # render_round warns when they diverge (stale panels guard, 2026-08-11)
    import Core.state_store as state_store
    state_store.meta_set(conn, 'record_fingerprint',
                         state_store.meta_get(conn, 'fingerprint') or '')
    # Keep the persisted tier cutoffs truthful: the load path rebuilds them
    # from the live Elo field (midpoints, 2026-08-26), but evaluate --save
    # never rewrote the calibration row — it stayed at ingest-time values.
    conn.execute("UPDATE calibration SET tier_cutoffs=? WHERE id=1",
                 (json.dumps(list(ing.calibration.tier_cutoffs)),))
    conn.commit()
    conn.close()
    return len(games)


def evaluate(seasons=None, save=False):
    ing = DataIngestor('CSV_DATA')
    ing.load_all_data()
    # Cache load already carries profiles/elo/calibration for the current
    # config (fingerprint-gated) — skip the ~4-min rebuild (reuse pass #6).
    if not ing.team_positions:
        ing.profile_all_teams()

    if seasons is None:
        seasons = sorted({i.season for i in ing.match_info.values()})
    seasons = [int(x) for x in seasons]

    rows = collect_rows(ing, seasons)
    print(f"matches evaluated: {len(rows)}")
    roll2, fb2, cals2 = run_mode(rows, 2, 'roll2')
    expand, fbe, _cals_e = run_mode(rows, None, 'expanding')
    print(f"rounds predicted on fallback (too little history): roll2={fb2}, expanding={fbe}")

    print("=" * 78)
    print(" WALK-FORWARD EVALUATION (dynamic calibration — refit before every round)")
    print("=" * 78)
    print(f"{'Season':<8}{'n':>5}{'roll2%':>8}{'exp%':>7}{'r2MAE':>8}{'eMAE':>8}{'r2RMSE':>8}{'eRMSE':>8}")
    print("-" * 78)
    for year in sorted({r[0] for r in rows}):
        a = [r for r in roll2 if r[0] == year]
        b = [r for r in expand if r[0] == year]
        na, acca, maea, rmsa = aggregate(a)
        nb, accb, maeb, rmsb = aggregate(b)
        print(f"{year:<8}{na:>5}{100*acca:>7.1f}{100*accb:>7.1f}{maea:>8.1f}{maeb:>8.1f}{rmsa:>8.1f}{rmsb:>8.1f}")

    n, acc, mae, rmse = aggregate(roll2)
    n2, acc2, mae2, rmse2 = aggregate(expand)
    print("-" * 78)
    print(f"{'ALL':<8}{n:>5}{100*acc:>7.1f}{100*acc2:>7.1f}{mae:>8.1f}{mae2:>8.1f}{rmse:>8.1f}{rmse2:>8.1f}")
    print(f"\n  rolling-2 : acc {100*acc:.1f}%  MAE {mae:.1f}  RMSE {rmse:.1f}")
    print(f"  expanding: acc {100*acc2:.1f}%  MAE {mae2:.1f}  RMSE {rmse2:.1f}")

    print()
    print(" Margin accuracy (pooled, by predicted-margin bands) — rolling-2:")
    print(f"{'band (pts)':<14}{'n':>6}{'actual win rate':>16}")
    for lo, hi in [(-100, -12), (-12, -4), (-4, 4), (4, 12), (12, 100)]:
        m = [r for r in roll2 if lo <= r[2] < hi]
        if m:
            print(f"  {lo:>4}-{hi:>4}      {len(m):>5}{sum(1 for r in m if r[3])/len(m):>16.3f}")

    # Transparency: the fit at the final round (what production would ship)
    c = ing.calibration   # Phase 1: was the module global
    print(f"\n active calibration (cache, latest fit): margin b1={c.margin_b1:.2f} b2={c.margin_b2:.2f} | "
          f"total {c.total_mean:.1f} | decay {c.decay_factor} | n={c.n_matches} [{c.window}]")

    if save:
        written = save_rows_to_db(roll2, cals2, ing)
        print(f"\n walk-forward predictions saved to results DB: {written} games "
              f"(single source of truth — renderer/analysis read these rows)")


if __name__ == '__main__':
    args = sys.argv[1:] or []
    save = '--save' in args
    seasons = [a for a in args if a != '--save'] or None
    evaluate(seasons, save=save)
