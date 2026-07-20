# chess-plans — positional pedagogy: naming long-term plans

**What this project is:** teach chess players the *plans* behind quiet moves —
minority attacks, storms, regroups, structural campaigns. End goal: a system
(possibly including a NN classifier) that, given a game or position, names the
plan in play with a verifiable witness, and coaches it. This is the
**positional** sibling of `~/Development/chess-lab` (tactical puzzle
explanations); it shares that project's method but none of its runtime.

## The founding result (2026-07-20, the three-tagged-games experiment)

Three annotated study games (Lilienthal, Tal, Benko — minority attack, spans
marked by the annotator) established the project's central finding:

> **Plans that RESTRUCTURE are invisible to static eval-term drift at creation
> time.** The backward c6 pawn moves the pawn-structure term by ~+8cp at the
> moment it is fixed — its value is future pressure. Term drift only appears
> later, at the HARVEST (exploitation phase). The creation-phase invariant is
> the **CHOREOGRAPHY**: pawn traffic toward the lever (b2–b4–b5, a4 support)
> and the lever itself (bxc6 / ...axb5 / ...cxb5).

Consequences (all already acted on):
- Plan detection = **geometry over move sequences** ("choreography theorems"),
  mechanism-style, not learned models — for every plan crisp enough to compile.
- A complete plan-unit = **choreography span → linked harvest drift**.
- Episode/clustering representations must carry a choreography channel, or
  clustering finds only harvests.
- **Plans follow STRUCTURES, not openings** — validated empirically: the
  Black-side minority attack fires mostly in London/QP games, not just the
  Exchange Caro-Kann.

## What exists in this repo

| file | what |
|---|---|
| `detectors.py` | `detect_minority_attack(game)` — both sides. Structure checks (`is_carlsbad`, `is_carlsbad_reversed`) + side-parameterized b-pawn choreography + lever + damaged-queenside post-condition. **Corpus-validated: White 53/28,461 elite games; Black 102/60,000** (Black-side mostly vs London). Blind-tested on Arkell–de Wolf (detected, correctly). |
| `experiments/trajectory_v1.py` | Term-trajectory extractor: quiet-ply sampling (skip captures/checks ± 1 ply) + rolling-drift segmentation. 300 Carlsbad games → 602 episodes, median span 16 plies. **Finds accumulation plans and harvests; misses restructuring creation** (see founding result). Depends on lucena-engine's `positional` module via PYTHONPATH (see Environment). |
| `experiments/trajectory_v0.py` | First prototype (event-based; superseded — kept for the diagnostic history). |
| `experiments/episodes.jsonl` | The 602 drift episodes (term, dir, net cp, ply span, moves, start FEN, game URL). |
| `experiments/episode_audit.html` | Human audit UI: 100 stratified spans, verdict buttons (coherent / not / split) + naming box, localStorage + export. **Not yet audited.** Links open the Lichess game AT the span's ply. |
| `data/lichess_elite_2023-01.pgn` | 311k elite games (Jan 2023). More months at database.nikonoel.fr. |
| `data/studies/*.pgn` | The ground-truth annotated games: 3 minority-attack chapters (Larakepara study) + Arkell–de Wolf blind-test game. |

## Method (inherited from chess-lab, proven there 15 times)

1. **Human supplies definitions, not labels.** A tagged game or a one-sentence
   ruling compiles into a rule/theorem; the theorem re-adjudicates the corpus.
2. **Theorem-first, NN-residual.** Every crisp plan becomes a choreography
   theorem (verifiable, corpus-scale, free). The NN is reserved for whatever
   resists formalization. Current bet: most named plans compile.
3. **Presence is geometry; the point is causality.** A detector's claim needs
   a post-condition (the weakness actually created, the harvest actually
   reaped). An unsound proof is worse than silence.
4. **Corpus-scale validation before speech.** Detector → run over elite corpus
   → sample review by the human → graduate or refine.

## The NN plan (current shape)

The classifier's role has RECEDED as theorems accumulate. Its residual jobs:
1. Plans too fuzzy for choreography (prophylaxis, worst-piece improvement,
   maneuvering quality, trade judgment).
2. The unnamed residue: after all theorems run over the corpus, cluster
   remaining plan-like spans (choreography + drift features). Nameable
   clusters → new theorems. Unnameable-but-real clusters → NN training set.
3. Possibly plan-salience ranking when several plans coexist.
Always proposer-only behind human ratification (the Maia-firewall pattern).

## Roadmap

1. **More annotated games → held-out detector testing.** Misses = choreography
   variants (a4-first orders, piece-executed minority attacks, other levers) —
   each miss refines the theorem. 10–20 games saturate.
2. **Two-phase linkage:** connect choreography spans to their harvest drifts
   (the episodes.jsonl spans that follow them); measure the lag. This defines
   the full plan-unit for pedagogy.
3. **Stage vocabulary from annotations:** initiation → resistance →
   reinforcement → lever → weakness fixed → exploitation (mine the study
   comments). This becomes the plan fact-sheet slots.
4. **Next plan theorems** (each needs a few tagged games): kingside pawn
   storm, IQP plans (d4-d5 break / blockade), good-knight-vs-bad-bishop,
   rook-lift attacks. Also: minority-attack DEFENSE (the ...a6/b5-block).
5. **Episode audit** (`experiments/episode_audit.html`) — 100 spans, judge
   "is this one coherent thing?" — calibrates trajectory v1's thresholds and
   seeds cluster names for accumulation-type plans.
6. **Clustering + rediscovery test** (after choreography channel added to
   episode features): known plans must re-emerge from the Carlsbad corpus
   unprompted.
7. **The NN decision point:** after 4–6 run over the corpus, size the
   unnamed residue. Small → no NN, fully verifiable product. Large → train
   (GBDT first) on theorem-labeled + cluster-labeled spans.

## Environment

- Python venv with `python-chess` (detectors.py needs nothing else).
- `trajectory_v1.py` additionally imports lucena-engine's static positional
  terms: `sys.path.insert(0, "/Users/avismara/Development/lucena/engine/python")`
  → `from lucena_engine import positional`. No engine server needed (static
  eval only, no search). chess-lab's venv works:
  `~/Development/chess-lab/.venv/bin/python`.
- Everything here is engine-free and deterministic; corpus scans run at
  thousands of games/second.

## Relation to chess-lab

- chess-lab = tactical puzzle explanations (shipped product, 15 adjudicated
  rulings, mechanism vocabulary). This repo = plans. Shared philosophy;
  independent code and data.
- If plan detection ever needs engine counterfactuals (e.g., "was the storm
  sound?"), chess-lab's `explainer/probes.py` pattern (lucena-engine gRPC on
  127.0.0.1:50052, fixed nodes) is the reference.
