# Regenerate 2026 Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reset and regenerate all visual assets for the 2026 AFL season (R0-R13) using the latest data.

**Architecture:** 
1. Clean environment by removing stale images and model cache.
2. Execute the existing generation script in a loop for each round.
3. Validate output directory structure and asset presence.

**Tech Stack:** Python 3, PowerShell.

---

### Task 1: Environment Cleanup

**Files:**
- Modify: `ROUND_IMAGES_UPDATE/2026/` (Delete contents)
- Modify: `CSV_DATA/.cache/ingestor_state.pkl` (Delete)

- [ ] **Step 1: Remove existing round directories**

Run: `powershell -Command "Get-ChildItem -Path ROUND_IMAGES_UPDATE/2026 -Directory | Remove-Item -Recurse -Force"`

- [ ] **Step 2: Remove model cache**

Run: `powershell -Command "Remove-Item -Path CSV_DATA/.cache/ingestor_state.pkl -Force"`

- [ ] **Step 3: Verify cleanup**

Run: `powershell -Command "ls ROUND_IMAGES_UPDATE/2026; ls CSV_DATA/.cache/"`
Expected: `ROUND_IMAGES_UPDATE/2026` should be empty or non-existent. `ingestor_state.pkl` should be gone.

### Task 2: Batch Generation (R0-R13)

**Files:**
- Execute: `generate_round_images.py`

- [ ] **Step 1: Run generation for all rounds**

Run: 
```powershell
0..13 | ForEach-Object { 
    Write-Host "--- Generating Round $_ ---"; 
    python generate_round_images.py --round $_ 
}
```

- [ ] **Step 2: Monitor for errors**

Check the console output for any "Error processing" or Traceback messages.

### Task 3: Output Validation

- [ ] **Step 1: Check directory structure**

Run: `powershell -Command "Get-ChildItem -Path ROUND_IMAGES_UPDATE/2026 -Directory | Select-Object Name"`
Expected: List of folders R0 through R13.

- [ ] **Step 2: Spot check latest round assets**

Run: `powershell -Command "ls ROUND_IMAGES_UPDATE/2026/R13/Desktop; ls ROUND_IMAGES_UPDATE/2026/R13/Mobile/InstaPost"`
Expected: Multiple PNG files including `ladder.png`, `TIPS.png`, and game-specific folders.
