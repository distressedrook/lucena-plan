# chess-plans — positional pedagogy: naming long-term plans

**What this project is:** teach chess players the *plans* behind quiet moves —
minority attacks, storms, regroups, structural campaigns. End goal (sharpened
2026-07-21): **given a position, reliably SUGGEST plans** — prospective, with
reliability stats and witness games — not just name the plan in a finished
game. The retrospective detectors are the LABELING MACHINE; the product is
`position → ranked plans + reliability + witnesses`. This is the
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

## Findings of the GM-corpus session (2026-07-21)

Two days of corpus work produced twelve validated results. All scripts and data
are in the repo; scores below are the relevant side's points fraction.

1. **The detector generalizes to GM classical play — and exposes an
   online-only plan.** `data/gm_classical.pgn` (33,769 GM-vs-GM classical
   games, TWIC 1497–1653) yields 127 minority attacks at the same 0.38% rate
   as Lichess elite — but the side split flips from ~50/50 to **113 White /
   14 Black**. The Black-side minority attack (vs London) is largely an
   online phenomenon; the GM-endorsed plan is the classical White QGD-Exchange
   version.

2. **The harvest is small and lives in the pawns term.** 100-game aligned
   trajectory analysis: every term is flat during choreography (re-confirming
   the founding result at scale); the only consistent post-lever channel is
   the pawns term (+6.7cp White-side, 60% of games — matching the founding
   ~+8cp). White-side attackers harvest STRUCTURE; Black-side harvest
   MATERIAL. Harvest amplitude is far below trajectory_v1's 45cp episode
   floor — two-phase linkage needs a span-conditioned low-threshold matcher.

3. **Certified teaching sets exist.** Funnel: detector → static
   steady-rise/no-blunder filter → engine verification (fixed 100k nodes,
   chess-lab probes). Lichess: 311k → 1,179 → 113 → **50 strict**
   (`minority-attack/teaching-set/`). GM: 33,769 → 127 → 8 → **3**
   (`minority-attack-gm/teaching-set/`: Nesterov–Lobanov, Petrosyan–Perez
   Mitjans, Plat–Heberla). Lessons: the static filter has a ~42% tactical
   false-positive rate — engine verification is not optional; and at GM level
   a steadily-rising STATIC trajectory can be an engine-flat illusion (GM
   defenders give the terms but keep the balance).

4. **Bad bishop: the split that matters is entombed vs outside, and escape
   beats trade.** (`experiments/bad_bishop_escape.py`, 4,581 GM cases.)
   Outside-the-chain "bad" bishops cost NOTHING (0.517). Entombed ones carry
   the whole penalty (0.470), and the escape hierarchy is: activate/extract
   0.496 > trade 0.456 ≈ self-break 0.451 > stuck 0.436. **Escaping the
   bishop restores near-equality; trading it recovers only half** — a
   corpus-backed revision of the textbook advice. Escape routes are the
   classical maneuvers (Bd7–e8, Bg5/Bh6 before the gate shuts, Ba6).

5. **Closedness is detectable and closed GM games are MORE decisive.**
   (`experiments/closed_v0.py`.) Hermetic closure (≥2 central rams, ≤1
   tension, no open files, 12+ plies) = 0.7% of GM games; top ECOs are
   exactly the closed-opening catalog (B12, C02/C11/C18/C19, C50, C95) —
   the geometry rediscovered the openings. Draw rate 46.7% closed vs 55.9%
   rest: closure disables simplification, not winning.

6. **B-vs-N folklore fails both ways; entombment dominates.**
   (`experiments/bishop_vs_knight_closed.py`, 11,015 imbalance games.)
   Single B = single N everywhere (truly open included). The bishop PAIR
   premium is largest in PAWN-FULL positions (+4.8pp) and vanishes when
   truly open (+0.9pp) — the folklore inverts. The one large effect: an
   entombed bishop in an OPEN position, 0.424. **Imbalance is a multiplier;
   the detectable state (entombed/sealed/escaped) is the plan.** Caveat for
   all imbalance stats: corpus scores are survivorship-conditioned on GM
   stewardship.

7. **Two weaknesses, corrected: creation is flat, HARVEST is the gradient —
   and weaknesses split into rent-payers vs lump-sums.**
   (`weaknesses.py` + `experiments/weakness_census.py`, 1,249 minority-attack
   games.) Attacker score by weak pawns harvested: 0 → 0.489, 1 → 0.577,
   2+ → 0.656; created-but-never-harvested = 0.453, WORSE than no weakness
   (tempi paid, nothing collected). Per-type by presence: occupied outposts
   +8.3pp and exposed king +6.7pp (piece-access weaknesses pay RENT every
   move); weak pawns −3.0pp by presence (material weaknesses pay only as a
   LUMP SUM on capture — persistence means unharvested). The census-2+ jump
   the principle predicts appears only at GM level (0.603 vs 0.538, n=39):
   the second weakness is a technique against ACCURATE defense. Conversion
   prescription, corpus-derived: create the pawn weakness, win with the
   piece-access weakness it buys.

