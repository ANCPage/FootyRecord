# Player-goals odds: what is actually obtainable (verified 2026-09-14)

Gate C needs **real prices for player-goals markets**. This is what exists, what
was probed, and what it would cost to answer the gate.

## 1. Betfair AU exchange — NO player-scoring markets for AFL (probed)

Verified by `Core/tools/odds_fetch.py probe` against the live AU exchange
(certificate login, eventType 61420 "Australian Rules"):

- **111 AFL markets** in the following 21 days, and **not one player-scoring
  market**. Market types returned: `WINNER` (72 — Brownlow-style awards),
  `UNUSED` (18), `WINNING_MARGIN` (8), `MATCH_ODDS` (2), `HANDICAP` (2),
  `TOTAL_MATCH_POINTS` (2), `HALF_TIME_FULL_TIME` (2), `UNDIFFERENTIATED` (2),
  `COMBINED_TOTAL` (2), `TO_REACH_FINAL` (1).
- Searched for `PLAYER_GOALS`, `TO_KICK`, `GOALS`, `PLAYER_SCORE`: **none present**.
- So the exchange — the only AU venue with an official API — cannot price, or
  therefore test, AFL player goals. The live fixtures do confirm the model's
  projected preliminary finals are the real ones (Sydney v Fremantle, Hawthorn v
  Brisbane are on the exchange this week).

Betfair's *Historic Data* product would not change this: it replays the markets
the exchange actually ran, and player goals were never among them.

## 2. The Odds API (the-odds-api.com) — the only viable path

Per their docs, AFL (`aussierules_afl`) is covered with AU books, and the
player-scoring markets are named explicitly:

- `player_goal_scorer_anytime` — Anytime Goal Scorer (Yes/No)
- `player_goals_scored_over` — Goals Scored **Over/Under** lines

Access is via the event-odds endpoint (one event per call):

```
GET https://api.the-odds-api.com/v4/sports/aussierules_afl/events/{eventId}/odds
      ?regions=au&markets=player_goal_scorer_anytime,player_goals_scored_over
      &oddsFormat=decimal&apiKey=KEY
```

- **Cost:** credits = markets x regions. Two markets, one region = 2 credits per event.
  Free tier = 500 credits/month: enough to *verify coverage* for a round, not to backtest.
- **History:** paid plans only. Featured markets (h2h/handicap/totals) back to mid-2020;
  **other markets (player props) from mid-2023** — which covers seasons 2024, 2025 and 2026,
  roughly 550 games and a very large number of player-market quotes.
- **Coverage caveat, in their own words:** "Coverage of player props is mainly limited to
  US sports and US bookmakers at this time", while the AFL page lists AFL player props for
  AU books. This discrepancy must be resolved with a live call before any plan is bought —
  the free tier is enough for that probe.

## 3. Corporate bookmakers (Sportsbet, TAB, Ladbrokes, Neds, PointsBet)

No official API, and reverse-engineered mobile endpoints breach their terms. Out.

## What this means for Gate C

Gate C **cannot be answered today**: no free or already-licensed source provides
historical AFL player-goals prices, and the exchange does not run the market at all.

Two honest routes:

1. **Buy a test.** One month of The Odds API at a paid tier (history from mid-2023)
   answers Gate C on ~3 seasons. Do the free-tier probe first to confirm AFL props
   are actually returned for AU books; if they are not, the money is not worth spending.
2. **Forward capture.** If a key exists (free tier is sufficient for current-round
   props), poll the event-odds endpoint for each game and store timestamped snapshots
   with `Core/tools/odds_fetch.py snapshot`-style storage. Prices can then be compared
   with the model in the 2027 season — slower, but free and unambiguous.

Either way, **Gate C remains open and unproven**. Nothing in this repository should be
read as evidence that the model beats a bookmaker's price.

## Status of the gate chain

| Gate | Tests | Status |
|---|---|---|
| A | beats the player's own average (odds error, 1+ and 2+) | **pass** — 0.1975 vs 0.2236 (1+), 0.0917 vs 0.1015 (2+), 2025-26 out-of-sample |
| B | allocation vs the player's own share of team goals, same team total | **pass** — 70.5% vs 67.6% head-to-head |
| A2 | advantage grows with matchup leverage (fit ≤2024, test 2025-26) | **pass** — slope +0.061 [+0.042,+0.080] (2025), +0.068 [+0.044,+0.092] (2026); quartiles rise monotonically |
| C | beats the market | **blocked** — no source for AFL player-goals prices (see above) |
