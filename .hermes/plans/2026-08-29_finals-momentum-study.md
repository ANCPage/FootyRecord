# Finals Momentum Study — Plan

**Question (Austin's):** does end-of-home-and-away momentum let a *lower-rated* team beat a
*higher-rated* team in finals, more often than the ratings alone predict?

**Status:** plan only — no code written, no model changes.

---

## What we have

| Asset | Coverage | Source |
|---|---|---|
| Finals results (winner + score) | **45 games, 2021–2025** (9/season) | Squiggle `is_final` |
| 2026 finals | 11 scheduled, **0 played** | Squiggle |
| End-of-H&A Elo rating per team | all 6 seasons | our record (R24) |
| End-of-H&A cumulative tactical score | all 6 seasons | our record |
| 5-round momentum at end of H&A | all 6 seasons | computed (already built) |
| Market price for finals | to verify | Squiggle Punters tips |
| **Finals chain data (tactical)** | **NONE — `MAX_ROUNDS = 24` excludes it** | would need re-scrape |

**Critical constraint:** our model has never seen a final. The record stops at R24 by design.
So we can test *whether pre-finals signals predict finals results*, but the model itself
cannot currently *predict* a final.

---

## The power problem — read this before choosing

45 finals total. The interesting subset — where rating and momentum **disagree** — will be
roughly 15–20 games. At n=18, a 12–6 split (67%) is about **1.4σ**: indistinguishable from
chance. **No design using only finals can reach significance.** Anyone claiming a finals
edge from 45 games is fitting noise.

This shapes the whole plan: we establish the effect where we have power (1,222 H&A games),
then ask whether finals are *consistent* with it. Finals become a **validation slice, not
the test**.

---

## Design

### Phase 1 — Establish the mechanism in H&A (high power, n≈550)
Already half-built from the momentum backtest. For every H&A match where quality and
momentum disagree (higher-rated team has worse recent form):
- how often does the momentum team win?
- what does rating-alone predict on those games?
- effect size + confidence interval

**Output:** a number with error bars — "when form contradicts rating, the form team wins
X% ± Y". This is the yardstick.

### Phase 2 — Describe the 45 finals against that yardstick
For each final, using **only end-of-H&A information** (no lookahead):
- rating gap (Elo), cumulative-tactical-score gap, real ladder gap
- momentum gap (5-round, and test 3/8 for sensitivity)
- who won; was it the higher-rated or the higher-momentum team
- home team (finals home is usually the higher seed — must be controlled)

**Output:** a 45-row table + the disagreement subset, compared against the Phase 1 rate.
Framed as *consistent / inconsistent with the H&A effect*, *never* as a significance claim.

### Phase 3 — Controls (the ones that usually kill this kind of finding)
1. **Home advantage** — finals home teams are higher seeds; momentum may just proxy seeding.
2. **Rating gap size** — the effect (if any) should only appear in close matchups; a
   momentum edge shouldn't beat a 100-point rating gap.
3. **Ladder vs rating** — our Elo disagrees with the real ladder (documented). Test both as
   the "quality" measure; if the finding flips depending on which, it's noise.
4. **Market comparison** — did the market already price the momentum? If the market's finals
   favourite beats our rating-based pick, momentum was public knowledge, not an edge.
5. **Survivorship** — later finals rounds only contain winners, so momentum "carries
   forward" mechanically. Test week 1 finals separately (n=20, cleanest slice).

### Phase 4 — Report
One summary + one 9:16 chart if the effect is visible. Written to the wiki with the power
caveat attached, whatever the result.

---

## Optional Phase 5 — ingest finals into the model (bigger, separate decision)

Raising `MAX_ROUNDS` to 28 and re-scraping 2021–2025 finals would give the model real
tactical data for ~45 games, so it could *predict* finals.

**Cost:** re-scrape (~3 min) + full rebuild (~4.5 min) + full re-render (~14 min).
**Consequence — this changes the model:** finals results would feed Elo history and the
calibration fit, so **the 66.5% record and every card would change.** The golden-record
test would fail by design, and we'd have to re-baseline.

**Recommendation: do NOT do this as part of the study.** Keep the H&A record as the stable
source of truth. If finals prediction is ever wanted, it should be a deliberate, separate
project with its own baseline.

---

## Effort

| Phase | Time |
|---|---|
| 1 — H&A mechanism | ~45 min (mostly built) |
| 2 — finals table | ~1 h (name mapping, joins) |
| 3 — controls | ~1 h |
| 4 — report + chart | ~45 min |
| **Total** | **~3.5 h**, analysis only, zero model risk |

---

## Questions for Austin

1. **Quality measure** — which is "the better team"? Our Elo rating, our cumulative tactical
   score, or the real ladder? (I'd run all three; if they disagree, that's the finding.)
2. **Momentum window** — 5 rounds was the accuracy sweet spot. Also test 3 and 8, or fix at 5?
3. **Scope** — full plan (Phases 1–4), or just Phase 2's descriptive finals table first
   (~1 h) to see whether the pattern is even visible before spending the rest?
4. **Confirm** — leave the model untouched (skip Phase 5)?

## What I expect to find (stated up front, so I can't retrofit)

Momentum will show a **small positive effect in close finals and nothing in mismatches**,
and it will **not survive the home-advantage control**. Reason: finals home teams are higher
seeds *and* tend to have better recent form, so the two are confounded by construction. My
honest prior is that the H&A momentum effect (+10pt in toss-ups, 1.5σ) is real but weak, and
45 finals cannot show it either way. The value here is a clean negative result with a
documented method — plus the finals table itself, which is interesting regardless.