8. **RULING (2026-07-22, adjudicated): the minority attack is "2 pawns vs 3,
   semi-open c-file" — not Carlsbad-specific.** The user overruled the
   Carlsbad-only gate; `experiments/minority_general.py` adjudicated over
   both corpora (126k qualifying positions). Verdict: the DEFINITION stands —
   GMs launch at an identical 25% in non-Carlsbad instances. The PAYOFF is
   family-split: Carlsbad completed 0.547 vs 0.507 baseline, lever resolves
   22% of launches; non-Carlsbad completed 0.513, lever only 13%, and
   launched-overall runs NEGATIVE (0.472 vs 0.495) — offer the plan with
   family-specific numbers, never suppress it. Falsified hypothesis: ...c5
   dissolution does NOT rescue the defender (attacker flat-to-better after
   it, both families). `suggest.py` gate rewritten accordingly. The stall
   penalty replicates in all four cells (advanced-no-lever 0.424-0.457).

9. **The four-way plan-agreement experiment (engine / Maia3-2400 / actual
   GMs / random; 120 equalish GM positions, 12-ply futures, plan_diff
   naming).** (`experiments/ev_pass_[abc].py` → `engine_vs_human_plans.jsonl`.)
   Results: engine and Maia are roughly TIED as GM-plan predictors (specific-
   plan Jaccard 0.135 / 0.156 vs ~0.065 random floor — each ≈2x chance; an
   n=30 preview showing Maia dominance did not replicate). The RANDOM CONTROL
   audited the grammar: harvest (21 vs 7), outpost (12 vs 4), escape (10 vs 5)
   pass specificity; storm (24 vs 24), entomb (15 vs 18), open_king (6 vs 6)
   FAIL at 12-ply windows — event-anchored rules work, state-drift rules need
   tightening. weakness_harvest is the top cross-source agreement plan (as
   pre-registered). Coverage is the limiting factor: only 33% of actual GM
   12-ply futures contain a specific-plan event — consistent with catalog
   incompleteness + horizon < median plan length (14+ plies). Maia over-
   indexes outposts vs GMs (19 vs 12). Infra lesson: gRPC channels do not
   survive fork() — engine and Maia legs must run in separate processes
   (the passes architecture).
   **Grammar v2 A/B (same futures, better naming):** event-anchored rewrite
   + 4 new families (rook_activation, seventh_invasion, king_march,
   passer_creation/push) took GM coverage 52%→83% with the random floor FLAT
   (45%) and engine-actual agreement 0.141→0.274 (4.6x floor). rook_activation
   is the most common nameable plan in GM chess (90/120 positions, 4:1
   specificity, top agreement plan). **Horizon A/B (25 vs 12 plies):**
   absolute agreement rises (shared-plan 39%→54% E-A, 45%→62% M-A) and slow
   plans appear (minority, 7th-rank, passer_push) — but random floor explodes
   (45%→78% eventful; discrimination 4.6x→1.7x): long windows let random
   walks stumble through event predicates. CONCLUSION: horizons must be
   PER-FAMILY (each plan parsed at its measured natural timescale — harvest/
   outpost ~12-16 plies, minority/passer ~25-40) — the multi-scale parser is
   the next grammar iteration. Still failing specificity at any horizon:
   entomb family, open_king.

10. **Corpus-scale namer calibration (88,159 GM anchors; actual vs seeded
    random; both regimes; `experiments/overnight_lift.py` → `lift_report.txt`;
    runtime ~2 min — geometry at corpus scale is free).** Production
    vocabulary (lift, CI clear of 1.5): outpost 2.85, harvest 2.77, rook
    2.59, king_march 2.27@slow (two-regime theory's cleanest confirmation:
    1.64 fast / 2.27 slow), passer_push 1.77, passer_creation 1.65.
    Corrections of small-n mirages: passer_push "8x" -> 1.77; the minority
    attack's LINE-WINDOW detector is near-random (1.06) — it is a whole-phase
    campaign; detect via full-game staging + structure prior (carlsbad:W
    futures play it at 16% vs 0.77% base = 20x concentration). pawn_storm is
    ANTI-predictive at slow (0.65) — random lines out-storm GMs; retire from
    rollout vocabulary pending an intent condition. Structure->plan table at
    scale now exists (e.g. open_sicilian:B -> minority_general 35%;
    french_advance:W -> bad_bishop_escape 11%). Live run dashboard:
    `experiments/status_server.py` on 127.0.0.1:8899.

