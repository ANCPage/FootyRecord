"""Investigate the two remaining magic calibrations in server.py:

1. Probability model (line ~496):  rating_diff = (h_elo-a_elo) + net_delta*80
   -> fit a proper logistic: P(home win) = sigmoid(b0 + b1*net_delta + b2*elo_raw)
2. Total-score heuristic (line ~486): total = (shots_a+shots_b) * 4.0, clamp [80,240]
   -> regress actual match totals on the shots feature; check clamp behaviour
     after matrix normalization (audit E2).

Walk-forward over 2024-2025, same guards as the backtests.
"""
import sys
sys.path.insert(0, 'Core')
import numpy as np
from engine_data import DataIngestor
from engine_core import MatchupEngine

ing = DataIngestor('CSV_DATA')
ing.load_all_data()
ing.profile_all_teams()

Xp = []   # probability features: [1, net_delta, elo_raw]
Yp = []   # home win (1/0)
Xt = []   # total-score features: [1, shots_sum]
Yt = []   # actual total score
clamp_hits = 0
n_matches = 0

for year in (2024, 2025):
    matches = [m for m, i in ing.match_info.items() if i.season == year]
    matches.sort(key=lambda m: (ing.match_info[m].round, m))
    for m_id in matches:
        info = ing.match_info[m_id]
        h, a = info.home, info.away
        if info.home_score == 0 and info.away_score == 0:
            continue
        m_a = ing.get_team_average_matrix(h, up_to_season=year, up_to_round=info.round)
        m_b = ing.get_team_average_matrix(a, up_to_season=year, up_to_round=info.round)
        if not m_a or not m_b:
            continue
        delta = MatchupEngine.calculate_delta(m_a, m_b)
        net = sum(delta.values())
        elo_h = ing.get_team_elo(h, year, info.round)
        elo_a = ing.get_team_elo(a, year, info.round)

        n_matches += 1
        # probability features
        Xp.append([1.0, net, elo_h - elo_a])
        Yp.append(1.0 if info.home_score > info.away_score else 0.0)
        # total score features (exactly as server.py computes them)
        shots_a = sum(s for e, s in m_a.items() if e.target == 'SCORE')
        shots_b = sum(s for e, s in m_b.items() if e.target == 'SCORE')
        shots = shots_a + shots_b
        total_guess = shots * 4.0
        if total_guess < 80.0 or total_guess > 240.0:
            clamp_hits += 1
        Xt.append([1.0, shots])
        Yt.append(info.home_score + info.away_score)

Xp, Yp = np.array(Xp), np.array(Yp)
Xt, Yt = np.array(Xt), np.array(Yt)

print(f"matches analysed: {n_matches}")

# --- 1. current probability model (server formula) -> Brier ---
def brier_of(X, y, b):
    logit = X @ b
    p = 1.0 / (1.0 + np.exp(-logit))
    return float(np.mean((p - y) ** 2))

# server formula: rating_diff = elo_raw + net*80 ; prob = 1/(1+10^(-rating_diff/400))
def server_prob(X):
    rating_diff = X[:, 2] + X[:, 1] * 80.0
    return 1.0 / (1.0 + 10.0 ** (-rating_diff / 400.0))

sp = server_prob(Xp)
print(f"\nCURRENT server probability model:")
print(f"  Brier = {np.mean((sp - Yp)**2):.4f}  (0=perfect, 0.25=coin flip)")

# --- 2. fitted logistic on same features ---
# IRLS logistic regression (no sklearn dependency)
def logit_fit(X, y, iters=50):
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ b)))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None])
        g = X.T @ (y - p)
        try:
            b += np.linalg.solve(H + 1e-9 * np.eye(H.shape[0]), g)
        except np.linalg.LinAlgError:
            break
    return b

bfit = logit_fit(Xp, Yp)
print(f"\nFITTED logistic (P(home win) = sigmoid(b0 + b1*net_delta + b2*elo_raw)):")
print(f"  b0(intercept) = {bfit[0]:+.4f}   b1(net_delta) = {bfit[1]:+.4f}   b2(elo diff) = {bfit[2]:+.4f}")
print(f"  Brier = {brier_of(Xp, Yp, bfit):.4f}")
print(f"  implied elo scale: b1/b2 = {bfit[1]/max(bfit[2],1e-9):.2f} (old magic: 80)")

# calibration table for fitted model
pf = 1.0 / (1.0 + np.exp(-(Xp @ bfit)))
print("\n  Calibration (fitted model):")
print("  pred bin      n     actual win rate")
for lo, hi in [(0.0, 0.4), (0.4, 0.55), (0.55, 0.7), (0.7, 1.0)]:
    m = (pf >= lo) & (pf < hi)
    if m.sum():
        print(f"  {lo:.2f}-{hi:.2f}      {m.sum():5d}   {Yp[m].mean():.3f}")

# --- 3. total score: fit + clamp behaviour ---
slope, icpt = np.polyfit(Xt[:, 1], Yt, 1)
print(f"\nTOTAL SCORE regression: total = {slope:.3f}*(shots_sum) + {icpt:.2f}")
print(f"  shots_sum range: [{Xt[:,1].min():.3f}, {Xt[:,1].max():.3f}]  mean {Xt[:,1].mean():.3f}")
print(f"  actual total mean = {Yt.mean():.1f}  (clamp engaged {clamp_hits}/{n_matches} times, "
      f"{100*clamp_hits/n_matches:.0f}%)")
print(f"  x4 heuristic mean = {(Xt[:,1]*4.0).mean():.1f}")
r = np.corrcoef(Xt[:, 1], Yt)[0, 1]
print(f"  correlation shots_sum vs total: r = {r:.3f}")
