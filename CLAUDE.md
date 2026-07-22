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
   beats trade.** (`experiments/studies/bad_bishop_escape.py`, 4,581 GM cases.)
   Outside-the-chain "bad" bishops cost NOTHING (0.517). Entombed ones carry
   the whole penalty (0.470), and the escape hierarchy is: activate/extract
   0.496 > trade 0.456 ≈ self-break 0.451 > stuck 0.436. **Escaping the
   bishop restores near-equality; trading it recovers only half** — a
   corpus-backed revision of the textbook advice. Escape routes are the
   classical maneuvers (Bd7–e8, Bg5/Bh6 before the gate shuts, Ba6).

5. **Closedness is detectable and closed GM games are MORE decisive.**
   (`closed_v0.py`.) Hermetic closure (≥2 central rams, ≤1
   tension, no open files, 12+ plies) = 0.7% of GM games; top ECOs are
   exactly the closed-opening catalog (B12, C02/C11/C18/C19, C50, C95) —
   the geometry rediscovered the openings. Draw rate 46.7% closed vs 55.9%
   rest: closure disables simplification, not winning.

6. **B-vs-N folklore fails both ways; entombment dominates.**
   (`experiments/studies/bishop_vs_knight_closed.py`, 11,015 imbalance games.)
   Single B = single N everywhere (truly open included). The bishop PAIR
   premium is largest in PAWN-FULL positions (+4.8pp) and vanishes when
   truly open (+0.9pp) — the folklore inverts. The one large effect: an
   entombed bishop in an OPEN position, 0.424. **Imbalance is a multiplier;
   the detectable state (entombed/sealed/escaped) is the plan.** Caveat for
   all imbalance stats: corpus scores are survivorship-conditioned on GM
   stewardship.