11. **EXTERNAL VALIDATION — the machine agrees with human annotators.**
    (`experiments/annotator_validation.py`; 599 human-annotated games,
    ValdemarOrn/Chess collections, in `data/annotated/` — now the permanent
    regression suite.) Wherever an annotator's comment names one of our
    concepts, the machinery independently finds it far above a shuffled
    control — PHASE-MATCHED (same-ply windows in other games; the stricter
    test): seventh rank 64% vs 14% (4.6x), bishop pair 78%/55% vs 30%/10%,
    outpost 33% vs 10% (3.3x), bad bishop 33% vs 17%, passed pawn 55% vs 31%
    (n=62; naive control 16% — phase explained part of the lift). Demoted by
    phase-matching: open file (43% vs 39% — base rate too high for the test
    at n=28). Zero tuning toward this corpus; crude keyword matching means
    survivors are floors. Two diagnostic failures: "weak pawn" INVERTED (24% vs 53% —
    annotators speak prospectively; our strict presence-predicate is too
    common to discriminate — matching the corpus lesson that only HARVEST
    carries signal), and annotators' "blockade" is lexically broader than
    the Nimzowitsch front-square rule. v4 grammar additions the same day:
    blockade 2.02 lift, pawn_storm fixed 0.65→2.04 via opposite-castling
    intent gate, pair_acquisition retired (0.71 slow — state, not plan);
    calibration re-run clean after finding a 7% silent-drop bias bug
    (94,289 anchors).

12. **NN direction settled:** no NNUE finetuning (wrong architecture); no LC0
   finetuning (data-starved, destroys the representation). Ladder: GBDT on
   explicit structure features first (calibrated reliability numbers ARE the
   product) → frozen-LC0 linear probes per plan if GBDT plateaus (McGrath-
   style concept probing) → plan-conditioned policy finetune only ever for
   move-level coaching. Bottleneck is the label matrix (negatives +
   plan-library breadth), not architecture.

## What exists in this repo

| file | what |
|---|---|
| `detectors.py` | `detect_minority_attack(game)` — both sides. Structure checks (`is_carlsbad`, `is_carlsbad_reversed`) + side-parameterized b-pawn choreography + lever + damaged-queenside post-condition. **Corpus-validated on FULL corpora: 1,179/311,327 Lichess elite (592 W / 587 B); 127/33,769 GM classical (113 W / 14 B)** — same 0.38% rate in both, side split flips at GM level (finding 1). Blind-tested on Arkell–de Wolf (detected, correctly). |
| `experiments/trajectory_v1.py` | Term-trajectory extractor: quiet-ply sampling (skip captures/checks ± 1 ply) + rolling-drift segmentation. 300 Carlsbad games → 602 episodes, median span 16 plies. **Finds accumulation plans and harvests; misses restructuring creation** (see founding result). Depends on lucena-engine's `positional` module via PYTHONPATH (see Environment). |
| `experiments/trajectory_v0.py` | First prototype (event-based; superseded — kept for the diagnostic history). |
| `experiments/episodes.jsonl` | The 602 drift episodes (term, dir, net cp, ply span, moves, start FEN, game URL). |
| `experiments/episode_audit.html` | Human audit UI: 100 stratified spans, verdict buttons (coherent / not / split) + naming box, localStorage + export. **Not yet audited.** Links open the Lichess game AT the span's ply. |
| `weaknesses.py` | **The fixed-target vocabulary** (finding 7): `weak_pawns`, `entombed_bishops`, `occupied_outposts`, `exposed_king`, `census()`. Pure geometry. Not yet built: passive rook, color complex, back rank, overextended pawns. |
| `suggest.py` | **THE FRONT DOOR — the position→plan suggester v0.** `./suggest.py "FEN"` or `./suggest.py game.pgn 24`. Wires structures + skeleton + census + hole scan into ranked plans per side, each with its corpus reliability line and witnesses. Effect-size ranking is hardcoded from the findings; grows as theorems graduate. |
| `structures.py` | **The theory structure catalog**: 15 recognizers (carlsbad, isolani, hanging pawns, french advance, advance caro, mar del plata, benoni, maroczy, hedgehog, open sicilian, boleslavsky, stonewall, grünfeld center, spanish center, slav triangle), each written once White-owner and auto-mirrored; `classify(board)`. All ECO-validated (`experiments/validate_structures.py`). |
| `experiments/evidence_table.py` | The structure→plan evidence row builder (roadmap 1). Carlsbad row done → `carlsbad_row.jsonl` (15,163 structure games, both corpora, stage = none/launched/advanced/completed). |
| `experiments/outpost_plan_v0.py` | **The hole/outpost plan** (plan-unit: concession → knight journey → anchored occupation → rent). 7,057 GM plan-units (20.9% of games!) → `outpost_plans.jsonl`. Laws: depth gradient 0.509/0.561/0.584 (4th/5th/6th rank); rim outposts worthless (0.496); f5 the best square in chess (0.630); self-conceded holes costliest (0.555 vs 0.540); median concession→occupation lag 14 plies; canonical route b1-c3-d5. Ready to graduate after review. |
| `data/lichess_elite_2023-01.pgn` | 311k elite games (Jan 2023). More months at database.nikonoel.fr. |
| `data/gm_classical.pgn` | **33,769 GM-vs-GM classical OTB games** (TWIC 1497–1653, Jul 2023–Jul 2026; both players titled GM; rapid/blitz/online excluded). Raw weeklies in `data/twic/`. |
| `data/studies/*.pgn` | The ground-truth annotated games: 3 minority-attack chapters (Larakepara study) + Arkell–de Wolf blind-test game. |
| `minority-attack/`, `minority-attack-gm/` | All detected minority-attack games, one PGN each with Plan* evidence headers + `index.jsonl`. Subfolders: `well-executed/` (static filter), `teaching-set/` (engine-certified; 50 Lichess / 3 GM). Verdicts in `engine_verified.jsonl`. |
| `experiments/bad_bishop_escape.py` | The escape study (finding 4). Cases in `bad_bishop_cases.jsonl` (4,581, with entombed/outside class, resolution, route, score). |
| `experiments/bishop_v0.py`, `bishop_v1.py` | Good-vs-bad-bishop exploitation theorem; v1 requires entombment. Honest negative: entombment requirement did NOT raise the good side's ~55% — conversion needs a second weakness (finding 7). |
| `experiments/closed_v0.py` | Closedness detector (finding 5): `skeleton()` (rams/central/tension/open files) + hermetic `is_closed`. |
| `experiments/bishop_vs_knight_closed.py` | The B-vs-N study (finding 6): closedness x openness x entombment x pair/single. |
| `experiments/weakness_census.py` | The two-weaknesses experiment (finding 7); imports `weaknesses.py`, so the census grows as detectors are added. |

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

