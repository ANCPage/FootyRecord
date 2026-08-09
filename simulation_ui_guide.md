# AFL Tactical Matchup Simulator: User Interface & API Guide

This document describes the dynamic matchup simulation web interface and its underlying Python server.

---

## 1. Quick Start Guide

To run the simulation dashboard locally, run the following command in your terminal:
```bash
python server.py
```
Then, open your web browser and navigate to:
**[http://localhost:8000](http://localhost:8000)**

---

## 2. Interface Features

*   **Interactive Team Selectors:** Choose any home (A) and away (B) team from the league. The dropdowns are populated dynamically with current ELO ratings.
*   **Custom ELO Overrides:** Want to simulate a matchup where Hawthorn's ELO drops by 100 points, or Adelaide is given a contender rating? Modify the numeric ELO inputs directly.
*   **Hyperparameter Sliders:**
    *   *Sliding Window:* Control how many historical games (5 to 50) are compiled into the averages.
    *   *Decay Factor:* Adjust how heavily recent plays are weighted (from 0.5 to 1.0).
    *   *ELO Weight:* Tune the influence of ELO difference relative to spatial vector delta (0.0 to 4.0).
*   **Dynamic Theming:** The predicted winner banner dynamically adjusts its background to match the winning team's primary color, blended with the vintage background to maintain design consistency.
*   **Clear Results:** Reset the sliders and custom ELOs back to their default profile settings, clearing all output graphs.

---

## 3. Server API Reference (`server.py`)

The backend is built using standard Python HTTP server modules (`http.server`):

1.  **`GET /`**: Serves the single-page application dashboard [index.html](file:///d:/Development/Projects/FootyRecord/index.html).
2.  **`GET /api/teams`**: Returns a list of all active teams in the database, sorted by their league ranking.
    *   *Response Format:*
        ```json
        [
          {
            "id": "CD_T80",
            "name": "Hawthorn",
            "primary": "#FBBF15",
            "secondary": "#4D2004",
            "elo": 1540.2,
            "tier": "CONTENDER",
            "rank": 2
          }
        ]
        ```
3.  **`POST /api/simulate`**: Receives custom parameters, re-profiles the historical dataset dynamically if the decay factor changed, calculates deltas, renders the matchup overlay to an in-memory buffer, and returns a Base64-encoded image string with stats.
    *   *Request Payload:*
        ```json
        {
          "team_a": "CD_T80",
          "team_b": "CD_T160",
          "window_size": 25,
          "decay_factor": 0.90,
          "elo_weight": 1.0,
          "custom_elo_a": 1540.0,
          "custom_elo_b": 1490.0
        }
        ```
    *   *Response payload:*
        ```json
        {
          "home_name": "Hawthorn",
          "away_name": "Sydney Swans",
          "winner_name": "Hawthorn",
          "winner_id": "CD_T80",
          "combined_score": 3.42,
          "net_delta": 2.92,
          "elo_diff": 0.50,
          "home_elo": 1540.0,
          "away_elo": 1490.0,
          "home_tier": "CONTENDER",
          "away_tier": "MID-TABLE",
          "home_rank": 2,
          "away_rank": 8,
          "image": "<base64_encoded_png_data>"
        }
        ```
