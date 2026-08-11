# Plan: one store — SQLite replaces the pickle cache

**Status: draft for review (2026-08-11)**
**Goal:** one database for the engine's working state AND its results. The
pickle cache (`CSV_DATA/.cache/ingestor_state.pkl`), the CACHE_VERSION dance,
and the dual-store split all die.

---

## Today's two stores

| Store | Contents | Role |
|---|---|---|
| `~/footyrecord-results/footyrecord.db` | predictions, calibration_log, delta matrices | results (truth) |
| `CSV_DATA/.cache/ingestor_state.pkl` | raw chains, per-position matrices, match_performance, Elo history, actual matrices, player histories, calibration | engine state (speed) |

## Target: one DB (`~/footyrecord-results/footyrecord.db`, extended)

| Table | Contents | Size estimate |
|---|---|---|
| `matches` | m_id, season, round, home, away, scores | 1.2k rows |
| `chains` | raw chain events (m_id, chain, seq, grid, player, team, outcome) | ~1.5M rows |
| `match_positions` | per-(match, team) position buckets as JSON blobs | ~2.4k blobs × 10-50KB |
| `match_performance` | expected, expected_delta (JSON), actual | 1.2k rows |
| `elo_history` | team, m_id, elo | ~25k rows |
| `actual_matrices` | per-(match, team) matrix JSON | 2.4k blobs |
| `player_history` | team, m_id, player, edge, weight | ~100k rows |
| `calibration` | current state row (decay, margin, total, divisor, tiers, window) | 1 row |
| `calibration_log` | per-round provenance (already exists) | 144 rows |
| `predictions` | per-game results + deltas (already exists) | 1.2k rows |
| `meta` | schema_version, fingerprint, built_at — **replaces CACHE_VERSION** | 1 row |

## Design decisions

1. **`meta.fingerprint` replaces CACHE_VERSION** — same staleness guard, no
   version-constant bumping; rebuilds when the fingerprint string changes.
2. **Rebuild = one transaction** — crash-safe (the pickle today can be
   half-written on a power cut; SQLite commits atomically).
3. **Raw chains in the DB** — the CSV ingestion writes chains once; profiling
   reads from SQLite. CSVs remain the *source format*, DB the *working store*.
4. **Position buckets as JSON blobs** — 2.4k blobs beat 1.5M edge rows for
   load speed; SQLite handles multi-MB blobs fine.
5. **Load path**: `DataIngestor.load_all_data()` reads SQLite → reconstructs
   in-memory structures exactly as today. Expect load ~2-3× slower than pickle
   (seconds, not minutes) — the profile BUILD (8 min) is unchanged.
6. **Determinism**: builds on the sorted-delta fix — byte-identical rebuilds
   (being verified right now with the two-seed test).
7. **DB stays local** — the SMB lock issue makes a NAS-hosted DB impossible;
   this is already where the results DB lives.

## Phases

1. **Schema + migration script** — dump the pickle, import into SQLite, parity
   check (load both stores, compare match_performance + a sample of matrices
   byte-for-byte). ~45 min
2. **Swap DataIngestor read/write paths** — pickle → SQLite; CACHE_VERSION →
   `meta`; update tests that touch the cache path. ~45 min
3. **Verify end-to-end** — fresh rebuild from CSVs into SQLite, evaluate
   --save, render one round, byte-compare a card against the pre-migration
   render. ~30 min
4. **Delete the pickle** + update docs (architecture.md, README). ~15 min

**Total: ~2-3 hours.** Risks: blob round-trip size (measure first), the load
path rewrite (contained in DataIngestor), test churn. The payoff: one file,
one schema, crash-safe rebuilds, no version-constant bookkeeping, and the
"what state made this result" question answers itself from one database.
