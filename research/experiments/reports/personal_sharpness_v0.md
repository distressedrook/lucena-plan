# Personal sharpness v0 — "sharp for you" (2026-07-24)

**The concept.** Objective dynamism prices the position's punishment of a
mistake; personal sharpness prices the punishment of the move a player of
rating L would ACTUALLY play:

    danger_L    = Σ_m P_L(m|fen) · loss(m)        (expected cp loss at L)
    trap_mass_L = Σ_m P_L(m|fen) · 1[loss ≥ 100]  (P your level blunders)
    trap_move_L = the highest-probability losing move (speakable)

P_L = Maia policy head read directly (rating-conditioned, ~25ms/level, no
rollouts — the policy IS the distribution K-sampling would estimate);
loss = engine child evals of the top-6 policy moves (union across levels,
~8-12 probes @60k nodes/position). As L→∞ the policy concentrates on
engine-equal moves, so danger_L→0 except where the position is genuinely
hard: sharp-for-you IS the per-position policy-vs-engine gap.

**Implementation.** `src/personal_sharpness.py` — pure check per the
house contract (caller supplies policy rows + child evals; the module
never rolls). `sharpness_profile()` = the metric across levels + the
dangerous-for read. No mirror-invariance claimed: Maia is deliberately
color-asymmetric.

## Study (300 audited roots, levels 1300/1800/2400, legs banked)

| elo | mean danger | mean trap_mass | TRAP | SLIPPERY | SAFE |
|---|---|---|---|---|---|
| 1300 | 53.9 | 0.173 | 73 | 108 | 119 |
| 1800 | 43.6 | 0.133 | 57 | 91 | 152 |
| 2400 | 34.1 | 0.094 | 38 | 71 | 191 |

- **Internal validity: 89% monotone easing** — danger falls with rating
  in 268/300 positions, as the concept demands.
- **It is genuinely a second axis**: spearman(danger_L, objective
  punishment) ≈ 0.05 — near-orthogonal to the validated dynamism gold.
  TRAP@1300 positions spread across ALL objective buckets (9 in DEAD, 8
  in QUIET, 19 in DYNAMIC, 19 SHARP, 18 RAZOR). "Sharp" and "sharp for
  you" measure different things, empirically.
- **The gold cell exists and is real**: 36/300 positions are objectively
  calm-to-dynamic yet TRAP at 1300 (>25% of policy mass loses ≥100cp).
  All 8 spot-checked trap moves CONFIRMED at 400k nodes (claimed losses
  within ±30cp). Example: a DYNAMIC position where 51% of 1300-policy
  mass plays Nxd5, losing 185cp — invisible to every engine-only metric,
  and exactly the sentence a coach wants: "at your level the natural
  Nxd5 is the losing move here."

## Status + calibration debt

Buckets (TRAP ≥0.25 trap_mass / SLIPPERY ≥0.10 or danger ≥40 / SAFE) are
PRIOR thresholds — provisional, data-tier, not speakable yet. The
graduation gate is the external leg: predicted trap_mass vs OBSERVED
blunder rate in rating-banded human games (open Lichess database, bands
around 1300/1800) on flagged positions/moves. Maia's calibration is the
bet; the reliability curve sets the spoken thresholds. Until then the
profile is data the coach may use for emphasis, not a claim it recites.

Depth-2+ traps (poison revealed only at ply 3+) are v1: walk the banked
K=16 rollouts a few plies and engine-label endpoints — the same
expectation at a horizon, replayable from the shards without new Maia
calls. Tie-in: trap_move_L is the poisoned-line concept conditioned on
level; the tactics layer's detector can supply the WHY once the policy
supplies the WHICH.

Legs banked: `studies/personal_sharpness/bank.jsonl` (policy@3 levels +
child evals, 300 positions) — re-scorable under any future thresholds.
