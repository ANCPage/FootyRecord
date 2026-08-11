"""Dynamic calibration (2026-08-10, audit follow-up).

Decision coefficients are no longer frozen config constants: they are
re-fitted from match history whenever the data changes, using only matches
strictly BEFORE the round being predicted (no leakage). Fits are computed on
ingestion and cached alongside the profiles; `current` holds the active
coefficients for decision paths (home_favored, margin, totals).

Fit window: rolling last N seasons (default 2, tracking the current meta) or
expanding (all history). evaluate.py A/Bs both and reports which wins.

The margin model has no intercept by design (no venue advantage, audit #1).

The probability layer was REMOVED 2026-08-10 (cleanest-model decision): the
margin is the single calibrated output; winner = margin sign; any percentage
shown is a display transform of the margin (MARGIN_TO_PROB_SCALE), not a
separately fitted model. Brier is gone — margin MAE is the honest error.

Shipped constants are the FALLBACK until enough history exists
(MIN_FIT_MATCHES), e.g. the first rounds of 2021.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import config as _config
import numpy as np

MIN_FIT_MATCHES = 60
WINDOW_SEASONS = 2  # production default: rolling last N seasons
MARGIN_TO_PROB_SCALE = 20.0  # display-only: sigmoid(margin/20) ~ probit fit of |margin| vs RMSE (~34)

# Shipped constants (fit on 2024-25, 2026-08-09/10) — bootstrap fallback only.
FALLBACK_MARGIN = (70.9755, 4.8817)       # b1(net), b2(elo/100)
FALLBACK_TOTAL = 159.26

FitRow = Tuple[int, int, float, float, float, float, float]  # season, round, net, elo_diff, margin, total, actual_delta


@dataclass
class Calibration:
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

    def margin(self, net_delta: float, elo_diff100: float) -> float:
        return self.margin_b1 * net_delta + self.margin_b2 * elo_diff100

    def prob_from_margin(self, margin: float) -> float:
        """DISPLAY-ONLY probability transform (not a fitted model): P(home win)
        ~ sigmoid(margin / MARGIN_TO_PROB_SCALE)."""
        return 1.0 / (1.0 + np.exp(-margin / MARGIN_TO_PROB_SCALE))

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

        - margin: least squares on [net_delta, elo_diff/100]
        - total:  mean actual match total
        - margin_divisor: median|actual_delta|/1.1 (Elo update scale; median
          gives margin_mult ~2.1, matching the original 2026-08-09 hand-fit)
        """
        Xm = np.column_stack([np.asarray(net_deltas, float),
                              np.asarray(elo_diffs, float) / 100.0])
        mb, *_ = np.linalg.lstsq(Xm, np.asarray(margins, float), rcond=None)
        if actual_deltas is not None and len(actual_deltas):
            med = float(np.median(np.abs(np.asarray(actual_deltas, float))))
            divisor = med / 1.1 if med > 0 else 0.3
        else:
            divisor = 0.3
        return Calibration(margin_b1=float(mb[0]), margin_b2=float(mb[1]),
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


def confidence_grade(margin: float) -> str:
    """Confidence grade from the PREDICTED MARGIN (cleanest-model 2026-08-10:
    the margin is the one calibrated output; no probability fiction).
    |margin| bands in points:
    F <4, E- <8, E <12, E+ <16, D- <20, D <24, D+ <28, C- <32, C <36,
    C+ <40, B- <45, B <50, B+ <55, A- <60, A <70, A+ >=70. Shared by the
    results DB (compute path) and the tips card (render path)."""
    score = abs(margin)
    if score < 4: return 'F'
    if score < 8: return 'E-'
    if score < 12: return 'E'
    if score < 16: return 'E+'
    if score < 20: return 'D-'
    if score < 24: return 'D'
    if score < 28: return 'D+'
    if score < 32: return 'C-'
    if score < 36: return 'C'
    if score < 40: return 'C+'
    if score < 45: return 'B-'
    if score < 50: return 'B'
    if score < 55: return 'B+'
    if score < 60: return 'A-'
    if score < 70: return 'A'
    return 'A+'


def select_window(rows: List[FitRow], cur_season: int,
                  window_seasons: int = None) -> List[FitRow]:
    """Rolling last N seasons (window_seasons=N) or expanding (None)."""
    if window_seasons is None:
        return rows
    lo = cur_season - window_seasons + 1
    return [r for r in rows if r[0] >= lo]


# Active coefficients for decision paths. The ingestor sets this on load
# (from cache or a fresh fit); stays at the shipped fallback otherwise.
current: Calibration = Calibration.fallback()
