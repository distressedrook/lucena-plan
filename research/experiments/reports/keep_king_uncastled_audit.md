# keep_king_uncastled — audit report (2026-07-23)

The vocabulary's first NEGATIVE-event plan (user-defined: surfaces when the
center is locked; engine rule: the king isn't castled in the next 6 moves).
Audited by `studies/keep_king_uncastled_audit.py` — full GM corpus (33,769
games) + banked benchmark shards (zero new engine calls).

## Trigger

`closed_v0.center_locked` (>= 2 central rams on c–f, zero central tension)
AND the side has not castled AND still holds a castling right (no right =
holding is forced, not a plan; excluded).

## Results

**Leg 1 — corpus hold-rate (2,079 triggered anchors):**
GM holds 12 plies 57.8% · seeded-random holds 92.2% · **lift 0.63**.
Expected inversion: not-castling is what random play does; naive lift cannot
carry a negative event either way.

**Leg 2 — outcome (the decision leg): mildly ANTI.**
Held 0.458 (n=1,202) vs castled-anyway 0.495 (n=877); negative both sides
(W −0.041, B −0.029). Blanket "keep it home when the center is locked" is
not corpus-supported — GMs with a live right who castle anyway do slightly
better.

**Leg 3 — engine lines (banked, 102 triggered benchmark positions):**
EVERY eval-equal PV holds (the verify contract) in 38/127 = **29.9%** of
side-cases; actual GM continuations hold 49.6%. The plan is real
per-position, on the engine's say-so only.

## Ruling encoded in code

- **Engine-contract ONLY.** MAIA-TYPICAL removed as a passing verdict for
  this family (`verify.py`): humans/rollouts hold constantly while scoring
  worse, so human typicality is meaningless for a negative event. Verdicts:
  CONFIRMED-SOUND / NOT-IN-BEST-LINES / UNSUPPORTED. Maia frac still
  reported as data (`typical` forced False).
- Never surfaced unverified (standard engine-contract tier). Tier
  precedents: `deny_castling` (audited, engine-gated), `backward_push`
  ("bare rule is random-typical; NEVER surface unverified").
