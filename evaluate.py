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
            p = cal.prob_home(net, elo)
            m = cal.margin(net, elo / 100.0)
            out.append((s, p, won, m, marg))
            # FitRow format for the calibration fit: (season, round, net,
            # elo_diff, margin, total, actual_delta) — NOT the collect_rows layout.
            prior.append((s, r, net, elo, marg, tot, act))
    return out, fallback_hits


def aggregate(rows):
    n = len(rows)
    acc = sum(1 for _, p, w, _, _ in rows if w == (p >= 0.5)) / n
    brier = sum((p - w) ** 2 for _, p, w, _, _ in rows) / n
    mae = sum(abs(mp - am) for _, _, _, mp, am in rows) / n
    rmse = math.sqrt(sum((mp - am) ** 2 for _, _, _, mp, am in rows) / n)
    return n, acc, brier, mae, rmse


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
    print(f"{'Season':<8}{'n':>5}{'roll2%':>8}{'exp%':>7}{'r2Brier':>9}{'eBrier':>8}{'r2MAE':>7}{'eMAE':>7}")
    print("-" * 78)
    for year in sorted({r[0] for r in rows}):
        a = [r for r in roll2 if r[0] == year]
        b = [r for r in expand if r[0] == year]
        na, acca, bria, maea, _ = aggregate(a)
        nb, accb, brieb, maeb, _ = aggregate(b)
        print(f"{year:<8}{na:>5}{100*acca:>7.1f}{100*accb:>7.1f}{bria:>9.4f}{brieb:>8.4f}{maea:>7.1f}{maeb:>7.1f}")

    n, acc, brier, mae, rmse = aggregate(roll2)
    n2, acc2, brier2, mae2, rmse2 = aggregate(expand)
    print("-" * 78)
    print(f"{'ALL':<8}{n:>5}{100*acc:>7.1f}{100*acc2:>7.1f}{brier:>9.4f}{brier2:>8.4f}{mae:>7.1f}{mae2:>7.1f}")
    print(f"\n  rolling-2 : acc {100*acc:.1f}%  Brier {brier:.4f}  MAE {mae:.1f}  RMSE {rmse:.1f}")
    print(f"  expanding: acc {100*acc2:.1f}%  Brier {brier2:.4f}  MAE {mae2:.1f}  RMSE {rmse2:.1f}")

    print()
    print(" Calibration (pooled, by predicted home probability) — rolling-2:")
    print(f"{'bin':<14}{'n':>6}{'actual win rate':>16}")
    for lo, hi in [(0.0, 0.35), (0.35, 0.5), (0.5, 0.65), (0.65, 1.0)]:
        m = [r for r in roll2 if lo <= r[1] < hi]
        if m:
            print(f"  {lo:.2f}-{hi:.2f}      {len(m):>5}{sum(1 for _, p, w, _, _ in m if w)/len(m):>16.3f}")

    # Transparency: the fit at the final round (what production would ship)
    from calibration import current
    c = current
    print(f"\n active calibration (cache, latest fit): prob b1={c.prob_b1:.4f} b2={c.prob_b2:.4f} | "
          f"margin b1={c.margin_b1:.2f} b2={c.margin_b2:.2f} | total {c.total_mean:.1f} | n={c.n_matches} [{c.window}]")


if __name__ == '__main__':
    evaluate(sys.argv[1:] or None)
