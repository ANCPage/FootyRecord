# FootyRecord — How It Works (Layperson's Guide)

**One-line version:** FootyRecord reads every possession of every AFL match since 2021, draws a "tactical fingerprint" for each team, compares two fingerprints to predict who wins, and turns the whole thing into pretty pictures.

---

## 1. The raw material

For every match, the system scrapes the league's detailed stats feed: each disposal, possession and score, with *where on the oval it happened* (x/y coordinates) and *when in the match*.

That's about 4.3 million stat events across six seasons (2021–2026). A season's worth of raw events is roughly the size of a small book — the computer's job is to turn that pile of pages into one clear picture.

## 2. Scoring chains — the sentences

The events are stitched together into **scoring chains**: a sequence of possessions that ends in a goal or behind (e.g. back pocket → wing → forward pocket → goal).

By design, only chains that end in a score are profiled. That's a deliberate choice, not a shortcut: scoring chains are where a team's *intent* is clearest. The trade-off is that the system is blind to pressure — a team that wins by smothering the opposition rather than by building pretty chains won't impress it.

## 3. The 15-zone grid — the map

The oval is cut into a 5×3 grid of zones, named like a footy position chart:

- **A column** = the back line (full-back, pockets)
- **C column** = the centre (wings, centre)
- **E column** = the forward line (full-forward, pockets)
- Goals sit at each end.

Every stat event is dropped into its zone. Because each team's data is kept in *its own* frame — the goal they're attacking is always "forward" — the same grid describes both teams fairly.

## 4. The fingerprint — a team's tactical shape

For each team, all their scoring chains are merged into a **transition map**: which zones the ball flows through, and how strongly. Recent matches count more than old ones (decay weighting), and each match's map is normalised so that a team with lots of scoring chains doesn't dominate one with fewer.

The result is a *shape*, not a volume: "this team funnels the ball up the right wing and finishes through the forward pocket" — not "this team scores a lot". That was a specific fix in the latest round of work: volume used to leak into the comparisons and masquerade as efficiency.

## 5. Team ratings — the Elo

Each team carries an Elo rating, like chess. The twist: the rating is trained on **the model's own judgement of dominance**, not the scoreboard. A team that *looked* more dangerous all night gets the points even if it lost by a kick. This was a deliberate design decision — the rating measures "model-measured dominance", not luck.

Ratings drift back toward average between seasons, so a great 2021 doesn't prop up a 2026 side.

## 6. The matchup — two fingerprints, one answer

To predict a game, the system subtracts one team's map from the other's. The result is a **delta**: "team A attacks through zones where team B is weak" reads as a positive number; the reverse reads negative. That number, blended with the Elo gap, feeds a probability.

One quirk: the "home team" label in AFL is unreliable (shared grounds, neutral games), so the system deliberately gives no venue advantage — it treats the two teams purely on their football.

## 7. Honest numbers

Walk-forward evaluation over 1,181 matches (each match predicted using only data from before it):

- **Winner accuracy:** ~65.5%
- **Brier score (probability quality):** 0.214 — better than the 0.25 "no opinion" baseline
- **Margin error:** ~27 points on average

2026 season-to-date sits around **69%**. One bad round (44% in R22, where five upsets landed, including Norf beating the Dogs — a classic pressure-game win the model can't see) drags it down from where it was.

## 8. What comes out the other end

For every round, the system produces:

- **Matchup cards** — arrows on a pitch showing where each team attacks (and where the matchup is won/lost)
- **Tips results** — the model's picks vs what actually happened, with a running season score
- **Ladder & team journeys** — Elo ratings, tiers and form over time

## 9. Engineering health (the boring-but-important part)

The latest work round professionalised the codebase:

- The grid maths lives in **one place** now — previously there were seven copies, and one of them was subtly wrong, which caused a rendering bug where arrows pointed at the wrong zones (a forward-pocket arrow drawn from full-back). One source of truth fixed the whole bug class.
- **37 automated tests** guard the maths (rotation, tie-breaking, data ingestion, scraping).
- Everything is in git with CI; the evaluation harness reports honest, reproducible numbers.

---

*Written August 2026, after the audit-driven cleanup: fresh data, normalised matrices, fitted calibration, single geometry module, full test suite.*
