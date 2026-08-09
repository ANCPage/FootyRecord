"""Walk-forward evaluation harness (audit E6 / menu #10).

Measures the SHIPPED model (config.py coefficients) against real results:
per-season and overall winner accuracy, Brier score, margin MAE/RMSE,
plus a calibration table. Run:  python evaluate.py [season ...]
Note: 2024-25 are in-sample for the calibration fits (config coefficients
were fitted on them); 2021-23 are out-of-sample for those coefficients.
"""
import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))
import config
from engine_data import DataIngestor
from engine_core import MatchupEngine

def evaluate(seasons=None):
    ing = DataIngestor('CSV_DATA')
    ing.load_all_data()
    ing.profile_all_teams()
    s = config.config

    if seasons is None:
        seasons = sorted({i.season for i in ing.match_info.values()})
    seasons = [int(x) for x in seasons]

    rows_all = []
    per_season = {}
    for year in seasons:
        matches = [m for m, i in ing.match_info.items() if i.season == year]
        matches.sort(key=lambda m: (ing.match_info[m].round, m))
        rows = []
        for m_id in matches:
            info = ing.match_info[m_id]
            if info.home_score == 0 and info.away_score == 0:
                continue
            if info.home_score == info.away_score:
                continue  # draws excluded (consistent with backtests)
            ma = ing.get_team_average_matrix(info.home, up_to_season=year,
                                             up_to_round=info.round)
            mb = ing.get_team_average_matrix(info.away, up_to_season=year,
                                             up_to_round=info.round)
            if not ma or not mb:
                continue
            net = sum(MatchupEngine.calculate_delta(ma, mb).values())
            eh = ing.get_team_elo(info.home, year, info.round)
            ea = ing.get_team_elo(info.away, year, info.round)
            # shipped probability model (config, no venue advantage)
            logit = s.prob_b0 + s.prob_b1 * net + s.prob_b2 * (eh - ea)
            p_home = 1.0 / (1.0 + math.exp(-logit))
            # shipped margin model
            margin_pred = (s.margin_intercept
                           + s.margin_delta_coef * net
                           + s.margin_elo_coef * ((eh - ea) / 100.0))
            home_won = info.home_score > info.away_score
            actual_margin = info.home_score - info.away_score
            rows.append((p_home, home_won, margin_pred, actual_margin))
        n = len(rows)
        if n == 0:
            continue
        acc = sum(1 for p, w, _, _ in rows if w == (p >= 0.5)) / n
        brier = sum((p - w) ** 2 for p, w, _, _ in rows) / n
        mae = sum(abs(mp - am) for _, _, mp, am in rows) / n
        rmse = math.sqrt(sum((mp - am) ** 2 for _, _, mp, am in rows) / n)
        per_season[year] = (n, acc, brier, mae, rmse)
        rows_all.extend(rows)

    print("=" * 64)
    print(" WALK-FORWARD EVALUATION (shipped model, config coefficients)")
    print("=" * 64)
    print(f"{'Season':<8}{'n':>6}{'Acc%':>8}{'Brier':>8}{'MAE':>7}{'RMSE':>7}")
    print("-" * 64)
    for year in sorted(per_season):
        n, acc, brier, mae, rmse = per_season[year]
        tag = "  <- in-sample (calibration fit)" if year in (2024, 2025) else ""
        print(f"{year:<8}{n:>6}{100*acc:>7.1f}{brier:>8.4f}{mae:>7.1f}{rmse:>7.1f}{tag}")
    n = len(rows_all)
    if n:
        acc = sum(1 for p, w, _, _ in rows_all if w == (p >= 0.5)) / n
        brier = sum((p - w) ** 2 for p, w, _, _ in rows_all) / n
        mae = sum(abs(mp - am) for _, _, mp, am in rows_all) / n
        rmse = math.sqrt(sum((mp - am) ** 2 for _, _, mp, am in rows_all) / n)
        print("-" * 64)
        print(f"{'ALL':<8}{n:>6}{100*acc:>7.1f}{brier:>8.4f}{mae:>7.1f}{rmse:>7.1f}")
        print()
        print(" Calibration (pooled, by predicted home probability):")
        print(f"{'bin':<14}{'n':>6}{'actual win rate':>16}")
        for lo, hi in [(0.0, 0.35), (0.35, 0.5), (0.5, 0.65), (0.65, 1.0)]:
            m = [r for r in rows_all if lo <= r[0] < hi]
            if m:
                print(f"  {lo:.2f}-{hi:.2f}      {len(m):>5}{sum(1 for p, w, _, _ in m if w)/len(m):>16.3f}")

if __name__ == '__main__':
    evaluate(sys.argv[1:] or None)
