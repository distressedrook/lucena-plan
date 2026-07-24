# Residual attribution v0 — can static features explain R? (2026-07-24)

**Question.** R = engine_cp − adjusted_material_cp (both White-POV; the
adjusted anchor is `lucena_core.metrics.material_stability`, SEE
quiescence). Can the deterministic positional family attribute R
per-position — "+1.0 = +0.7 material, +0.2 bishop pair, +0.1 outpost"?

**Answer up front: mostly no.** On quiet positions the entire static
family explains **R² ≈ 0.15** of R (held-out, seed-grouped split); an
unconstrained GBDT does no better than a linear model, so the bound is
the *features*, not the model class. Mean |unexplained R| is 45cp quiet /
70cp tense. Per-position sign errors are routine. The coach may use these
features as salience (which dimension characterises the position), but a
static-feature decomposition of the ENGINE'S MARGIN is not defensible at
this feature vocabulary — the compensation the engine prices is mostly
invisible to one-board geometry, even on quiet boards.

## Pipeline (all in studies/residual_attribution/)

1. `harvest_features.py` — 77,429 unique labeled positions: the 4,000
   benchmark roots + interiors at plies 2..10 along each banked MultiPV
   line (`eng_shards`). A position on a PV inherits the line's root cp
   (minimax consistency). |cp| ≤ 300 clip; features are 27 White−Black
   differentials (terms + norm/percentile metrics + flags + tempo).
2. `validate_labels.py` — the inheritance trick vs fresh 200k-node
   Stockfish, 60/stratum: **MAE 8–12cp through ply 8, 22cp at ply 10,
   bias ≈ 0**. Labels trusted; noise ≪ sd(R) = 89cp.
3. `model_residual.py` — three models, seed-grouped 80/20:
   linear (ridge) / additive monotone GBDT (interaction_cst=singletons —
   the would-be "speaker": pred = Σ fᵢ(xᵢ), exact attribution) /
   unconstrained GBDT (the ceiling instrument).
4. `surgery.py` — interventional faithfulness: minimal counterfactual
   boards (pair→knight swap; passer un-passed by an enemy-pawn file
   shift), both versions engine-labeled fresh, engine Δ vs model Δ.

## Results

| bucket (held-out) | n | sd(R) | linear | additive | GBDT |
|---|---|---|---|---|---|
| all | 15,430 | 89 | 0.147 | 0.140 | 0.134 |
| quiet | 7,723 | 67 | **0.148** | 0.141 | 0.127 |
| tense | 7,707 | 104 | 0.108 | 0.100 | 0.097 |
| quiet middlegame | 5,845 | 68 | 0.142 | 0.135 | 0.135 |
| quiet endgame | 535 | 65 | **0.255** | 0.241 | 0.031 |
| quiet opening | 1,343 | 62 | 0.129 | 0.132 | 0.125 |

- **GBDT ≈ additive ≈ linear everywhere** → no interaction structure the
  features expose; interpretability is free, but there is little to
  interpret. Adding tempo + the four PST-grade term cps moved quiet R²
  only 0.131 → 0.141–0.148 — the "features too coarse" hypothesis is dead
  at this vocabulary level.
- **Tactics own the residual**: |unexplained| 70cp tense vs 45cp quiet;
  R² drops 0.15 → 0.10 quiet → tense. The dynamism gate is doing real
  work — static attribution degrades exactly where the classifier says
  not to trust static reads.
- **Endgames are twice as attributable** (0.26 vs 0.14) — passers +
  structure are a bigger share of truth there. Attribution as a product
  feature is most honest in quiet endgames.
- Top ablations (speaker, quiet): bishop_pair +0.010, islands +0.007,
  king_safety_cp +0.007, attack_viability +0.007, open_files_held +0.005,
  activity +0.005. Everything else ≤ 0.003. Collinear clusters resolved
  as expected (king_safety_cp~king_danger 0.90, activity_cp~activity_mean
  0.88, center_cp~center_share 0.80, passer_count~passer_best 0.96).
- Mean R = +7.9cp ≈ the tempo, but `stm` ablates at +0.0005 — tempo is
  real in aggregate yet swamped per-position.

## Surgery (interventional faithfulness)

80 counterfactual pairs per class, both boards freshly engine-labeled
(200k nodes), both required quiet; comparison is engine Δeval vs the
speaker model's whole-vector Δprediction.

| surgery | n | corr(engineΔ, modelΔ) | engine Δ sd | model Δ sd |
|---|---|---|---|---|
| bishop pair → knight | 80 | **0.75** | 102cp | 29cp |
| passer un-passed (enemy pawn imported onto its file) | 80 | **0.55** | 87cp | 20cp |

Reading: attributions are DIRECTIONALLY causal (rankings correlate well
with the engine's own counterfactual), but magnitudes are compressed
3–4×: the engine prices "the pair" anywhere from ≈ −100 to +150cp by
context, while an additive per-position attribution can only serve the
corpus-mean shape. So a spoken attribution is honest as a SIGN and a
RANKING ("the pair is part of White's edge; the passer matters more
here"), and dishonest as a NUMBER ("+0.2 from the pair"). The passer
surgery deltas also include the donor-file damage, so 0.55 is a floor.

## Fixes to the static layer this study forced (lucena-core)

- `metrics._quiescent_material`: the greedy SEE chain walker tie-broke on
  move-generation order and forced captures without stand-pat — a
  position and its color-mirror settled up to 10 pawns apart. Replaced
  with capture-only negamax + stand-pat (order-invariant; mirror-exact).
  This is the anchor of R; the study was not runnable before the fix.
- `positional._center_term`: 1cp mirror asymmetry (float accumulation
  noise at a .5 rounding boundary) — micro-round before the integer round.
- Audit instrument: color-mirror anti-symmetry over 297 benchmark
  positions — now 0 violations across the whole metric family.

## Interpretation for the product

The right claim shape for the coach is NOT "your +0.5 is +0.2 pair +0.2
file". It is: material/adjusted-material as the anchor (trustworthy),
salience terms for WHICH dimension to talk about (already the LLD
contract), and for the margin itself: "the rest of White's edge is
concrete — it lives in the engine's lines, not in any single static
feature" — which this study makes a *measured*, defensible sentence.
The per-line theories path (`line_theories`: walk the engine's own
eval-equal lines to quiescence and read the settled terms) remains the
promising route to explaining R, because it looks where the compensation
actually cashes out — the future — instead of asking one static board to
contain it.
