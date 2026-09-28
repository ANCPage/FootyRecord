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
margin is the single calibrated output; winner = margin sign. The display-only
percentage helper (prob_from_margin / MARGIN_TO_PROB_SCALE) was REMOVED
2026-08-12 (re-audit #4: vestigial — nothing displayed it since the server
decommission). Brier is gone — margin MAE is the honest error.

Shipped constants are the FALLBACK until enough history exists
(MIN_FIT_MATCHES), e.g. the first rounds of 2021.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

import Core.config as _config
from Core.engine_core import home_favored

# Structurally derived, not chosen: a least-squares fit of 2 parameters needs
# enough rows that the design matrix is well conditioned. 20 rows per parameter.
MIN_FIT_ROWS_PER_PARAM = 20
MIN_FIT_MATCHES = MIN_FIT_ROWS_PER_PARAM * 2   # 2 fitted parameters (net, elo/100)
# FIT window: how many SEASONS of matches the margin/total fit uses. Different animal
# from config.MATRIX_WINDOW_GAMES (games in the tactical fingerprint) — both were called
# 'window' until 2026-09-14 (calibration audit finding 4).
FIT_WINDOW_SEASONS = 2

# SCAN-FITTED (refit_hyperparams.py): the margin scale is the median winning
# margin divided by this. Previously a literal 1.1 that reproduced an older
# hand-fit; now a scanned value like every other engine hyperparameter, so it is
# data-chosen rather than assumed (magic-numbers pass, 2026-09-14).
DIVISOR_FACTOR = 1.1

# Used ONLY when there is not yet a single completed match to take a median from
# (cold corpus). Expressed as a divisor of a typical AFL winning margin so the
# scale is explicit rather than a bare literal: 30 points / 1.1, the same relation
# the fitted divisor uses. Scanned with DIVISOR_FACTOR once data exists.
TYPICAL_WINNING_MARGIN = 30.0
BOOTSTRAP_DIVISOR = TYPICAL_WINNING_MARGIN / DIVISOR_FACTOR
# The trailing window for the projected total is the CURRENT SEASON's completed
# matches (fallback: the previous season when the current one is too young) — so
# the estimate is "what scoring looks like now" without a literal match count.
TRAILING_MIN_GAMES = 30          # below this, fall back to the previous season

# FITTED BY MEASUREMENT (scan_window.py): how many recent matches the projected total
# is estimated over. None = fall back to the season-derived rule.
#
# Scored on mean absolute per-season totals bias over a full walk-forward rebuild
# (2026-09-14):
#     15 -> 0.745 | 20 -> 0.602 | 25 -> 0.691 | 30 -> 0.773 | 40 -> 1.011
#     60 -> 1.214 | 90 -> 1.751 | 120 -> 2.211 | season-derived -> 1.758
# A clean interior optimum at 20. The 60 that sat here originally was a literal nobody
# had measured: it is TWICE as bad as the fitted value. The season-derived rule, which
# briefly replaced it, is the worst of the lot. Per-season bias at 20: 2021 +0.79,
# 2022 -0.01, 2023 -0.53, 2024 -0.74, 2025 -0.08, 2026 -1.47.
# Re-run scan_window.py when the game or the data changes.
TRAILING_WINDOW_FIT = 20

# Bootstrap fallback ONLY (used when there is too little history to fit).
#
# RE-FITTED 2026-09-14 on the SCORE-CORRECTED data — the previous pair
# (70.9755, 4.8817) / 159.26 was fitted 2026-08-09/10 against the light scores and
# was by then ~37% low on margin scaling and ~15 points light on totals, while
# still being reachable from the live prediction path (calibration audit, findings
# 1-2). Values come from Core.tools.refit_fallbacks --seasons 2024 2025
# (413 rows, r=0.548): re-run that tool after any engine or data-scale change.
FALLBACK_MARGIN = (66.3774, 5.8006)       # b1(net), b2(elo/100)
FALLBACK_TOTAL = 168.6320

FitRow = Tuple[int, int, float, float, float, float, float, str, str, str]  # season, round, net, elo_diff, margin, total, actual_delta, match_id, home, away


