# Known Quirks

Small, deliberate, documented behaviours that look like bugs but aren't — or
that carry a watch note for a future decision.

## Zone mirror (L/R orientation) — leave as-is, watch note

**Finding (2026-08-09, LFP→FB investigation):** the data vendor's x-axis
(forward/backward) was verified against real play; the y-axis (left/right
mirroring) could not be verified against any ground truth. The pipeline is
internally consistent (team-relative frame, single rotation source since the
geometry consolidation), the labels are cosmetic, and the orientation is
**prediction-neutral** — net deltas, winner picks and margins are unaffected
by a global mirror.

**Watch note:** if a future feature ever needs real-world left/right accuracy
(e.g., "attacks down the left wing" meant literally), verify the y-axis
against a single known play before trusting it. One known-good play is
sufficient — the consistency is already proven.
