# Sharpness audit v0 (2026-07-24)

**Question.** Do dynamism.py's buckets mean what we claim — and what does
"sharpness" reliably mean at all?

**Literature.** Three operationalizations exist: (1) WDL-based sharpness
(Leela community: high min(win,loss) with low draw share — "how easy to
mess up"; needs a WDL head, unrecoverable from a single cp), (2)
Guid–Bratko complexity (eval-gap-weighted best-move changes across search
depth — "does calculation change the verdict"), (3) classical criteria
(compensation/initiative, opposite castling, forcing density — the
geometry dynamism already encodes). All three converge on "punishment of
the next mistake" as the target; our (fen, pvs, rolls) design measures it
from lines + geometry + human scatter, which is the closest computable
cousin of (1) without Leela.

**Gold standards** (audit_sharpness.py; 300 benchmark roots, 60/bucket,
production contract 4pv + K=16 Maia rolls; fresh Stockfish per position):
PUNISH = mean cp loss of alternatives 2..6 (MultiPV=6 @150k, clip 300);
BREADTH = # moves within 50cp; GB = depth-sweep best-move instability.

## Verdict: the bucket ladder is real

| bucket | n | mean punish | breadth | GB |
|---|---|---|---|---|
| DEAD | 60 | 30 | 5.4 | 5.5 |
| QUIET | 60 | 35 | 5.2 | 5.2 |
| DYNAMIC | 60 | 53 | 4.3 | 6.0 |
| SHARP | 60 | 118 | 2.6 | 5.5 |
| RAZOR | 60 | 208 | 1.7 | 2.6 |

Spearman(score, punish) = 0.72, (score, breadth) = −0.65. The buckets are
a validated punishment predictor. Caveats now measured, not vibes:

- **DEAD vs QUIET barely separate** (30 vs 35cp) — treat them as one
  speech register.
- **Sharpness ≠ complexity**: GB instability is slightly ANTI-correlated
  (−0.38; RAZOR has the LOWEST depth-instability — forced positions lock
  early). Never sell the bucket as "hard to calculate"; it is "punishing
  to misplay".
- 65/120 SHARP/RAZOR have best move = SEE>0 capture and are the MOST
  punishing (209 vs 108cp). Whether humans actually err there is a
  findability question (Maia unanimity → human-outcome data), parked as
  future work — narrowness is right to score them under the punishment
  definition.

## The one indicted component, fixed

Compensation fired on RAW material vs eval: 51 of 117 fires (44%) were
pending-recapture mirages that SEE-adjusted material closes. dynamism.py
now measures the gap against `material_stability(fen)["adjusted_cp"]` —
"real compensation is on the board" is only said when the gap survives
the captures. Re-scored on the stored gold (recheck.py): 45/300
re-bucketed (mirages demoted from SHARP/RAZOR), ladder stays monotone
(30/37/77/143/192), spearman 0.72 → 0.66 — the small predictive dip is
the raw-gap's accidental proxying of unresolved tactics, which the
board-tension component already names truthfully. Claim-correctness wins
per the grounding contract. Mirror-invariance of the geometry legs: 0
mismatches in 120.

Everything else in dynamism.py audited clean (tension pairs, deep
passers, opposite castling, mobility asymmetry, forcing density, edge
guards). Smoke-tested under the tactics venv (backend-equivalent
imports).
