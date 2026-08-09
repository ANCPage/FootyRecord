# AFL Tactical Visualizer: Architectural Assessment

**Date:** April 2026
**Subject:** FootyRecord Strategic Prediction Engine (Core Module)

---

## 1. Executive Summary

The FootyRecord codebase employs a modular, pipeline-based architecture centered around a graph-theory approach to Australian Rules Football. By translating continuous spatial data into a discrete 5x3 tactical grid, the engine models ball movement as directed edges (vectors) between zones. 

The architecture successfully achieves a strong **Separation of Concerns**, dividing the system into four distinct layers: Acquisition, Ingestion, Core Logic, and Visualization. While the modularity is excellent and the data flow is highly traceable, there are notable opportunities to improve performance through caching, enhance type safety, and formalize configuration management.

---

## 2. Architectural Pipeline & Data Flow

The system follows a strict, unidirectional data flow:

### Layer 1: Data Acquisition (engine_scraper.py)
*   **Role:** Interfaces with the external AFL API to fetch raw play-by-play and spatial tracking data.
*   **Mechanism:** Uses concurrent threading (ThreadPoolExecutor) to download matches efficiently. It flattens deeply nested JSON payloads into normalized CSV files.
*   **Critique:** Robust. Decoupling the scraper from the core engine ensures that API changes only break the scraper, not the mathematical models. 

### Layer 2: Data Ingestion & Profiling (engine_data.py)
*   **Role:** Reads the flattened CSVs and transforms raw coordinates into the structural model.
*   **Mechanism:** The DataIngestor parses coordinates (x, y) and maps them to a normalized 5x3 grid (A1 to E3). It builds historical transition matrices for every team, applying an edge-based decay logic to weight recent performances higher.
*   **Critique:** This is the heaviest component. Currently, profile_all_teams() recalculates the entire historical graph in memory on every run. 

### Layer 3: Core Logic (engine_core.py)
*   **Role:** The mathematical brain of the engine.
*   **Mechanism:** Implements a pure Graph structure and a MatchupEngine. It compares two team matrices (Home vs. Away) and calculates the 'Delta' (the net tactical advantage) across all edges on the field.
*   **Critique:** Highly modular and pure. Because the MatchupEngine just takes two matrices and returns a delta matrix, it is incredibly easy to unit test and reason about.

### Layer 4: Visualization (engine_visualizer.py & isualize_*.py)
*   **Role:** Renders the tactical data into presentation-ready graphics.
*   **Mechanism:** Uses matplotlib to draw the oval, plot the grid nodes, and draw the weighted delta arrows. The V3 update centralized styling via 	heme.py and mappings.py.
*   **Critique:** Breaking the visualizers into specific classes (TipsVisualizer, MatchupVisualizer, etc.) prevents monolithic drawing functions. The integration of 	heme.py enforces a consistent design system across all outputs.

---

## 3. Critical Review & Recommendations

### A. Performance & Caching (High Priority)
*   **Issue:** The system rebuilds the entire team profiling history from CSV files every time a script like generate_round_images.py is executed.
*   **Recommendation:** Implement a persistent caching layer. The output of ingestor.get_team_average_matrix() should be serialized and stored (e.g., using pickle, SQLite, or Parquet) at the end of each round. The engine should only parse new matches and append them to the cached state, drastically reducing startup and generation times.

### B. Type Safety & Data Structures (Medium Priority)
*   **Issue:** The codebase heavily relies on complex, nested dictionaries to pass data between layers (e.g., passing Dict[str, Dict[Tuple[str, str], float]] for transition matrices). This makes it difficult for new developers to understand the shape of the data and increases the risk of KeyError exceptions.
*   **Recommendation:** Refactor the core data structures using Python dataclasses or pydantic models. Defining explicit models for TransitionEdge, TeamProfile, and MatchupDelta will self-document the code and allow IDE type-checkers to catch errors early.

### C. Configuration Management (Low Priority)
*   **Issue:** Magic numbers (like the decay factor of 0.9, the sliding window size of 25, or grid boundaries) and hardcoded paths are scattered across the files.
*   **Recommendation:** Consolidate all constants, hyper-parameters for the mathematical model, and directory paths into config.py. The main.py orchestrator or the individual engines should load these parameters on initialization.

### D. Error Handling & State Recovery
*   **Issue:** The main orchestration scripts are somewhat optimistic. If a CSV file is missing or corrupted, or if the API returns an unexpected status for a single game, the pipeline might crash midway through generating a round.
*   **Recommendation:** Implement more robust 	ry/except blocks around the ingestion loop. If a game fails to parse, it should be logged as an error, but the engine should seamlessly continue profiling the remaining games.

---

## 4. Conclusion
The FootyRecord engine is a well-architected piece of software. The decision to model a dynamic sport as a discrete, directed graph is highly effective. By addressing the caching bottleneck and formalizing the data structures, the codebase will be fully prepared to scale to thousands of historic matches and support real-time, live-game predictive modeling.
