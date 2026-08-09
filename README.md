# FootyRecord Strategic Prediction Engine

The FootyRecord Tactical Prediction Engine models ball movement in Australian Rules Football (AFL) as directed edges (vectors) on a discrete 5x3 spatial grid. By translating continuous tracking data into historical transition matrices, the engine computes team matchup deltas, optimizes mathematical prediction strategies, integrates historical ELO ratings, and outputs rich presentation-ready graphics.

---

## Project Structure & Layout

The project root is organized into clean, modular directories:

```
├── Core/               # The architectural and model layer
│   ├── base_visualizer.py      # Base visualization configurations and fallback logic
│   ├── config.py               # Global engine parameters and settings
│   ├── elo_engine.py           # ELO calculations, regression, and lookup engine
│   ├── engine_core.py          # Directed Graph and Matchup Delta calculations
│   ├── engine_data.py          # Data ingestion, profiling, and caching logic
│   ├── engine_scraper.py       # Threaded scraper for play-by-play/spatial data
│   ├── field_visualizer.py     # AFL oval pitch and grid node drawing
│   ├── mappings.py             # Team definitions, abbreviations, and color profiles
│   ├── models.py               # Dataclasses (MatchInfo, TransitionEdge, Coordinate, etc.)
│   ├── theme.py                # Visual styling, palettes, and typography
│   ├── vector_renderer.py      # Scaling, blur, and styling of flow arrows
│   ├── visualize_ladder.py     # Cumulative ladder and team journey chart renderer
│   ├── visualize_matchup.py    # Matchup expectations and actual flow renderer
│   ├── visualize_story.py      # Variance mapping and player performance bar renderer
│   └── visualize_tips.py       # Tips card visualizer
├── CSV_DATA/           # Normalized play-by-play tracking data files (2021-2026)
├── Experiments/        # Experimental testing scripts for ELO, decay, and windows
├── LegacyScripts/      # Obsolete patching, injection, and utility scripts
├── PLANNING/           # Project planning and research reports
├── ROUND_IMAGES_UPDATE/# Directory containing generated visualizer output graphics
├── index.html          # Web-based interface frontend
├── server.py           # Interactive local simulation web server
├── requirements.txt    # Python package dependencies
└── README.md           # Project documentation
```

---

## Core Entry Points

### 1. Production Pipeline
*   **[generate_round_images.py](file:///d:/Development/Projects/FootyRecord/generate_round_images.py)**: Renders matchup deltas, expectation-vs-actual diagrams, player performance bars, tipping summaries, seasonal cumulative ladders, and team journeys for a selected round. Output images are structured into Desktop and Mobile format subdirectories.
    ```bash
    python generate_round_images.py --round 2 --comp_id 2026014
    ```

### 2. Game Predictor
*   **[predict_game.py](file:///d:/Development/Projects/FootyRecord/predict_game.py)**: Fetches live match fixture details, calculates expectations, and lists key player drivers/win conditions driving prediction results for both teams.
    ```bash
    python predict_game.py <round_num> <game_num>
    ```

### 3. Simulation Web Server
*   **[server.py](file:///d:/Development/Projects/FootyRecord/server.py)**: Starts a local HTTP server hosting an interactive dashboard for AFL match simulation.
    *   **Port**: `8000` (Visit: `http://localhost:8000`)
    ```bash
    python server.py
    ```

### 4. Backtesting & Analysis
*   **[backtest_2025.py](file:///d:/Development/Projects/FootyRecord/backtest_2025.py)**: Evaluates the ELO model predictions over the entire 2025 AFL season, detailing round-by-round accuracy.
    ```bash
    python backtest_2025.py
    ```
*   **[backtest_2026.py](file:///d:/Development/Projects/FootyRecord/backtest_2026.py)**: Evaluates the model predictions over the active 2026 AFL season.
    ```bash
    python backtest_2026.py
    ```
*   **[analyze_margins.py](file:///d:/Development/Projects/FootyRecord/analyze_margins.py)**: Performs statistical regression comparing expected delta values against actual margins for the 2024-2025 seasons.
    ```bash
    python analyze_margins.py
    ```
*   **[analyze_wce_nm.py](file:///d:/Development/Projects/FootyRecord/analyze_wce_nm.py)**: Evaluates individual matches (e.g. West Coast vs North Melbourne) comparing pre-match expectations against final actual play-by-play tactical outputs.
    ```bash
    python analyze_wce_nm.py
    ```

---

## Setup & Dependencies

Ensure you have Python installed, then install the package requirements:
```bash
pip install -r requirements.txt
```
To run visualizers with the official stencil look, place font files (e.g., `Wallpoet`, `Roboto`) in the `downloaded_fonts/` directory. If not present, the visualization engine will seamlessly fall back to system fonts without failing.
