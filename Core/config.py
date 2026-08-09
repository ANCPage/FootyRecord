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
# Margin calibration: Expected Margin = slope * combined_score + intercept.
# Fitted 2026-08-09 via `python analyze_margins.py` on normalized matrices
# (412 matches, r=0.538). Re-fit whenever the engine/data changes.
MARGIN_SLOPE = 144.1387
MARGIN_INTERCEPT = 6.1856

class Settings:
    def __init__(self):
        self.decay_factor = DECAY_FACTOR
        self.time_decay_factor = TIME_DECAY_FACTOR
        self.window_size = WINDOW_SIZE
        self.elo_weight = ELO_WEIGHT
        self.elo_k = ELO_K
        self.margin_slope = MARGIN_SLOPE
        self.margin_intercept = MARGIN_INTERCEPT
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