7. **Two weaknesses, corrected: creation is flat, HARVEST is the gradient —
   and weaknesses split into rent-payers vs lump-sums.**
   (`weaknesses.py` + `experiments/studies/weakness_census.py`, 1,249 minority-attack
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
   Carlsbad-only gate; `experiments/studies/minority_general.py` adjudicated over
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
    random; both regimes; `experiments/studies/overnight_lift.py` → `lift_report.txt`;
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
    `experiments/tools/status_server.py` on 127.0.0.1:8899.

11. **EXTERNAL VALIDATION — the machine agrees with human annotators.**
    (`experiments/studies/annotator_validation.py`; 599 human-annotated games,
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

12. **The breadth pass (2026-07-22): 11 literature plans compiled and
   audited in one day; 5 graduate, 4 fail, 2 starve.** Gap map from
   Nimzowitsch/Silman/Soltis vs the catalog; every rule event-anchored;
   v5 audit over 94,289 anchors. PRODUCTION (lift fast/slow):
   trade_into_endgame **339.5/33.5** (the highest-lift plan in the book —
   random lines never trade queens while holding an asset and keep
   trading), remove_defender 7.11/5.36, chain_base_attack 4.30/2.88
   (Nimzowitsch's chain law validated; 10-13% of futures in
   giuoco/catalan/slav structures), alternation 3.00/4.52 (finding 7's
   two-front shuttle is real GM technique, outcome 0.607 — the best
   outcome price in the vocabulary), heavy_battery 1.93/2.35. FAILED:
   fix_then_attack 1.10/1.04, majority_roll 0.63 slow (ANTI — the storm
   disease: needs an intent gate), bind_squeeze 0.33/0.19 (strongly ANTI —
   refusing trades is what RANDOM play does; the real squeeze must be
   finer). rook_lift RETIRED as a family after two-round adjudication:
   v1 geometry 0.91/0.99; v2 intent-gated (check / king-zone capture /
   attack-mass rise after the swing) STILL 0.91/1.17 — random kings get
   checked by accident at the GM rate; the storm cure does not transfer.
   Verdict: the lift is a MECHANISM inside attacking plans (a route, like
   the knight hop within an outpost plan), not a plan family; trace-
   annotation only. Joins pair_acquisition ("state, not plan") as a
   category-boundary correction. STARVED
   (preconditions too rare at anchors, not refuted): minority_block,
   piece_attack. Weakness vocabulary completed the same day
   (passive_rooks, weak_color_complex, back_rank_weak, overextended_pawns,
   backward_half_open); structures at 30 (nimzo_samisch, winawer_chain,
   benko_structure, split_majorities — split_majorities fires in 54% of
   games, the most common structure in the catalog). K-study (12/12
   shards): per-position Maia plan frequencies still drifting at K=8
   (Δ=0.044); K=16 extension running on the same 300 anchors (raw UCIs
   banked this time — the k-bank is now relabelable under any grammar).

13. **The hierarchy is measured, and the CAMPAIGN is a real unit of value
   (2026-07-22).** Three levels with distinct epistemic contracts —
   MECHANISM (vocabulary, no reliability claim) / PLAN (audited, carries
   lift) / CAMPAIGN (composition of same-side plans within 30-ply chains,
   `hierarchy.py::compose`). Composition edges corpus-evidenced by colift
   vs the random floor (`experiments/studies/composition_evidence.py`):
   deny_castling->center_break 14.9x@2.3r, storm_launch->pawn_storm
   28.4x@1.5r, entomb->chain_base 2.0x@1.9r, seventh->king_march 2.4x@1.5r;
   pair_acquisition/majority_roll/fix_then_attack compose with NOTHING
   above floor (states, confirmed). Full-corpus campaign study
   (`experiments/studies/campaign_study.py`, 29,730 GM games): monotone
   absent<fragment<partial<full gradient in EVERY campaign — PROMOTION
   0.458->0.626 (+17pp, the largest gradient in the book), KING HUNT
   ->0.634, CONVERSION ->0.567. REFUTED pre-registration: no campaign-level
   stall penalty (fragments BEAT absent — members are already-valuable
   plans, unlike raw weaknesses). SYMPTOM TEST passed: 81% of full
   promotion campaigns launch from MATERIAL EQUALITY and score 0.643
   (higher than unconditioned); launched-from-behind still beats absent
   (0.525 vs 0.458) — promotion is a plan, not a symptom of winning.
   KING ATTACK required the first per-family window (storm clock opens at
   the VICTIM'S CASTLING ply, not window start — backward-compatible):
   0 instances -> 2,084+220, gradient 0.484->0.605. Campaign witness bank:
   `campaign_study.jsonl` (8,955 full promotions, 7,878 full conversions,
   with spans). Curriculum falls out mechanically: mechanisms -> plans by
   lift -> campaigns after their members (`python3 hierarchy.py`).

14. **The loop is CLOSED (2026-07-22): suggest -> ROLL -> DIFF, per
   position.** VERIFY is not a new subsystem — it is the existing pipeline
   in a loop (the user's reframe). `verify.py::verify_plan(fen, side,
   family)`: engine roll (MultiPV=4 @1M nodes, shelled to chess-lab's venv
   via `experiments/tools/engine_roll_helper.py` for protobuf isolation) + Maia
   roll (K=9, the k-study K*, 40-60 policy gate) -> `plan_diff.labels()`
   diff -> graded verdict CONFIRMED-SOUND (in an eval-equal engine line) >
   MAIA-TYPICAL (>=2 of 9 rolls, beats floor) > NOT-IN-BEST-LINES >
   UNSUPPORTED. Per-family horizons (harvest 14, minority 30, alternation
   40 — finding 9's timescales finally used). `suggest.py --verify` /
   `suggest_verified()` — the front door is end-to-end for the first time.
   Verified live: engine's 4 equal PVs, diff tagged chain_base_attack
   CONFIRMED-SOUND, declined harvest/rook/outpost. Caveats: confirmation is
   ONE-SIDED (true REFUTED needs a forced-commit roll one move deeper —
   same loop); ~57s/engine-roll (on-demand, not inline). Note: Maia has NO
   search (looks 0 plies) — the 25-ply horizon is our rollout chaining 25
   policy predictions; the engine is the only leg that looks ahead.

   **K-STUDY FINAL: K*=9** (12/12 base shards + K=16 extension). Per-
   position Maia plan-frequency settles at the 9th rollout; corpus
   marginals were stable at K=8 (only the per-position VERIFY contract
   needed K>8). Extension banked RAW UCIs -> the k-bank is relabelable
   under any future grammar.

   **MULTI-LINE AGREEABILITY (120 positions, engine leg; user's 2 gates:
   eval-equal lines, 40-60 Maia band).** `experiments/ev_pass_*_multi.py`.
   Equalish middlegames hold ~3.4 EQUAL-EVAL plans (mean; "one best plan"
   is empirically false -> the ranked-list format is vindicated by the
   engine). 55% of GM-engine agreement lives in PVs 2-4 (single-PV was
   under-counting). The union-any-line metric SATURATES (81% vs 71% random-
   union floor = 1.14x, meaningless) — the honest metrics are floor-immune
   PER-PLAN: union Jaccard 1.42x, and the CONFIRMATION RATE (GM plan in an
   eval-equal engine line): high-confirmation event-anchored plans
   (simplification 88, prepared_break 85, rook_activation 85, outpost 77,
   harvest 68) vs low-confirmation state/slow plans (entomb 29, open_king
   33, blockade 38 — payoff past the 25-ply horizon). This split IS why
   verify.py needs per-family horizons and why a slow plan's silence must
   downgrade to UNSUPPORTED, never REJECT. Maia distributional leg queued.

   **THE BENCHMARK: `benchmark_v1` (4,000 frozen positions).**
   `experiments/studies/export_benchmark.py` — banked argmax anchors (NOT a
   load_anchors re-derivation, which the v5 grammar reshuffled; caught by a
   150/300 k-study-overlap check), sha256+git-pinned, 300 flagged kstudy.
   A standing EVAL SET: grammars/models/K vary against it, positions never
   do. Copy-ready kit in `gpu_benchmark/` (self-contained, its own
   CLAUDE.md written for the GPU box's agent): `gpu_bench.py` (Maia leg,
   GPU, K rollouts, reproducible cross-machine seeds), `engine_bench.py`
   (engine leg, CPU, MultiPV, UCI+gRPC backends), `check_shards.py`,
   `reduce_agreement.py` (home-side merge). Not yet RUN — the 4,000-scale
   grading turns "validated in the small" into "validated at scale, per-
   structure." rook_lift RETIRED this session (two-round adjudication, even
   intent-gated stayed 0.91/1.17 — a MECHANISM/route, not a plan; joins
   pair_acquisition/bind_squeeze as category-boundary corrections).

   **RULING (2026-07-22, rook_activation surfacing):** basic-vocabulary
   plans (rook to open file, outpost) stay in the CANDIDATE tier even when
   their state trigger is near-universal (rook file-trigger fires 84-86%,
   outpost 81%) — do NOT tighten triggers to fake selectivity; the ENGINE
   tier prunes per position. Measured on the banked 120: engine filter cuts
   39% of rook firings; GM-played enrichment 34% vs 26% (right direction,
   not yet significant — the 4,000 benchmark settles it). Distinguish
   rook_activation (production, lift 2.26-2.58) from rook_lift (retired
   mechanism) — they are different families.

   **GROUNDING TEST: PASS** (`experiments/reports/grounding_test.md`). Fact-sheet
   narration (Sonnet + Gemini Flash-Lite, no board/engine access, geometry-
   only fact sheet from `suggest.py`) tested in two rounds on the same
   position, the second adding exactly one new fact (the rook_activation
   candidate above) to isolate delta-fidelity. Sonnet: zero hallucinations
   across both rounds, correctly restated the new fact near-verbatim.
   Gemini Flash-Lite: 2 errors round 1 (space-differential inversion,
   fabricated plural "knights"), 0 round 2 (n=1/cell — not yet a trend).
   Confirms: geometry does the chess, the fact sheet carries truth, model
   choice is a style/cost knob — Sonnet reliably so, Flash-Lite usable but
   spot-check until run at larger n.

15. **NN direction settled:** no NNUE finetuning (wrong architecture); no LC0
   finetuning (data-starved, destroys the representation). Ladder: GBDT on
   explicit structure features first (calibrated reliability numbers ARE the
   product) → frozen-LC0 linear probes per plan if GBDT plateaus (McGrath-
   style concept probing) → plan-conditioned policy finetune only ever for
   move-level coaching. Bottleneck is the label matrix (negatives +
   plan-library breadth), not architecture.

16. **The prose fact sheet, per-square verify architecture, and two graduated
   plan families (2026-07-22 session).** Several fixes landed together —

   **Verify architecture, fixed:** OUTPOST and BREAK THE BISHOP PAIR
   candidates are now per-square/per-target, not bundled (a confirmed d5
   must never lend credibility to an unconfirmed f6). `verify_plan()`
   gained TIMING (fires-at-ply, immediate ≤2 / developing ≤6 / long-term
   >6 → `CONFIRMED-SOUND` vs `CONFIRMED-SOUND-LATER`, with an
   `immediate_move` field) and route-scaled horizons for convoluted
   knight journeys (`knight_route_conditional()`: pawn-safe route now +
   named-blocker shortcut, since real maneuvers go back-and-forth and
   blocking pawns may vanish by execution time). PERSIST lowered 6→4 for
   outpost_occupation.

   **Two new families, both audited:** `pair_break` (trade a minor —
   knight OR bishop, widening strengthened it — for the opponent's
   bishop when they hold the pair) graduated at **lift 15.66 fast /
   11.71 slow** (n=26,183) — 2nd-strongest family in the book, confirmed
   again at benchmark scale (82% engine-confirm / 4% floor = **20.5×
   discrimination**, the cleanest in the vocabulary). `knight_reroute`
   (multi-hop knight maneuvers) FAILED its audit (1.13/0.87 — random
   knights wander into holes at the GM rate) and joined `rook_lift`/
   `pair_acquisition` in the retired-mechanism tier (trace-only, not a
   plan).

   **DENY CASTLING's elimination gate audited, deliberately not wired
   live:** reusing already-banked engine/Maia lines (no new rolling),
   712 trigger cases → 86% eliminated (opponent castles within 12 plies
   in ≥1 rolled line) — confirms the printed candidate is right to warn
   "rollout-invisible." Left corpus-only per explicit scoping.

   **Two advisories calibrated as a mirror pair:** AVOID TRADES (new,
   space-advantaged side) and SIMPLIFY (existing, re-calibrated) share
   one corpus study each side of the same space-differential axis
   (`space_trades_study.py` / `simplify_gate_study.py`, 25,562 GM games):
   "considerable" space edge starts at **6** (+9.0pp avoid-vs-heavy for
   the advantaged side; symmetric -9.0pp for the cramped side pushed to
   trade). SIMPLIFY's inherited literature gate (-4) was too loose;
   tightened to match. Both are advisory-tier — the corpus dose-response
   curve IS the evidence, no engine contract needed.

   **The fact sheet rewritten from "mechanical" to "mechanical AND
   natural language"** (`fact_sheet.py`) after a multi-round back-and-
   forth: ASSESSMENT (bucketed from lucena-engine's 5-term static cp sum,
   words only) → POSITION READ (prose: the engine's own `standing` text,
   space/king as PLAIN GEOMETRIC FACTS ONLY — a caught bug: the sheet
   once asserted "no pawn shelter"/"stuck in the center" as hardcoded
   judgments that contradicted the API's own king-safety verdict on a
   real position; fixed by pulling shield/danger language only from the
   term's own `standing`, never re-derived) → material/bishop-pair →
   full skeleton/lever/majority prose (parsed from `pawn_decomposition()`
   /`skeleton()`'s own structured output, not hand-authored) → STRUCTURE
   (named only; the narrating LLM may recite theory, we don't inject it)
   → dedicated WEAKNESSES FOR WHITE / WEAKNESSES FOR BLACK sections
   (only what's present — no "No X" negative lines; pawn islands moved
   OUT as a neutral feature, not a weakness) → PLAN FOR WHITE/BLACK
   (top candidates, corpus/lift/verify jargon stripped). `suggest.py`
   refactored: `build_menus()` extracted so both the numeric and prose
   renderers share one source of truth.

   **The weakness-plan matrix + Kmoch backward pawns (2026-07-22, user
   request):** `weaknesses.py` gained `backward_pawns()` (the literature
   Kmoch definition — neighbors strictly ahead, stop-square enemy-PAWN-
   controlled, not passed; supersedes `backward_half_open` for plan
   purposes, which required the pawn to already be file-isolated and
   missed the classic Boleslavsky/Scheveningen case) and
   `isolated_pawns()`. `suggest.py` gained a literature-tier matrix —
   BESIEGE/USE-OR-LIQUIDATE (isolani), FIX-AND-BESIEGE (backward pawn,
   advisory), TARGET (doubled), PRESSURE/KEEP-ABREAST (hanging pawns) —
   every clause piece-gated (a missing knight silently drops the
   "blockade with a knight" clause; the plan dies only when NO clause
   survives), advisory tier per the SIMPLIFY precedent (literature now,
   corpus calibration opportunistic).

   **`backward_push` (the freeing break) graduated after THREE audit
   rounds** — the intent-gate lesson repeats: v1 bare push scored
   0.99 fast / 0.82 slow (the storm/rook_lift disease — random shoves
   the pawn MORE than GMs, who wait for the right moment); v2's
   no-net-pawn-loss gate broke on even liquidations (transiently dips
   material mid-exchange); v3's **SEE preparedness gate** (after the
   push, the opponent's static-exchange value on the stop-square is
   zero — handles x-rays and even trades that raw attacker-counts get
   wrong) graduated clean: **corpus lift 1.55 fast [1.40,1.71] / 1.36
   slow [1.26,1.48]** (n=20,688, full 33,769-game corpus) and
   **benchmark_v1: 39% engine-confirm vs 10% floor = 3.9× discrimination**
   — production tier, between weakness_harvest (4.1×) and
   rook_activation (3.7×), clear of the retired tier (knight_reroute/
   open_king at 2.4×). Engine endorses the break at ~2× the GM in-window
   rate (16.7% vs 8.5%) — engine-CONTRACT gated, never surfaced
   unverified (the bare-push rule really is random-typical).

   **Full 4,000-position benchmark re-run** under the current grammar
   (`gpu_benchmark/reduce_agreement.py`, both legs at 4000/4000
   coverage, mean 3.1 eval-equal engine lines/position) confirmed the
   whole vocabulary is stable after adding two new families: `pair_break`
   82%/4%=20.5×, `simplification` 91% (highest absolute confirm in the
   book), retired families stayed low (`rook_lift` 11%/0%). Report banked
   at `experiments/reports/agreement_report_v6.txt`.

17. **The product-integration wave (2026-07-22, evening): the layer went
   LIVE in the backend, and the lines became the source of every printed
   specific.** The (fen, pvs, rolls) contract shipped end-to-end:
   lucena-backend rolls in-process (warm pooled engine + MaiaEngine —
   full 1M/250k calibration nodes cost only ~4-5s live, the research
   57s was subprocess/cold-hash/gRPC overhead; Maia leg 11ms/policy call
   → 2.5s, always on) and gates entry (freeform paste, out of book,
   middlegame, |eval| <= 1.5). Architecture ruling that reshaped
   rendering: **suggest proposes, verify FILTERS — every specific the
   sheet prints comes from the firing eval-equal lines, never from
   geometry**: `verify_plan` now returns `details` (the emitters' own
   specifics, deduped across firing lines) and `routes` (the observed
   piece journey per line, via `_journey` backward-chaining — NOT
   merged across lines). Motivating incidents: a knight-route
   d7-b8-a6-b4-d3 printed on a pair-break plan that every rolled line
   executed as BxB@f4 instead; PUSH-THE-PASSER surfacing on a
   `passer_creation`-only confirmation. New geometry the same day:
   `bishop_confinement()` (wall-vs-door blocker classification — the
   Carlsbad c1 bishop is BETWEEN chains with door b2-b3, not choked;
   three-way weakness wording), `standing_batteries()` +
   the `heavy_battery` proposer (was an orphan family, same gap as
   KNOWN_ISSUES #8), passer squares named with escort annotations.
   Engine-side: king-safety gained the centred-uncastled-king penalty
   (the two-attacker zone gate zeroed a lone staring queen; gated on
   open files nearby so startpos can't fire). **`attack_passer`
   AUDITED same day** (emitter tracks the passer as it advances;
   details name the attacking pieces read off the line): benchmark
   87% engine-confirm / 44% floor, 91% maia-typical (n=253); corpus
   lift 1.30/1.42 — a move-type plan (free_bad_bishop precedent):
   per-position engine presence is the admission ticket, never the
   floor gate. Reports: `experiments/reports/agreement_report_v7.txt`
   + `lift_report_v7.txt` (94,289 anchors; whole vocabulary stable
   under the v7 grammar).

## What exists in this repo

| file | what |
|---|---|
| `detectors.py` | `detect_minority_attack(game)` — both sides. Structure checks (`is_carlsbad`, `is_carlsbad_reversed`) + side-parameterized b-pawn choreography + lever + damaged-queenside post-condition. **Corpus-validated on FULL corpora: 1,179/311,327 Lichess elite (592 W / 587 B); 127/33,769 GM classical (113 W / 14 B)** — same 0.38% rate in both, side split flips at GM level (finding 1). Blind-tested on Arkell–de Wolf (detected, correctly). |
| `experiments/studies/trajectory_v1.py` | Term-trajectory extractor: quiet-ply sampling (skip captures/checks ± 1 ply) + rolling-drift segmentation. 300 Carlsbad games → 602 episodes, median span 16 plies. **Finds accumulation plans and harvests; misses restructuring creation** (see founding result). Depends on lucena-engine's `positional` module via PYTHONPATH (see Environment). |
| `experiments/studies/trajectory_v0.py` | First prototype (event-based; superseded — kept for the diagnostic history). |
| `experiments/reports/episodes.jsonl` | The 602 drift episodes (term, dir, net cp, ply span, moves, start FEN, game URL). |
| `experiments/reports/episode_audit.html` | Human audit UI: 100 stratified spans, verdict buttons (coherent / not / split) + naming box, localStorage + export. **Not yet audited.** Links open the Lichess game AT the span's ply. |
| `weaknesses.py` | **The fixed-target vocabulary** (finding 7, completed finding 12, extended finding 16): `weak_pawns`, `entombed_bishops`, `occupied_outposts`, `exposed_king`, `passive_rooks`, `weak_color_complex`, `back_rank_weak`, `overextended_pawns`, `backward_half_open`, `census()` — plus the standalone literature-definition pair `backward_pawns()` (Kmoch: strictly-ahead neighbors + enemy-pawn-controlled stop-square) and `isolated_pawns()`, both used by the suggest.py weakness-plan matrix and fact_sheet.py's WEAKNESSES sections. Also `knight_route`/`knight_route_conditional` (pawn-aware BFS route annotations). Pure geometry. |
| `suggest.py` | **THE FRONT DOOR — the position→plan suggester.** `./suggest.py "FEN"` or `./suggest.py game.pgn 24`; `--verify` for the closed loop. `build_menus(b)` builds the raw per-side candidate menus (shared by the numeric renderer `suggest_plans()` and `fact_sheet.py`'s prose renderer); PASS 1 state-triggered + the literature weakness-plan matrix (finding 16: isolani/backward/doubled/hanging-pawns, piece-gated) + PASS 2 situational (prophylaxis/simplify/avoid-trades/defense). OUTPOST and BREAK THE BISHOP PAIR candidates are per-square, each with a knight-route annotation. Effect-size ranking is corpus-derived where audited, prior otherwise. |
| `fact_sheet.py` | **The natural-language fact-sheet + control-prompt generator** (finding 16), for grounding-tested LLM narration. `build_fact_sheet(fen, pvs, rolls)` (the (fen, pvs, rolls) contract — never rolls; ASSESSMENT cp comes from the supplied top PV, static term-sum + SEE correction as the no-engine fallback) → ASSESSMENT (words) / POSITION READ (prose) / STRUCTURE (named only) / WEAKNESSES FOR WHITE·BLACK (present-only, no negative lines) / PLAN FOR WHITE·BLACK (jargon-free). `build_control_prompt(fen)` — same framing, zero facts, isolates genuine grounding from free association. FEN redacted to an opaque `POSITION-<hash>` id throughout. |
| `structures.py` | **The theory structure catalog**: 15 recognizers (carlsbad, isolani, hanging pawns, french advance, advance caro, mar del plata, benoni, maroczy, hedgehog, open sicilian, boleslavsky, stonewall, grünfeld center, spanish center, slav triangle), each written once White-owner and auto-mirrored; `classify(board)`. All ECO-validated (`experiments/studies/validate_structures.py`). |
| `experiments/studies/evidence_table.py` | The structure→plan evidence row builder (roadmap 1). Carlsbad row done → `carlsbad_row.jsonl` (15,163 structure games, both corpora, stage = none/launched/advanced/completed). |
| `experiments/studies/outpost_plan_v0.py` | **The hole/outpost plan** (plan-unit: concession → knight journey → anchored occupation → rent). 7,057 GM plan-units (20.9% of games!) → `outpost_plans.jsonl`. Laws: depth gradient 0.509/0.561/0.584 (4th/5th/6th rank); rim outposts worthless (0.496); f5 the best square in chess (0.630); self-conceded holes costliest (0.555 vs 0.540); median concession→occupation lag 14 plies; canonical route b1-c3-d5. Ready to graduate after review. |
| `data/lichess_elite_2023-01.pgn` | 311k elite games (Jan 2023). More months at database.nikonoel.fr. |
| `data/gm_classical.pgn` | **33,769 GM-vs-GM classical OTB games** (TWIC 1497–1653, Jul 2023–Jul 2026; both players titled GM; rapid/blitz/online excluded). Raw weeklies in `data/twic/`. |
| `data/studies/*.pgn` | The ground-truth annotated games: 3 minority-attack chapters (Larakepara study) + Arkell–de Wolf blind-test game. |
| `minority-attack/`, `minority-attack-gm/` | All detected minority-attack games, one PGN each with Plan* evidence headers + `index.jsonl`. Subfolders: `well-executed/` (static filter), `teaching-set/` (engine-certified; 50 Lichess / 3 GM). Verdicts in `engine_verified.jsonl`. |
| `experiments/studies/bad_bishop_escape.py` | The escape study (finding 4). Cases in `bad_bishop_cases.jsonl` (4,581, with entombed/outside class, resolution, route, score). |
| `experiments/studies/bishop_v0.py`, `bishop_v1.py` | Good-vs-bad-bishop exploitation theorem; v1 requires entombment. Honest negative: entombment requirement did NOT raise the good side's ~55% — conversion needs a second weakness (finding 7). |
| `closed_v0.py` | Closedness detector (finding 5): `skeleton()` (rams/central/tension/open files) + hermetic `is_closed`. |
| `experiments/studies/bishop_vs_knight_closed.py` | The B-vs-N study (finding 6): closedness x openness x entombment x pair/single. |
| `experiments/studies/weakness_census.py` | The two-weaknesses experiment (finding 7); imports `weaknesses.py`, so the census grows as detectors are added. |
| `verify.py` | **THE CLOSED LOOP** (finding 14, extended finding 16; contract ruling 2026-07-22): `verify_plan(fen, side, family, pvs, rolls, square=None, route_hops=None)` — **the (fen, pvs, rolls) contract: the library NEVER rolls, it only checks caller-supplied lines** (backend supplies its own engine/Maia lines; research harness rolls via `experiments/tools/rolls.py` or replays banked shards). Per-family horizons + random floors, tighter floor when square-scoped, route-scaled horizon for multi-hop journeys. TIMING (immediate/developing/long-term) split into `CONFIRMED-SOUND` vs `CONFIRMED-SOUND-LATER` with an `immediate_move` field. Graded verdict. Either leg may be None — degrades and says so. |
| `experiments/tools/rolls.py` | **The research harness's live roll producers — the ONLY place in the repo that reaches an engine or Maia at runtime.** `roll_engine` (MultiPV=4 @1M nodes via `engine_roll_helper.py` under chess-lab's venv, protobuf isolation), `roll_maia` (K=9 docker-pipe gated rollouts), `roll_both` -> the `{"pvs", "rolls"}` bank shape the verify/fact_sheet/suggest CLIs read. |
| `hierarchy.py` | **The pedagogy layer** (finding 13): MECHANISM/PLAN/CAMPAIGN, `compose()`, `curriculum()`. 7 campaigns with role-tagged members, composition edges colift-evidenced. |
| `experiments/studies/campaign_study.py` | Full-corpus campaign calibration (finding 13); the monotone absent<fragment<partial<full gradient + the material-at-start symptom control. Witnesses -> `campaign_study.jsonl`. |
| `experiments/studies/composition_evidence.py` | Which mechanisms NEST in which plans, by colift-vs-random (the campaign edges). |
| `experiments/studies/export_benchmark.py` | Freezes `benchmark_v1.jsonl` (4,000 positions, sha+git-pinned) from the banked argmax anchors. |
| `experiments/studies/ev_pass_a_multi.py`, `ev_pass_b_multi.py`, `ev_pass_c_multi.py` | Multi-line agreeability (finding 14): engine MultiPV=4 (eval-equal gate) + Maia K=16 (40-60 gate) + merged report. |
| `experiments/studies/kstudy_reduce.py`, `kstudy_extend.py` | K-study reducer (convergence curve, K*=9) + the K=8->16 extension (raw UCIs banked). |
| `gpu_benchmark/` | **The copy-ready benchmark kit** (finding 14, re-run finding 16): `benchmark_v1.jsonl` + `gpu_bench.py` (Maia/GPU) + `engine_bench.py` (engine/CPU) + `check_shards.py` + `reduce_agreement.py` + its own agent-facing `CLAUDE.md`. Self-contained; produces raw-UCI futures labeled back home. `reduce_agreement.py` is re-run whenever the grammar changes (banked `eng_shards`/`maia_shards` cover all 4,000 positions — no new engine/Maia calls needed to re-score under a new family). |
| `experiments/reports/agreement_report_v6.txt` | The full 4,000-position engine-confirm/Maia-typical table (finding 16), post-`backward_push`/`pair_break` grammar. Per-plan: engine-confirm %, random floor %, Maia-typical %, n. `pair_break` 82%/4% (20.5x, cleanest in the vocabulary), `backward_push` 39%/10% (3.9x, production tier), `simplification` 91% (highest absolute confirm). |

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
   (Carlsbad/minority attack) BUILT** (`experiments/studies/evidence_table.py`,
   `carlsbad_row.jsonl`): GM White-side — structure in 4.2% of games, launch
   24%, complete-given-launch 33%, score none 0.529 / launched 0.551 /
   completed 0.580. Stage scores re-confirm harvest-gating: Lichess
   advanced-but-no-lever = 0.466, WORSE than never launching. GM Black-side:
   launch 17.6%, completion 17.7% — the lever is systematically refused by
   GM defenders; the plan is effectively refuted at GM level. The structure
   RECOGNIZER layer for the rest of the table is `structures.py` (15
   theory-catalog recognizers, all ECO-fingerprint-validated on the GM
   corpus — see `experiments/studies/validate_structures.py`; notable: isolani most
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
