import datetime
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
# Margin calibration is DYNAMIC (Core/calibration.py, fitted on ingestion —
# audit follow-up 2026-08-10). Fallback constants live in calibration.py.
# Probability calibration: P(home win) = sigmoid(b0 + b1*net_delta + b2*elo_diff).
# Dynamic too — see calibration.py. b0 = 0 by design (no venue advantage; the
# AFL "home" label is unreliable — shared/neutral grounds).
# Total-score estimate: dynamic mean of actual match totals (calibration.py).
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

SEASONS = list(range(2021, datetime.datetime.now().year + 1))