## Roadmap (reordered 2026-07-21 for the prospective goal)

1. **The structure→plan evidence table** — the product's backend. **Row 1
   (Carlsbad/minority attack) BUILT** (`experiments/evidence_table.py`,
   `carlsbad_row.jsonl`): GM White-side — structure in 4.2% of games, launch
   24%, complete-given-launch 33%, score none 0.529 / launched 0.551 /
   completed 0.580. Stage scores re-confirm harvest-gating: Lichess
   advanced-but-no-lever = 0.466, WORSE than never launching. GM Black-side:
   launch 17.6%, completion 17.7% — the lever is systematically refused by
   GM defenders; the plan is effectively refuted at GM level. The structure
   RECOGNIZER layer for the rest of the table is `structures.py` (15
   theory-catalog recognizers, all ECO-fingerprint-validated on the GM
   corpus — see `experiments/validate_structures.py`; notable: isolani most
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
3. **Complete the weakness vocabulary** (`weaknesses.py`): passive rook,
   weak color complex, back rank, overextended pawns. Then re-run the census
   experiments — the rent-vs-lump-sum split (finding 7) is the conversion
   layer of EVERY plan.
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
- `trajectory_v1.py` additionally imports lucena-engine's static positional
  terms: `sys.path.insert(0, "/Users/avismara/Development/lucena/engine/python")`
  → `from lucena_engine import positional`. No engine server needed (static
  eval only, no search). chess-lab's venv works:
  `~/Development/chess-lab/.venv/bin/python`.
- Detection and census layers are engine-free and deterministic; corpus scans
  run at thousands of games/second. The TEACHING-SET certification layer uses
  chess-lab's probes (lucena-engine gRPC on 127.0.0.1:50052, fixed 100k
  nodes ≈ 1s/position, deterministic) — see finding 3; static screening alone
  passes ~42% tactical false positives.

## Relation to chess-lab

- chess-lab = tactical puzzle explanations (shipped product, 15 adjudicated
  rulings, mechanism vocabulary). This repo = plans. Shared philosophy;
  independent code and data.
- If plan detection ever needs engine counterfactuals (e.g., "was the storm
  sound?"), chess-lab's `explainer/probes.py` pattern (lucena-engine gRPC on
  127.0.0.1:50052, fixed nodes) is the reference.