@dataclass
class Calibration:
    margin_b1: float = FALLBACK_MARGIN[0]
    margin_b2: float = FALLBACK_MARGIN[1]
    total_mean: float = FALLBACK_TOTAL
    total_trailing: float = 0.0       # mean total over the most recent TRAILING_MATCHES
                                      # (walk-forward); 0 = not available, use total_mean
    margin_divisor: float = _config.config.elo_margin_divisor  # dynamic: median|actual_delta| / DIVISOR_FACTOR
    decay_factor: float = _config.DECAY_FACTOR                # dynamic: fitted on ingestion (Option B)
    tier_cutoffs: tuple = ()          # (elite_min, contender_min, mid_min) — dynamic percentiles
    n_matches: int = 0
    window: str = 'fallback'
    # Provenance (2026-09-12): the data identity this fit was made from, so a
    # stale fit can never masquerade as current. Written at ingest, verified on
    # every load (state_store.verify_state). Metadata only — never affects the
    # fitted numbers themselves.
    fit_fingerprint: str = ''         # csv fingerprint the coefficients were fitted on
    fit_n_matches: int = 0            # matches in the fitted state at fit time
    source: str = 'fitted'            # 'fitted' | 'fallback' (fallback = constants)

    @classmethod
    def fallback(cls) -> "Calibration":
        return cls(window='fallback', source='fallback')

    def margin(self, net_delta: float, elo_diff100: float) -> float:
        return self.margin_b1 * net_delta + self.margin_b2 * elo_diff100

    def projected_total(self) -> float:
        """The total to project a scoreline onto.

        Prefers the TRAILING mean (the last TRAILING_MATCHES games) over the
        two-season mean: using a fixed anchor makes the totals error purely the gap
        between the anchor and the season being played (calibration audit finding 5,
        measured: +14.8 in 2021 down to -5.1 in 2026). Falls back to total_mean when
        no trailing value was fitted.
        """
        return self.total_trailing or self.total_mean

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
        - margin_divisor: median|actual_delta| / DIVISOR_FACTOR (Elo update scale; median
          gives margin_mult ~2.1, matching the original 2026-08-09 hand-fit)
        """
        Xm = np.column_stack([np.asarray(net_deltas, float),
                              np.asarray(elo_diffs, float) / 100.0])
        mb, *_ = np.linalg.lstsq(Xm, np.asarray(margins, float), rcond=None)
        if actual_deltas is not None and len(actual_deltas):
            med = float(np.median(np.abs(np.asarray(actual_deltas, float))))
            divisor = med / DIVISOR_FACTOR if med > 0 else _config.config.elo_margin_divisor
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


def fit_walk_forward(rows: List[FitRow], season: int, round_num: int,
                     window_seasons: int = FIT_WINDOW_SEASONS,
                     ) -> "Calibration":
    """Fit on matches STRICTLY BEFORE (season, round) — the honest, out-of-sample
    fit used by the record path.

    The ingest path (`profiler.fit_calibration`) fits ONCE over a rolling window
    that INCLUDES the season being predicted, so its coefficients have already seen
    that season's outcomes. That is fine for a live round (the results do not exist
    yet) and wrong for a re-record or a backtest, where it flatters the accuracy
    (calibration audit finding 3). This function removes that: rows are filtered by
    (season, round), so a projection for R5 knows only R1-R4 plus prior seasons.
    """
    usable = [r for r in rows if (r[0], r[1]) < (season, round_num)]
    if len(usable) < MIN_FIT_MATCHES:
        return Calibration.fallback()
    sel = select_window(usable, season, window_seasons)
    c = fit_or_fallback(sel, f'wf-roll{window_seasons}')
    c.total_trailing = _trailing_total(usable)
    return c


# The presentation ladder. Its LENGTH is what decides how many tier cutoffs exist,
# so no count is hardcoded: 4 tiers -> 3 cutoffs (magic-numbers pass, 2026-09-14).
TIER_NAMES = ('ELITE', 'CONTENDER', 'MID-TABLE', 'REBUILDING')
MIN_TIER_SIZE = 2                  # a tier has to hold more than one team

POINTS_PER_GOAL_DEFINITION = 6.0   # laws of the game: a goal is worth six points


def points_per_goal(goals: float, behinds: float) -> float:
    """Points per goal, DERIVED from one consistent source of scoring data.

    (6 * goals + behinds) / goals. The 6 is the law of the game, not a fit; the
    behinds-to-goals ratio is the part that moves with the data.

    Was a literal 6.71 typed into TWO modules (Core/player_props.py and
    Core/tools/props_backtest.py). Two things were wrong with it: the duplication
    could drift, and it mixed sources — corrected team points divided by goals the
    feed only partly attributes. On the corrected data that pairing reads 7.10
    against a feed-consistent 6.70, so the props layer was inflating projected goal
    volume by ~6% (magic-numbers pass, 2026-09-14). Callers must pass totals from the
    SAME source as the points they are dividing.
    """
    if not goals:
        return POINTS_PER_GOAL_DEFINITION
    return (POINTS_PER_GOAL_DEFINITION * goals + behinds) / goals


def _trailing_total(usable: List[FitRow]) -> float:
    """The total to project a scoreline onto: this season's own scoring level.

    No fixed match count (that was a magic 60) and no bare-bones early season either.
    A pooled version — this season shrunk toward the previous season by sample size —
    was TRIED and REVERTED on 2026-09-14: measured mean absolute bias 2.08 against
    1.76 for this rule, and it did not move 2021 at all, because 2021 is the FIRST
    season in the corpus and has no previous season to borrow from. 2021's early-round
    totals bias (+4.88) is therefore a COLD-START data boundary, not an estimator
    flaw: no estimator can know the scoring level before any games exist. The real
    fixes are more history (2020 scores) or not publishing a totals claim for those
    rounds — not a cleverer formula.
    """
    if not usable:
        return 0.0
    if TRAILING_WINDOW_FIT:
        recent = usable[-TRAILING_WINDOW_FIT:]
        return float(np.mean([r[5] for r in recent])) if recent else 0.0
    cur = max(r[0] for r in usable)
    same = [r[5] for r in usable if r[0] == cur]
    if len(same) >= TRAILING_MIN_GAMES:
        return float(np.mean(same))
    prev = [r[5] for r in usable if r[0] == cur - 1]
    if prev:
        return float(np.mean(prev))
    return float(np.mean(same)) if same else float(np.mean([r[5] for r in usable]))


def compute_tier_cutoffs(team_elos: List[float]) -> Tuple:
    """Tier cutoffs taken from the LIVE Elo field: the biggest gaps in the sorted
    field, restricted to the middle band so an outlier is never cut off alone.

    Returns one cutoff per boundary between TIER_NAMES (4 tiers -> 3 cutoffs, the
    length of the ladder itself, so no count is hardcoded). Each cutoff sits at the
    midpoint of its gap, so no team lands on a boundary (2026-08-26: percentile
    cutoffs EQUALLED the boundary team's rating and tiers flipped on floating-point
    epsilons). Empty tuple when the field is too small for one group per tier.

    Replaces literal indices s[3]/s[4], s[7]/s[8], s[12]/s[13] — the tier SIZES
    4/4/5 were hardcoded, so the ladder could not follow the data (magic-numbers
    pass, 2026-09-14).
    """
    n = len(team_elos)
    n_breaks = len(TIER_NAMES) - 1
    if n < (n_breaks + 1) * MIN_TIER_SIZE:
        return ()
    s_ = sorted(team_elos, reverse=True)
    # Candidate positions, leaving room for a group either side of every break.
    cands = [i for i in range(MIN_TIER_SIZE, n - MIN_TIER_SIZE)]
    if len(cands) < n_breaks:
        return ()
    ranked = sorted(cands, key=lambda i: s_[i] - s_[i + 1], reverse=True)
    chosen = []
    for i in ranked:                      # keep breaks apart: one per position
        if all(abs(i - j) >= MIN_TIER_SIZE for j in chosen):
            chosen.append(i)
        if len(chosen) == n_breaks:
            break
    if len(chosen) < n_breaks:
        return ()
    return tuple((s_[i] + s_[i + 1]) / 2.0 for i in sorted(chosen))


def align_margin(margin: float, net_delta: float, elo_diff_hundreds: float) -> float:
    """Direction comes from the RAW signal, never from the fit (2026-08-11:
    the Elo blend sets the SIZE only — the fitted margin can never flip the
    raw delta's direction). Dead-even delta -> Elo side.

    ONE winner rule: delegates to engine_core.home_favored (dedup audit
    2026-09-05, item 1). The elo args are passed as (diff, 0.0) because only
    the h_elo >= a_elo comparison matters.
    """
    home = home_favored(net_delta, elo_diff_hundreds, 0.0)
    return abs(margin) if home else -abs(margin)


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


# NOTE (Phase 1, 2026-08-26): the module-level `current` global was REMOVED.
# Calibration now travels with the ingestor (`ing.calibration`) — every
# decision path takes it explicitly. Hidden mutable module state was the bug
# class behind the old `config.config.window_size` family of errors: two places
# disagreed about which calibration was active and nothing complained.
# tests/test_no_global_calibration.py guards against reintroduction.
