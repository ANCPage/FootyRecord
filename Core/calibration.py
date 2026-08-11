"""Dynamic calibration (2026-08-10, audit follow-up).

Decision coefficients are no longer frozen config constants: they are
re-fitted from match history whenever the data changes, using only matches
strictly BEFORE the round being predicted (no leakage). Fits are computed on
ingestion and cached alongside the profiles; `current` holds the active
coefficients for decision paths (home_favored, margin, totals).

Fit window: rolling last N seasons (default 2, tracking the current meta) or
expanding (all history). evaluate.py A/Bs both and reports which wins.

The probability intercept stays 0 by design (no venue advantage, audit #1).
The margin model has no intercept either (audit #1 consistency).

Shipped constants are the FALLBACK until enough history exists
(MIN_FIT_MATCHES), e.g. the first rounds of 2021.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import config as _config
import numpy as np

MIN_FIT_MATCHES = 60
WINDOW_SEASONS = 2  # production default: rolling last N seasons

# Shipped constants (fit on 2024-25, 2026-08-09/10) — bootstrap fallback only.
FALLBACK_PROB = (0.0, 3.7866, 0.0036)     # b0, b1(net), b2(elo raw)
FALLBACK_MARGIN = (70.9755, 4.8817)       # b1(net), b2(elo/100)
FALLBACK_TOTAL = 159.26

FitRow = Tuple[int, int, float, float, float, float, float]  # season, round, net, elo_diff, margin, total, actual_delta


@dataclass
class Calibration:
    prob_b0: float = 0.0
    prob_b1: float = FALLBACK_PROB[1]
    prob_b2: float = FALLBACK_PROB[2]
    margin_b1: float = FALLBACK_MARGIN[0]
    margin_b2: float = FALLBACK_MARGIN[1]
    total_mean: float = FALLBACK_TOTAL
    margin_divisor: float = _config.config.elo_margin_divisor  # dynamic: median|actual_delta|/1.1
    decay_factor: float = _config.DECAY_FACTOR                # dynamic: fitted on ingestion (Option B)
    tier_cutoffs: tuple = ()          # (elite_min, contender_min, mid_min) — dynamic percentiles
    n_matches: int = 0
    window: str = 'fallback'

    @classmethod
    def fallback(cls) -> "Calibration":
        return cls()

    def logit(self, net_delta: float, elo_diff_raw: float) -> float:
        return self.prob_b0 + self.prob_b1 * net_delta + self.prob_b2 * elo_diff_raw

    def prob_home(self, net_delta: float, elo_diff_raw: float) -> float:
        return 1.0 / (1.0 + np.exp(-self.logit(net_delta, elo_diff_raw)))

    def margin(self, net_delta: float, elo_diff_hundreds: float) -> float:
        return self.margin_b1 * net_delta + self.margin_b2 * elo_diff_hundreds

    def tier(self, elo: float) -> str:
        """Distribution-relative tier (top-4 ELITE, next-4 CONTENDER, next-5
        MID-TABLE, rest REBUILDING); absolute-threshold fallback when no
        cutoffs fitted yet (e.g. tests, early data)."""
        if self.tier_cutoffs:
            elite_min, contender_min, mid_min = self.tier_cutoffs
            if elo >= elite_min: return "ELITE"
            if elo >= contender_min: return "CONTENDER"
            if elo >= mid_min: return "MID-TABLE"
            return "REBUILDING"
        if elo >= 1600: return "ELITE"
        if elo >= 1550: return "CONTENDER"
        if elo >= 1450: return "MID-TABLE"
        return "REBUILDING"

    @staticmethod
    def fit(net_deltas, elo_diffs, margins, totals, actual_deltas=None,
            window='fit') -> "Calibration":
        """Fit all decision coefficients with NO intercept (b0=0 semantics).

        - probability: IRLS logistic on [net_delta, elo_diff_raw]
        - margin:      least squares on [net_delta, elo_diff/100]
        - total:       mean actual match total
        - margin_divisor: median|actual_delta|/1.1 (Elo update scale; median
          gives margin_mult ~2.1, matching the original 2026-08-09 hand-fit)
        """
        Xp = np.column_stack([np.asarray(net_deltas, float),
                              np.asarray(elo_diffs, float)])
        y = (np.asarray(margins, float) > 0).astype(float)
        b = np.zeros(2)
        for _ in range(60):
            p = 1.0 / (1.0 + np.exp(-(Xp @ b)))
            W = p * (1 - p)
            H = Xp.T @ (Xp * W[:, None])
            g = Xp.T @ (y - p)
            try:
                b += np.linalg.solve(H + 1e-9 * np.eye(2), g)
            except np.linalg.LinAlgError:
                break
        Xm = np.column_stack([np.asarray(net_deltas, float),
                              np.asarray(elo_diffs, float) / 100.0])
        mb, *_ = np.linalg.lstsq(Xm, np.asarray(margins, float), rcond=None)
        if actual_deltas is not None and len(actual_deltas):
            med = float(np.median(np.abs(np.asarray(actual_deltas, float))))
            divisor = med / 1.1 if med > 0 else 0.3
        else:
            divisor = 0.3
        return Calibration(prob_b0=0.0, prob_b1=float(b[0]), prob_b2=float(b[1]),
                           margin_b1=float(mb[0]), margin_b2=float(mb[1]),
                           total_mean=float(np.mean(totals)),
                           margin_divisor=divisor,
                           n_matches=len(net_deltas), window=window)


def fit_or_fallback(rows: List[FitRow], window_label: str) -> Calibration:
    """Fit on the given rows, or return the shipped fallback if too little data."""
    if len(rows) < MIN_FIT_MATCHES:
        return Calibration.fallback()
    nets = [r[2] for r in rows]
    elos = [r[3] for r in rows]
    marg = [r[4] for r in rows]
    tots = [r[5] for r in rows]
    acts = [r[6] for r in rows]
    return Calibration.fit(nets, elos, marg, tots, acts, window=window_label)


def compute_tier_cutoffs(team_elos: List[float]) -> Tuple:
    """Top-4 ELITE / next-4 CONTENDER / next-5 MID-TABLE cutoffs from the live
    Elo distribution (18 AFL teams). Empty tuple (absolute-threshold fallback)
    when the field is too small to split meaningfully."""
    if len(team_elos) < 8:
        return ()
    s = sorted(team_elos, reverse=True)
    return (s[3], s[7], s[12])


def select_window(rows: List[FitRow], cur_season: int,
                  window_seasons: Optional[int]) -> List[FitRow]:
    """Rolling last N seasons (window_seasons=N) or expanding (None)."""
    if window_seasons is None:
        return rows
    lo = cur_season - window_seasons + 1
    return [r for r in rows if r[0] >= lo]


# Active coefficients for decision paths. The ingestor sets this on load
# (from cache or a fresh fit); stays at the shipped fallback otherwise.
current: Calibration = Calibration.fallback()
