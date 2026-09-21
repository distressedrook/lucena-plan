# lucena-plans — positional pedagogy: naming long-term plans

**What this project is:** teach chess players the *plans* behind quiet moves —
minority attacks, storms, regroups, structural campaigns. End goal (sharpened
2026-07-21): **given a position, reliably SUGGEST plans** — prospective, with
reliability stats and witness games — not just name the plan in a finished
game. The retrospective detectors are the LABELING MACHINE; the product is
`position → ranked plans + reliability + witnesses`. This is the
**positional** sibling of `lucena-tactics` (tactical puzzle
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

## Findings of the GM-corpus session (2026-07-21)

Two days of corpus work produced twelve validated results (all scripts and data are
in the repo). The full findings are archived in [docs/FINDINGS-2026-07-21.md](docs/FINDINGS-2026-07-21.md)
— read it before touching the plan grammar, the detectors, or the verify contract.

## What exists in this repo

**Layout (2026-07-22 restructure): `src/` (the library, flat modules), `docs/` (KNOWN_ISSUES.md), `research/` (experiments + gpu_benchmark + data + minority-attack-gm). Rows with a bare module name (`suggest.py`) live in `src/` and ship (see `pyproject.toml` py-modules); rows with a `research/...` path are the harness and never ship. The full shipped src surface is the 13 modules in py-modules — `closed_v0`, `detectors`, `dynamism`, `fact_sheet`, `king_danger_calibration`, `personal_sharpness`, `plan_diff`, `position_read`, `structures`, `suggest`, `tension`, `verify`, `weaknesses`.**

| file | what |
|---|---|
| `detectors.py` | `detect_minority_attack(game)` — both sides. Structure checks (`is_carlsbad`, `is_carlsbad_reversed`) + side-parameterized b-pawn choreography + lever + damaged-queenside post-condition. **Corpus-validated on FULL corpora: 1,179/311,327 Lichess elite (592 W / 587 B); 127/33,769 GM classical (113 W / 14 B)** — same 0.38% rate in both, side split flips at GM level (finding 1). Blind-tested on Arkell–de Wolf (detected, correctly). |
| `research/experiments/studies/trajectory_v1.py` | Term-trajectory extractor: quiet-ply sampling (skip captures/checks ± 1 ply) + rolling-drift segmentation. 300 Carlsbad games → 602 episodes, median span 16 plies. **Finds accumulation plans and harvests; misses restructuring creation** (see founding result). Depends on `lucena_core.positional` (moved out of lucena-engine in the 2026-07-23 consolidation; see Environment). |
| `research/experiments/studies/trajectory_v0.py` | First prototype (event-based; superseded — kept for the diagnostic history). |
| `research/experiments/reports/episodes.jsonl` | The 602 drift episodes (term, dir, net cp, ply span, moves, start FEN, game URL). |
| `research/experiments/reports/episode_audit.html` | Human audit UI: 100 stratified spans, verdict buttons (coherent / not / split) + naming box, localStorage + export. **Not yet audited.** Links open the Lichess game AT the span's ply. |
| `weaknesses.py` | **The fixed-target vocabulary** (finding 7, completed finding 12, extended finding 16): `weak_pawns`, `entombed_bishops`, `occupied_outposts`, `exposed_king`, `passive_rooks`, `weak_color_complex`, `back_rank_weak`, `overextended_pawns`, `backward_half_open`, `census()` — plus the standalone literature-definition pair `backward_pawns()` (Kmoch: strictly-ahead neighbors + enemy-pawn-controlled stop-square) and `isolated_pawns()`, both used by the suggest.py weakness-plan matrix and fact_sheet.py's WEAKNESSES sections. Also `knight_route`/`knight_route_conditional` (pawn-aware BFS route annotations). Pure geometry. |
| `suggest.py` | **THE FRONT DOOR — the position→plan suggester.** `./suggest.py "FEN"` or `./suggest.py game.pgn 24`; `--verify` for the closed loop. `build_menus(b)` builds the raw per-side candidate menus (shared by the numeric renderer `suggest_plans()` and `fact_sheet.py`'s prose renderer); PASS 1 state-triggered + the literature weakness-plan matrix (finding 16: isolani/backward/doubled/hanging-pawns, piece-gated) + PASS 2 situational (prophylaxis/simplify/avoid-trades/defense). OUTPOST and BREAK THE BISHOP PAIR candidates are per-square, each with a knight-route annotation. Effect-size ranking is corpus-derived where audited, prior otherwise. |
| `fact_sheet.py` | **The fact-sheet generator.** PRODUCT SURFACE (since 2026-07-24): `pre_verify_json(fen, pvs, rolls)` / `post_verify_json(fen, pvs, rolls)` — the structured `lucena-plans/sheet@1` JSON the backend consumes (`suggest proposes, verify FILTERS`; each confirmed plan carries the firing lines' `details`/`routes`/`family`, not geometry). The prose `build_fact_sheet` + `build_control_prompt` are retired to research use. All emit the (fen, pvs, rolls) contract (never rolls; ASSESSMENT cp from the supplied top PV, static term-sum + SEE correction as the no-engine fallback). FEN redacted to an opaque `POSITION-<hash>` id throughout — including a whole-sheet `_redact_fens` scrub over nested quiescence FENs (2026-07-24 fix). |
| `structures.py` | **The theory structure catalog**: 15 recognizers (carlsbad, isolani, hanging pawns, french advance, advance caro, mar del plata, benoni, maroczy, hedgehog, open sicilian, boleslavsky, stonewall, grünfeld center, spanish center, slav triangle), each written once White-owner and auto-mirrored; `classify(board)`. All ECO-validated (`research/experiments/studies/validate_structures.py`). |
| `research/experiments/studies/evidence_table.py` | The structure→plan evidence row builder (roadmap 1). Carlsbad row done → `carlsbad_row.jsonl` (15,163 structure games, both corpora, stage = none/launched/advanced/completed). |
| `research/experiments/studies/outpost_plan_v0.py` | **The hole/outpost plan** (plan-unit: concession → knight journey → anchored occupation → rent). 7,057 GM plan-units (20.9% of games!) → `outpost_plans.jsonl`. Laws: depth gradient 0.509/0.561/0.584 (4th/5th/6th rank); rim outposts worthless (0.496); f5 the best square in chess (0.630); self-conceded holes costliest (0.555 vs 0.540); median concession→occupation lag 14 plies; canonical route b1-c3-d5. Ready to graduate after review. |
| `research/data/lichess_elite_2023-01.pgn` | 311k elite games (Jan 2023). More months at database.nikonoel.fr. |
| `research/data/gm_classical.pgn` | **33,769 GM-vs-GM classical OTB games** (TWIC 1497–1653, Jul 2023–Jul 2026; both players titled GM; rapid/blitz/online excluded). Raw weeklies in `research/data/twic/`. |
| `research/data/studies/*.pgn` | The ground-truth annotated games: 3 minority-attack chapters (Larakepara study) + Arkell–de Wolf blind-test game. |
| `research/minority-attack-gm/` | The detected GM minority-attack games (PGN with Plan* evidence headers + `index.jsonl`; `teaching-set/` = the 3 engine-certified games). The 1,179-game Lichess dump was REMOVED in the 2026-07-22 restructure — regenerable by running `detectors.py` over the Lichess corpus. |
| `research/experiments/studies/bad_bishop_escape.py` | The escape study (finding 4). Cases in `bad_bishop_cases.jsonl` (4,581, with entombed/outside class, resolution, route, score). |
| `research/experiments/studies/bishop_v0.py`, `bishop_v1.py` | Good-vs-bad-bishop exploitation theorem; v1 requires entombment. Honest negative: entombment requirement did NOT raise the good side's ~55% — conversion needs a second weakness (finding 7). |
| `closed_v0.py` | Closedness detector (finding 5): `skeleton()` (rams/central/tension/open files) + hermetic `is_closed`. |
| `research/experiments/studies/bishop_vs_knight_closed.py` | The B-vs-N study (finding 6): closedness x openness x entombment x pair/single. |
| `research/experiments/studies/weakness_census.py` | The two-weaknesses experiment (finding 7); imports `weaknesses.py`, so the census grows as detectors are added. |
| `verify.py` | **THE CLOSED LOOP** (finding 14, extended finding 16; contract ruling 2026-07-22): `verify_plan(fen, side, family, pvs, rolls, square=None, route_hops=None)` — **the (fen, pvs, rolls) contract: the library NEVER rolls, it only checks caller-supplied lines** (backend supplies its own engine/Maia lines; research harness rolls via `research/experiments/tools/rolls.py` or replays banked shards). Per-family horizons + random floors, tighter floor when square-scoped, route-scaled horizon for multi-hop journeys. TIMING (immediate/developing/long-term) split into `CONFIRMED-SOUND` vs `CONFIRMED-SOUND-LATER` with an `immediate_move` field. Graded verdict. Either leg may be None — degrades and says so. |
| `research/experiments/tools/rolls.py` | **The research harness's live roll producers — the ONLY place in the repo that reaches an engine or Maia at runtime.** `roll_engine` (MultiPV=4 @1M nodes via `engine_roll_helper.py` under lucena-tactics' venv, protobuf isolation), `roll_maia` (K=9 docker-pipe gated rollouts), `roll_both` -> the `{"pvs", "rolls"}` bank shape the verify/fact_sheet/suggest CLIs read. |
| `research/experiments/studies/hierarchy.py` | **The pedagogy layer** (finding 13): MECHANISM/PLAN/CAMPAIGN, `compose()`, `curriculum()`. 7 campaigns with role-tagged members, composition edges colift-evidenced. (Research module — NOT in src/, not shipped.) |
| `plan_diff.py` | **The plan grammar / retrospective namer** — `snapshot`/`delta_stream`/`parse_line`/`labels`: the hand-written, hand-mirrored event detectors for every plan family (castle, harvest, outpost, pair_break, trade_into_endgame, minority_*, ...). verify.py treats its emissions as ground truth. Pure geometry over move sequences. |
| `tension.py` | Central-tension read: `central_tension` (cocked central levers), `classify_line` (how a banked line FIRST discharges the tension — keep/lock/resolve), `analyze`/`render` for the sheet's CENTRAL TENSION section. |
| `dynamism.py` | Sharpness buckets (finding 19): DEAD/QUIET/DYNAMIC/SHARP/RAZOR from narrowness + forcingness + compensation (gapped against SEE-adjusted material). Consumed by `fact_sheet`'s `character` block. |
| `position_read.py` | Deterministic renderer for the post-verify JSON sheet (`render(post)`) — no LLM in the read path (owner 2026-07-24), and since 2026-07-25 every detected plan is surfaced with its evidence TAG (engine-confirmed / strong-human / structural) instead of unconfirmed ones being dropped. Consumed by the backend's `render_position_read`. |
| `king_danger_calibration.py` | `p_catastrophe_profile(danger)` — calibrated P(catastrophe) in the three regimes (findings 21-25); consumed by `fact_sheet`'s king_risk block. |
| `personal_sharpness.py` | Per-player sharpness read (research-facing; not yet consumed by the shipped sheet). |
| `research/experiments/studies/campaign_study.py` | Full-corpus campaign calibration (finding 13); the monotone absent<fragment<partial<full gradient + the material-at-start symptom control. Witnesses -> `campaign_study.jsonl`. |
| `research/experiments/studies/composition_evidence.py` | Which mechanisms NEST in which plans, by colift-vs-random (the campaign edges). |
| `research/experiments/studies/export_benchmark.py` | Freezes `benchmark_v1.jsonl` (4,000 positions, sha+git-pinned) from the banked argmax anchors. |
| `research/experiments/studies/ev_pass_a_multi.py`, `ev_pass_b_multi.py`, `ev_pass_c_multi.py` | Multi-line agreeability (finding 14): engine MultiPV=4 (eval-equal gate) + Maia K=16 (40-60 gate) + merged report. |
| `research/experiments/studies/kstudy_reduce.py`, `kstudy_extend.py` | K-study reducer (convergence curve, K*=9) + the K=8->16 extension (raw UCIs banked). |
| `research/gpu_benchmark/` | **The copy-ready benchmark kit** (finding 14, re-run finding 16): `benchmark_v1.jsonl` + `gpu_bench.py` (Maia/GPU) + `engine_bench.py` (engine/CPU) + `check_shards.py` + `reduce_agreement.py` + its own agent-facing `CLAUDE.md`. Self-contained; produces raw-UCI futures labeled back home. `reduce_agreement.py` is re-run whenever the grammar changes (banked `eng_shards`/`maia_shards` cover all 4,000 positions — no new engine/Maia calls needed to re-score under a new family). |
| `research/experiments/reports/agreement_report_v6.txt` | The full 4,000-position engine-confirm/Maia-typical table (finding 16), post-`backward_push`/`pair_break` grammar. Per-plan: engine-confirm %, random floor %, Maia-typical %, n. `pair_break` 82%/4% (20.5x, cleanest in the vocabulary), `backward_push` 39%/10% (3.9x, production tier), `simplification` 91% (highest absolute confirm). |

## Method (inherited from chess-lab/lucena-tactics, proven there 15 times)

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

## Roadmap (reordered 2026-07-21 for the prospective goal)

1. **The structure→plan evidence table** — the product's backend. **Row 1
   (Carlsbad/minority attack) BUILT** (`research/experiments/studies/evidence_table.py`,
   `carlsbad_row.jsonl`): GM White-side — structure in 4.2% of games, launch
   24%, complete-given-launch 33%, score none 0.529 / launched 0.551 /
   completed 0.580. Stage scores re-confirm harvest-gating: Lichess
   advanced-but-no-lever = 0.466, WORSE than never launching. GM Black-side:
   launch 17.6%, completion 17.7% — the lever is systematically refused by
   GM defenders; the plan is effectively refuted at GM level. The structure
   RECOGNIZER layer for the rest of the table is `structures.py` (15
   theory-catalog recognizers, all ECO-fingerprint-validated on the GM
   corpus — see `research/experiments/studies/validate_structures.py`; notable: isolani most
   common at 16%, ownership asymmetry 0.538 W vs 0.428 B; space structures
   uniformly +2-4pp; hedgehog worst in book at 0.414). Next: stamp the
   launch/completion template across the other 14 rows as their plan
   theorems land.
2. **Plan-library breadth is the critical path** — a one-plan suggester
   isn't a suggester. Next theorems (a few tagged games each): kingside pawn
   storm, IQP plans, rook-lift attacks, minority-attack DEFENSE
   (...a6/b5-block). Two are session-ready to graduate into `detectors.py`
   after human sample review: **seal-to-entomb** (close the position to bury
   their bishop; post-condition = entombment) and **bad-bishop escape** (the
   defense twin, with the route vocabulary).
3. **Weakness vocabulary COMPLETE** (findings 12, 16): passive rook, weak
   color complex, back rank, overextended pawns, Kmoch backward pawns,
   isolated pawns. Now surfaced end-to-end in both `suggest.py` (the
   literature weakness-plan matrix) and `fact_sheet.py` (named per side).
   Remaining: corpus-calibrate the matrix's advisory-tier reliability
   lines (isolani/doubled/hanging-pawns — the SIMPLIFY/AVOID-TRADES
   precedent) and re-run the census rent-vs-lump-sum split (finding 7)
   with the two new detectors folded in.
4. **Two-phase linkage with the measured threshold:** harvest matcher must be
   span-conditioned and low-amplitude (finding 2: typical harvest ≈ +2–7cp,
   far under the 45cp episode floor). Harvest-gating (finding 7) defines the
   plan-unit's success criterion: created-but-unharvested is a NEGATIVE.
5. **More annotated games → held-out detector testing** (choreography
   variants: a4-first orders, piece-executed attacks, other levers).
6. **Stage vocabulary from annotations** → plan fact-sheet slots.
7. **Episode audit + clustering rediscovery test** (unchanged).
8. **The NN decision point** (direction settled — finding 8): size the
   unnamed residue after the theorems run; GBDT on structure features first;
   frozen-LC0 probes only if it plateaus.

## Environment

- Python venv with `python-chess` (detectors.py needs nothing else).
- `trajectory_v1.py` additionally imports the static positional terms from
  `lucena_core` (2026-07-23 consolidation — they moved out of lucena-engine):
  `from lucena_core import positional`. No engine server needed (static
  eval only, no search). lucena-tactics' venv works:
  `~/Development/lucena/lucena-tactics/.venv/bin/python`
  (computed relative to the superrepo root by rolls.py, not hardcoded).
- Detection and census layers are engine-free and deterministic; corpus scans
  run at thousands of games/second. The TEACHING-SET certification layer uses
  lucena-tactics' probes (lucena-engine gRPC on 127.0.0.1:50052, fixed 100k
  nodes ≈ 1s/position, deterministic) — see finding 3; static screening alone
  passes ~42% tactical false positives.

## Relation to lucena-tactics (formerly chess-lab)

- lucena-tactics = tactical puzzle explanations (shipped product, 15 adjudicated
  rulings, mechanism vocabulary). This repo = plans. Shared philosophy;
  independent code and data.
- If plan detection ever needs engine counterfactuals (e.g., "was the storm
  sound?"), lucena-tactics' `src/probes.py` pattern (lucena-engine gRPC on
  127.0.0.1:50052, fixed nodes) is the reference — now re-exported from the superrepo's `/common/engine_client` (2026-07-22), which both repos share instead of one reaching into the other's source tree.
