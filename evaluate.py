"""Walk-forward evaluation harness (audit E6; dynamic calibration 2026-08-10).

Measures the model with DYNAMIC calibration: at every round, the decision
coefficients are re-fitted on matches strictly before that round (no leakage),
so every match is out-of-sample by construction. Two fit windows are A/B'd:
rolling last 2 seasons vs expanding (all history). Reports per-season and
overall winner accuracy, Brier, margin MAE/RMSE, and a calibration table.

Run:  python evaluate.py [season ...]
"""
import math
import sys

from calibration import fit_or_fallback, select_window
from engine_data import DataIngestor

import bootstrap  # noqa: F401  (side-effect: puts Core/ on sys.path)


def collect_rows(ing, seasons, decay=None, window=None):
    """(season, round, net_delta, elo_diff_raw, home_won, actual_margin,
    actual_delta) — REUSES ingestor._build_fit_rows() (reuse pass #6): the
    expected net deltas, Elo diffs and actuals are already stored in
    match_performance + Elo history, computed once at profile time. No
    per-match re-computation (was the slow ~4-min part of every eval).

    `decay`/`window` (refit tool): recompute expected net deltas at the given
    params (Option B — recombination only, no re-profiling needed)."""
    if decay is None and window is None:
        rows = []
        for (s, r, net, elo, marg, tot, act) in ing._build_fit_rows():
            if s not in seasons:
                continue
            rows.append((s, r, net, elo, marg > 0.0, marg, tot, act))
        return rows

    import calibration as cal
    import config as cfg
    from engine_core import MatchupEngine
    saved_decay = cal.current.decay_factor
    saved_window = cfg.config.window_size
    if decay is not None:
        cal.current.decay_factor = decay
    if window is not None:
        cfg.config.window_size = window
    try:
        rows = []
        for m_id, info in ing.match_info.items():
            if info.season not in seasons or m_id.startswith('POST_'):
                continue
            if info.home_score == 0 and info.away_score == 0:
                continue
            if info.home_score == info.away_score:
                continue
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
                         info.home_score + info.away_score, act))
        return rows
    finally:
        cal.current.decay_factor = saved_decay
        cfg.config.window_size = saved_window


def run_mode(rows, window_seasons, label):
    """Walk forward: fit calibration on prior rows at each round boundary."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        groups[(r[0], r[1])].append(r)
    ordered = sorted(groups.items())

    prior = []
    out = []
    fallback_hits = 0
    for (season, rnd), group in ordered:
        sel = select_window(prior, season, window_seasons)
        cal = fit_or_fallback(sel, label)
        if cal.window == 'fallback':
            fallback_hits += 1
        for (s, r, net, elo, won, marg, tot, act) in group:
            m = cal.margin(net, elo / 100.0)  # the one calibrated output
            out.append((s, m, won, m, marg))
            # FitRow format for the calibration fit: (season, round, net,
            # elo_diff, margin, total, actual_delta) — NOT the collect_rows layout.
            prior.append((s, r, net, elo, marg, tot, act))
    return out, fallback_hits


def aggregate(rows):
    """Accuracy + margin error only (Brier removed 2026-08-10 — the margin is
    the single calibrated output; winner = margin sign)."""
    n = len(rows)
    acc = sum(1 for _, m, w, _, _ in rows if w == (m > 0)) / n
    mae = sum(abs(mp - am) for _, _, _, mp, am in rows) / n
    rmse = math.sqrt(sum((mp - am) ** 2 for _, _, _, mp, am in rows) / n)
    return n, acc, mae, rmse


def evaluate(seasons=None):
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
    roll2, fb2 = run_mode(rows, 2, 'roll2')
    expand, fbe = run_mode(rows, None, 'expanding')
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
        m = [r for r in roll2 if lo <= r[1] < hi]
        if m:
            print(f"  {lo:>4}-{hi:>4}      {len(m):>5}{sum(1 for _, _, w, _, _ in m if w)/len(m):>16.3f}")

    # Transparency: the fit at the final round (what production would ship)
    from calibration import current
    c = current
    print(f"\n active calibration (cache, latest fit): margin b1={c.margin_b1:.2f} b2={c.margin_b2:.2f} | "
          f"total {c.total_mean:.1f} | decay {c.decay_factor} | n={c.n_matches} [{c.window}]")


if __name__ == '__main__':
    evaluate(sys.argv[1:] or None)
