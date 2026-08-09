import os

# Project Root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directory Paths
DATA_DIR = os.path.join(PROJECT_ROOT, 'CSV_DATA')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'ROUND_IMAGES_UPDATE')
FONTS_DIR = os.path.join(PROJECT_ROOT, 'downloaded_fonts')

# Engine Settings
DECAY_FACTOR = 0.9
TIME_DECAY_FACTOR = 0.8
WINDOW_SIZE = 25
ELO_WEIGHT = 1.0
ELO_K = 32
# Margin calibration: margin = b0 + b1*net_delta + b2*elo_diff, fitted via
# `python analyze_margins.py` (412 matches 2024-25, r=0.540; elo_diff = (h-a)/100).
# Re-fit whenever the engine/data changes.
MARGIN_INTERCEPT = 6.2299
MARGIN_DELTA_COEF = 107.4945
MARGIN_ELO_COEF = 3.6828
# Probability calibration: P(home win) = sigmoid(b0 + b1*net_delta + b2*(elo diff)).
# Fitted 2026-08-09 via `python fit_calibration.py` (412 matches, Brier 0.2023
# vs 0.2066 for the old net_delta*80 formula).
# NOTE: b0 (home-ground intercept) is deliberately 0 — the AFL "home" label is
# unreliable (shared/neutral grounds, venue isn't always home team's), so no
# venue advantage is applied. Fit suggested ~0.30; set back if you want it.
PROB_B0 = 0.0
PROB_B1 = 3.7866
PROB_B2 = 0.0036
# Total-score estimate: normalized matrices no longer carry scoring volume, so
# the shots*4 heuristic is meaningless (clamped 100% of the time). Use the
# fitted league-average match total (fit_calibration.py).
TOTAL_SCORE_MEAN = 159.26
# Elo margin scaling: margin_mult = clamp(0.5, 3.0, |delta|/D + 1). D recalibrated
# 2026-08-09 from actual-match deltas (median |delta| = 0.32 -> typical mult ~2.1;
# D=0.1 overshot and clamped most matches at 3.0, hurting the baseline).
ELO_MARGIN_DIVISOR = 0.3

class Settings:
    # (min, max) validation for runtime-mutable settings (audit #15).
    _RANGES = {
        'decay_factor': (0.0, 1.0),
        'time_decay_factor': (0.0, 1.0),
        'window_size': (1, None),
        'elo_k': (1.0, None),
        'elo_weight': (0.0, None),
        'elo_margin_divisor': (0.01, None),
    }

    def __setattr__(self, name, value):
        if name in self._RANGES:
            lo, hi = self._RANGES[name]
            ok = value >= lo if hi is None else lo <= value <= hi
            if not ok:
                raise ValueError(
                    f"config.{name} must be within [{lo}, {hi if hi is not None else 'inf'}], got {value}")
        super().__setattr__(name, value)

    def __init__(self):
        self.decay_factor = DECAY_FACTOR
        self.time_decay_factor = TIME_DECAY_FACTOR
        self.window_size = WINDOW_SIZE
        self.elo_weight = ELO_WEIGHT
        self.elo_k = ELO_K
        self.margin_intercept = MARGIN_INTERCEPT
        self.margin_delta_coef = MARGIN_DELTA_COEF
        self.margin_elo_coef = MARGIN_ELO_COEF
        self.prob_b0 = PROB_B0
        self.prob_b1 = PROB_B1
        self.prob_b2 = PROB_B2
        self.total_score_mean = TOTAL_SCORE_MEAN
        self.elo_margin_divisor = ELO_MARGIN_DIVISOR
        self.data_dir = DATA_DIR
        self.output_dir = OUTPUT_DIR
        self.fonts_dir = FONTS_DIR

# Global config object that can be mutated at runtime
config = Settings()

# AFL API Configuration
AFL_AUTH_URL = "https://api.afl.com.au/cfs/afl/WMCTok"
AFL_MATCH_PLAYS_URL = "https://sapi.afl.com.au/afl/matchPlays/{}"
AFL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Origin": "https://www.afl.com.au",
    "Referer": "https://www.afl.com.au/"
}

MAX_RETRIES = 3
GAMES_PER_ROUND = 9
MAX_ROUNDS = 24
import datetime
SEASONS = list(range(2021, datetime.datetime.now().year + 1))
