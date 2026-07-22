# lucena-plans

**Position → ranked plans, with evidence.** The positional-pedagogy layer of
[Lucena](../): given any chess position, suggest the long-term plans available
to each side — minority attacks, outpost campaigns, bad-bishop escapes,
freeing breaks — each backed by corpus statistics from GM play and verifiable
against engine lines. The tactical sibling explains *why a combination wins*;
this repo explains *what to do when nothing is hanging*.

Private and proprietary. Consumed by `lucena-backend`; the research corpus
and audit harness live in-repo but never ship.

## The idea

Plans are **geometry, not vibes**. Every plan in the vocabulary is a
*choreography theorem* — a deterministic, event-anchored rule over move
sequences (pawn traffic toward a lever, a knight's route to a hole, the
rook arriving on the opened file) — validated three ways before it may be
spoken:

1. **Corpus lift.** Detected in GM play far above a seeded-random floor
   (33,769 GM classical games + 311k elite online games). A plan that random
   lines execute at the GM rate is not a plan; several famous ones failed
   this bar and were retired (rook lifts, bind-and-squeeze, bare pawn storms
   without an intent gate).
2. **Outcome calibration.** The reliability numbers shown to a student are
   measured points-fractions, per structure family — never folklore.
3. **Per-position verification.** A suggested plan is confirmed only if it
   actually appears in an eval-equal engine line or in Maia rollouts *from
   this exact position* (the closed loop: suggest → roll → diff). Corpus
   priors rank candidates; they are never the admission ticket.

The LLM narrates last, from a fact sheet, and calculates nothing.

## The contract: `(fen, pvs, rolls)`

**No module in this library ever rolls an engine or Maia.** Every entry
point takes the position plus caller-supplied rolled lines:

```python
verify_plan(fen, side, family, pvs, rolls, ...)   # checks lines, never rolls
build_fact_sheet(fen, pvs, rolls)                  # prose sheet for LLM narration
suggest_verified(board, pvs, rolls)                # the closed loop, rendered
```

- `pvs` — engine MultiPV lines, `[{"cp": int, "ucis": [...]}, ...]`
  (eval-equal band ±50cp; one horizon-25/40 MultiPV=4 roll covers every
  family — verify truncates each family to its own natural horizon).
- `rolls` — K=9 Maia gated rollouts, each a list of UCI moves.
- Either may be `None` (that leg absent); verification degrades to the other
  leg and says so. Given the same lines, everything is deterministic.

Who produces the lines is the caller's business: the backend uses its own
in-process engine/Maia access; the research harness rolls live via
`research/experiments/tools/rolls.py` or replays the banked 4,000-position benchmark
shards with zero new engine calls.

## Layout

```
src/                     THE LIBRARY (only dep: python-chess)
  suggest.py               the front door: position → candidate plan menus
  verify.py                suggest → check rolled lines → graded verdict
  fact_sheet.py            natural-language fact sheet for LLM narration
  dynamism.py              deterministic sharpness rating (DEAD…RAZOR)
  plan_diff.py             the plan grammar: labels plans executed in a line
  detectors.py             whole-game plan detection (the labeling machine)
  weaknesses.py            fixed-target vocabulary (weak pawns, entombed
                           bishops, outposts, king exposure, knight routes…)
  structures.py            30 theory-structure recognizers (Carlsbad, isolani,
                           hedgehog…), ECO-validated
  closed_v0.py             pawn-skeleton / closedness geometry
  tension.py               pawn-tension analysis over rolled lines

docs/                    KNOWN_ISSUES.md (open, understood, not yet fixed)

research/                RESEARCH HARNESS (never shipped)
  research/experiments/tools/rolls.py   the ONLY live engine/Maia rolling in the repo
  research/experiments/studies/         corpus studies behind every calibrated number
  research/experiments/reports/         banked results (agreement tables, lift reports)
  research/gpu_benchmark/               the frozen 4,000-position benchmark kit
  data/                        GM + elite corpora, annotated ground truth
  minority-attack-gm/          the certified GM teaching set
```

## Quick start

```bash
# Candidate plans, pure geometry — instant, no engine anywhere:
./src/suggest.py "r1bq1rk1/pp2bppp/2n1pn2/2pp4/3P1B2/2P1PN2/PP1N1PPP/R2QKB1R w KQ - 0 8"

# The closed loop (research harness rolls live, then the library checks):
./src/suggest.py "<FEN>" --verify

# Bank a position's rolled lines once, reuse everywhere:
./research/experiments/tools/rolls.py "<FEN>" 25 > bank.json
./src/verify.py "<FEN>" W outpost_occupation bank.json
./src/fact_sheet.py "<FEN>" bank.json
```

As a library (how the backend consumes it):

```python
import chess
from suggest import build_menus
from verify import verify_plan
from fact_sheet import build_fact_sheet

pvs, rolls = my_engine_lines(fen), my_maia_rollouts(fen)   # caller's job
verdict = verify_plan(fen, "W", "weakness_harvest", pvs, rolls)
sheet, opaque_id = build_fact_sheet(fen, pvs, rolls)
```

## Verdicts and tiers

Per-candidate verdict ladder (`verify.py`):
`CONFIRMED-SOUND` (in an eval-equal engine line, fires within 2 plies) >
`CONFIRMED-SOUND-LATER` (sound but not yet due — carries the line's actual
next move) > `MAIA-TYPICAL` (strong humans play it here) >
`NOT-IN-BEST-LINES` > `UNSUPPORTED`. Confirmation is one-sided; a slow
plan's silence downgrades, never refutes.

Vocabulary tiers (each with a distinct epistemic contract):

| tier | claim | examples |
|---|---|---|
| **plan** | audited, carries corpus lift, engine-verifiable | pair_break (20.5× discrimination), weakness_harvest, rook_activation, backward_push |
| **advisory** | corpus dose-response curve, no per-position contract | SIMPLIFY / AVOID TRADES (space ≥ 6), the literature weakness matrix |
| **mechanism** | vocabulary only, no reliability claim | rook lifts, knight reroutes (real routes, not plans) |
| **campaign** | composition of plans, colift-evidenced | promotion (+17pp full vs absent), king hunt, conversion |

## Docs

- `CLAUDE.md` — the lab notebook: every finding, ruling, and study, with
  provenance. Read it before touching the grammar.
- `docs/KNOWN_ISSUES.md` — current caveats.

The grammar is calibrated against the frozen `benchmark_v1` (4,000
sha-pinned positions, `research/gpu_benchmark/`); re-run `reduce_agreement.py` after
any grammar change — the banked shards make re-scoring free.
