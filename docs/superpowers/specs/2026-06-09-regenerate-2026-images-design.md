# Design Spec: Regenerating 2026 Round Images (R0-R13)

## Goal
Completely reset and regenerate all diagnostic and visual round images for the 2026 AFL season, from Round 0 through Round 13, using the latest available statistical data.

## Context
- **Data Source:** `CSV_DATA/flattened_stats_2026_simple.csv` (contains data through Round 13).
- **Output Directory:** `ROUND_IMAGES_UPDATE/2026/`.
- **Engine:** `generate_round_images.py` which handles ELO calculation, matchup visualization, story maps, and ladder updates.

## Proposed Changes

### 1. Environment Reset
- **Action:** Delete all subdirectories within `ROUND_IMAGES_UPDATE/2026/` (R0, R1, etc.).
- **Action:** Delete the model cache file `CSV_DATA/.cache/ingestor_state.pkl`.
- **Reasoning:** Ensures that ELO ratings and team profiles are recalculated from the ground up, incorporating the newly downloaded Round 8-13 data into the historical window correctly.

### 2. Batch Processing
- **Action:** Execute `python generate_round_images.py --round <N>` for each round `N` from 0 to 13.
- **Sequence:**
    - Round 0
    - Round 1
    - ...
    - Round 13
- **Logic:** The first run (Round 0) will rebuild the cache; subsequent runs will benefit from the cached profiling but update the visualizations for their specific round context.

### 3. Verification & Validation
- **Automated Check:** Confirm that directories `R0` through `R13` exist in `ROUND_IMAGES_UPDATE/2026/`.
- **Visual Spot-Check:** Verify that `TIPS_RESULTS.png` exists for completed rounds and `TIPS.png` exists for the latest rounds.
- **Data Integrity:** Check that `ladder.png` in R13 reflects the state after 13 rounds of play.

## Success Criteria
- All 14 round directories (R0-R13) are populated with their respective Desktop and Mobile subfolders.
- ELO ratings in the visualizations reflect a continuous progression from the start of the season.
- No "stale" images from previous partial runs remain.
