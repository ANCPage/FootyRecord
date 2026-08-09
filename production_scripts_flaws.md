# FootyRecord Production Scripts: Flaw & Defect Analysis Report

> **STATUS (2026-08-09): historical document.** Most items below are resolved
> in the current codebase; several were misdiagnoses. See
> `code_audit_2026-08.md` for the authoritative audit trail with per-item
> FIXED / CLOSED / kept-by-design status.

This report compiles the findings from in-depth analyses of the FootyRecord production scripts, including the orchestration scripts (`generate_round_images.py`, `Core/main.py`) and the visualization engines (`Core/visualize_*.py`). The issues are categorized by type, highlighting their locations, impact, and concrete recommendations for resolution.

---

## 1. Critical Logical & Data Bugs

### A. Roster & Player Name Fetching Omission (Empty Names on Graphics)
* **Location:** [generate_round_images.py:L20-48](file:///d:/Development/Projects/FootyRecord/generate_round_images.py#L20-48), [L87](file:///d:/Development/Projects/FootyRecord/generate_round_images.py#L87), [L130-136](file:///d:/Development/Projects/FootyRecord/generate_round_images.py#L130-136), [L172](file:///d:/Development/Projects/FootyRecord/generate_round_images.py#L172), [L178](file:///d:/Development/Projects/FootyRecord/generate_round_images.py#L178), [L202](file:///d:/Development/Projects/FootyRecord/generate_round_images.py#L202)
* **Problem:** The authentication function `get_token()` and data-fetching helper `fetch_match_data()` are defined but **never called** in `generate_round_images.py`. Roster data (`r_data`) is initialized as a static empty dictionary `{}` at line 87.
* **Impact:** 
  1. The dictionary `player_names` remains empty.
  2. Driver annotations on the variance maps display raw player IDs (e.g., `CD_I1001234`) instead of readable player names.
  3. The player performance visualization displays empty names (only raw IDs) on the bars.
* **Recommendation:**
  * Initialize the API token at the start of the script: `token = get_token()`.
  * Within the game iteration loop, fetch the roster data: `r_data = fetch_match_data(mid, token) if token else {}`.

### B. ELO Inter-Season Reset (Loss of Historical Carry-Over)
* **Location:** [Core/engine_data.py:L123-125](file:///d:/Development/Projects/FootyRecord/Core/engine_data.py#L123-125)
* **Problem:** In `profile_all_teams()`, when the loop processes a match belonging to a new season, it clears the ratings dictionary:
  ```python
  if info.season != current_season:
      current_season = info.season
      ratings.clear()
  ```
* **Impact:** All teams are reset back to the baseline ELO of `1500.0` at the start of every season. This wipes out historical carry-over, meaning early-season ELO ratings are highly inaccurate (e.g., the reigning premier and the wooden-spoon team are treated identically).
* **Recommendation:** Carry ELO ratings over between seasons instead of wiping them. Apply a standard regression to the mean:
  ```python
  if info.season != current_season:
      current_season = info.season
      for team in list(ratings.keys()):
          ratings[team] = 1500.0 + (ratings[team] - 1500.0) * 0.75
  ```

### C. ELO Query Season-Locking Bug
* **Location:** [Core/engine_data.py:L263-276](file:///d:/Development/Projects/FootyRecord/Core/engine_data.py#L263-276)
* **Problem:** The method `get_team_elo()` filters historical ratings strictly within the *requested* season:
  ```python
  if info.season == season:
      last_elo = elo
  ```
* **Impact:** In early rounds of a new season (e.g., Round 1), before any matches have been recorded in the current season, the loop will skip all matches from the previous season and return the default `1500.0`. ELO is thus locked within seasons even if the reset bug in the profiler is fixed.
* **Recommendation:** Allow `last_elo` to update for any historical match that is chronologically prior to the requested target round:
  ```python
  for m_id, elo in history:
      info = self.match_info.get(m_id)
      if not info: continue
      if info.season > season: break
      if info.season == season and info.round >= round_num: break
      last_elo = elo # Unconditional update if match is prior
  ```

### D. Team Scores Double-Counting Vulnerability
* **Location:** [Core/engine_data.py:L80-90](file:///d:/Development/Projects/FootyRecord/Core/engine_data.py#L80-90)
* **Problem:** Goal and behind counts are processed to compute match scores *before* checking if the play-by-play row has already been seen and deduplicated:
  ```python
  if row.get('stat_description') == 'Goal':
      match_scores[m_id][row['stat_teamId']] += 6
  # ...
  stat_key = (row['chain_period'], row['stat_periodSeconds'], row['x'], row['y'], row['stat_playerId'])
  if stat_key in seen_stats: continue
  seen_stats.add(stat_key)
  ```
* **Impact:** If play-by-play rows contain duplicates (a common occurrence in raw spatial/event feeds), goals or behinds will be double-counted. This corrupts `actual_winners` and ELO calculations.
* **Recommendation:** Move the `seen_stats` deduplication check to the very beginning of the loop body.

### E. ELO Off-By-One-Round Tracking Bug
* **Location:** [Core/engine_data.py:L127-128](file:///d:/Development/Projects/FootyRecord/Core/engine_data.py#L127-128)
* **Problem:** `profile_all_teams()` appends ratings to `team_elo_history` *before* the match is processed:
  ```python
  self.team_elo_history[h_team].append((m_id, ratings[h_team]))
  ```
* **Impact:** The final updated ELO ratings after the last match of a season are never recorded. When querying ELO for the next round (or post-season visualizers), it returns outdated "before" ELOs, causing incorrect rankings on ladder and journey plots.
* **Recommendation:** At the end of the match loop or when a season boundaries transition occurs, record the final post-match ELO ratings.

---

## 2. Visual & Rendering Flaws

### A. Opponent Vector Direction & Scaling Visual Bug (Critical Visual Defect)
* **Location:** [Core/visualize_matchup.py:L82-85](file:///d:/Development/Projects/FootyRecord/Core/visualize_matchup.py#L82-85), [Core/visualize_story.py:L128-132](file:///d:/Development/Projects/FootyRecord/Core/visualize_story.py#L128-132)
* **Problem:** When `score < 0` (indicating the away team has the delta advantage), the visualizer attempts to draw the away team's transition.
  1. The code maps `target = 'AWAY_G'` if `end == 'SCORE'` and `score < 0` to point the arrow at the left goal.
  2. However, it **does not rotate the `start` node**, nor does it rotate any non-scoring target nodes.
* **Impact:**
  * For `E3 -> SCORE` with `score < 0`, the arrow is drawn from `E3` (right pocket) to `AWAY_G` (left goal), resulting in a field-spanning diagonal arrow that misrepresents a close-range shot as a field-length kick.
  * For non-scoring edges like `D2 -> E2` with `score < 0`, the arrow points to the **right** (toward Team A's goal), which makes it look like Team A is attacking, even though it represents Team B's advantage.
* **Recommendation:** When `score < 0`, rotate both the `start` and `target` nodes 180 degrees using the graph rotation helper, and map the goal target to `AWAY_G` (since Team B attacks left):
  ```python
  if score < 0:
      start = rotate_node(edge.source)
      target = rotate_node(edge.target)
      if target == 'SCORE': target = 'AWAY_G'
  ```

### B. Wallpoet Legibility Violations (Minimum Font Size)
* **Location:** [Core/visualize_ladder.py:L127](file:///d:/Development/Projects/FootyRecord/Core/visualize_ladder.py#L127), [L249](file:///d:/Development/Projects/FootyRecord/Core/visualize_ladder.py#L249), [L291-293](file:///d:/Development/Projects/FootyRecord/Core/visualize_ladder.py#L291-293), [Core/visualize_tips.py:L124](file:///d:/Development/Projects/FootyRecord/Core/visualize_tips.py#L124)
* **Problem:** **Wallpoet** is an aggressive, stencil-style font that becomes illegible at small sizes. The code comments denote size 8 is too small, yet:
  * Cumulative ladder labels use size `9` (desktop) and `8` (mobile).
  * Journey plot score labels use size `9` (desktop) and `7` (mobile).
  * Legend texts use size `10` (desktop) and `8` (mobile).
* **Impact:** Key texts on charts are blurred or unreadable.
* **Recommendation:** Enforce a minimum font size of `12` for Wallpoet. If a size below `12` is requested, automatically fall back to **Roboto-Regular** (`self.prop_body`).

### C. Desktop vs Mobile Branding Inconsistencies
* **Location:** [Core/visualize_tips.py:L58-60](file:///d:/Development/Projects/FootyRecord/Core/visualize_tips.py#L58-60)
* **Problem:** The script determines fonts dynamically:
  ```python
  sub_font = self.prop_sub if sub_fs >= 12 else self.prop_body
  ```
  Since `row_fs` is `12` on desktop but `11` on mobile, mobile visualizers fall back to Roboto for confidence grades and game numbers, whereas desktop renders them in Wallpoet.
* **Impact:** Inconsistent styling and brand identity between desktop and mobile versions of the same graphic.
* **Recommendation:** Standardize font choices explicitly or use a consistent size threshold that behaves identically on both aspect ratios.

### D. Results Card Text Overflow
* **Location:** [Core/visualize_tips.py:L114-131](file:///d:/Development/Projects/FootyRecord/Core/visualize_tips.py#L114#L131)
* **Problem:** The background `FancyBboxPatch` uses axis-relative coordinates (height `0.03`). Due to aspect ratio changes, this translates to `0.30"` height on desktop and `0.48"` on mobile, whereas text uses absolute point sizes (`11pt` and `8pt`).
* **Impact:** On desktop, the two lines of text occupy ~`0.264"`, which overflows the `0.30"` card boundary once padding is added, causing text clipping.
* **Recommendation:** Define bounding box dimensions in absolute points or scale them dynamically based on the figure's aspect ratio.

### E. Destructive Aspect Ratio Cropping via `bbox_inches='tight'`
* **Location:** [Core/visualize_story.py:L232](file:///d:/Development/Projects/FootyRecord/Core/visualize_story.py#L232)
* **Problem:** `draw_variance_map` saves the figure using `bbox_inches='tight'`.
* **Impact:** Matplotlib clips the margins dynamically based on text lengths, altering the image's aspect ratio and breaking the target `9:16` Reels or `9:12` Posts layouts.
* **Recommendation:** Use `plt.tight_layout()` or specify padding margins explicitly without using `bbox_inches='tight'`.

### F. Overlapping X-Axis Ticks on Mobile Journey Plot
* **Location:** [Core/visualize_ladder.py:L275](file:///d:/Development/Projects/FootyRecord/Core/visualize_ladder.py#L275)
* **Problem:** Plots 24 ticks horizontally without text rotation on a narrow mobile canvas (`9"` width).
* **Impact:** Labels overlap entirely, rendering the x-axis unreadable.
* **Recommendation:** Rotate x-axis labels (e.g., `rotation=45`) or only show every 2nd or 3rd tick on mobile screens.

---

## 3. Performance & Ingestion Bottlenecks

### A. Processing and Adding Non-Scoring Chains
* **Location:** [Core/engine_data.py:L158-170](file:///d:/Development/Projects/FootyRecord/Core/engine_data.py#L158-170)
* **Problem:** If a chain does not end in a score, the decay factor evaluates to `0.0`. The script still processes these chains, adds edges with `0.0` values, and updates player matrices.
* **Impact:** Around 65-70% of match chains are non-scoring (turnovers/stoppages). Profiling spends most of its CPU cycles processing useless zero-value edges.
* **Recommendation:** Add a short-circuit check at the beginning of the loop:
  ```python
  if not has_score:
      continue
  ```
  This will speed up data profiling by roughly 3x.

### B. Unused requests.Session Connection Pooling
* **Location:** [Core/engine_scraper.py:L39-40](file:///d:/Development/Projects/FootyRecord/Core/engine_scraper.py#L39-40), [L61](file:///d:/Development/Projects/FootyRecord/Core/engine_scraper.py#L61)
* **Problem:** The scraper creates `self._session = requests.Session()` but uses the global `requests.get` inside thread executions.
* **Impact:** Connection reuse is bypassed, forcing a new SSL handshake/TCP connection for every fetch. This slows down scraping and increases the rate-limiting footprint.
* **Recommendation:** Replace `requests.get(...)` with `self._session.get(...)`.

### C. Inefficient Cache Invalidation
* **Location:** [Core/engine_data.py:L54-56](file:///d:/Development/Projects/FootyRecord/Core/engine_data.py#L54-56)
* **Problem:** Invalidation checks if *all* files have mtimes older than the cache:
  ```python
  if all(os.path.getmtime(f) <= cache_mtime for f in files):
  ```
* **Impact:** If one file (like the active season's CSV) changes, the cache is completely invalidated, forcing a full rebuild of static past seasons (2021-2025).
* **Recommendation:** Implement incremental caching or only re-process the active season's data.

---

## 4. Architectural & Configuration Issues

### A. Hardcoded Development Paths & Configuration Time-Bombs
* **Location:** [Core/config.py:L44-45](file:///d:/Development/Projects/FootyRecord/Core/config.py#L44-45), [Core/engine_data.py:L51](file:///d:/Development/Projects/FootyRecord/Core/engine_data.py#L51)
* **Problem:** `RAW_DIR` is set to a hardcoded local developer directory (`C:\Users\austin.page\Documents...`). `SEASONS` is a hardcoded list up to `2026`.
* **Impact:** Running the scripts on another machine causes a crash. When the year transitions to 2027+, the system will silently ignore new data.
* **Recommendation:** Resolve paths dynamically relative to `PROJECT_ROOT`, glob files using regex like `flattened_stats_(\d{4}).csv`, and generate the seasons list dynamically up to the current calendar year.

### B. Matplotlib Figure & Handle Memory Leaks
* **Location:** [Core/visualize_matchup.py](file:///d:/Development/Projects/FootyRecord/Core/visualize_matchup.py), [Core/visualize_story.py](file:///d:/Development/Projects/FootyRecord/Core/visualize_story.py), [Core/visualize_ladder.py](file:///d:/Development/Projects/FootyRecord/Core/visualize_ladder.py), [Core/visualize_tips.py](file:///d:/Development/Projects/FootyRecord/Core/visualize_tips.py)
* **Problem:** `plt.close(fig)` is called at the end of the plotting functions, but none of the code is wrapped in `try...finally` blocks.
* **Impact:** If a rendering or data retrieval exception occurs mid-execution, the figure stays open in memory. During bulk round runs, this leaks memory and file handles, causing eventual crashes.
* **Recommendation:** Wrap visualizer functions in `try...finally` structures to guarantee figure closure, or run `plt.close('all')` at the loop level in `generate_round_images.py`.

### C. Duplicated Code (DRY Violations)
* **Location:** `get_short_name` is duplicated in `visualize_ladder.py` (twice) and `visualize_tips.py`. Grid translation mapping is duplicate-defined in `engine_data.py` and `engine_scraper.py`.
* **Impact:** Harder to maintain; changes to pitch dimensions or team naming styles must be duplicated across files.
* **Recommendation:** Move team formatting and grid mapping helpers into [theme.py](file:///d:/Development/Projects/FootyRecord/Core/theme.py) and [config.py](file:///d:/Development/Projects/FootyRecord/Core/config.py) respectively.

### D. Unimplemented Command CLI Hooks
* **Location:** [Core/main.py:L18](file:///d:/Development/Projects/FootyRecord/Core/main.py#L18), [L35](file:///d:/Development/Projects/FootyRecord/Core/main.py#L35), [L67-69](file:///d:/Development/Projects/FootyRecord/Core/main.py#L67-69)
* **Problem:** Commands `evaluate` and `profile` exist in `main.py` CLI parser but are completely unimplemented (either `pass` or silent exit).
* **Recommendation:** Connect `evaluate` to backtesting scripts and implement basic summary outputs for `profile`.
