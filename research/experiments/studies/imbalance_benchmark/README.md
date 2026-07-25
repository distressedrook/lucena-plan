# General material-imbalance benchmark (2026-07-24)

Generalizes the Q-for-two-minors probe (80 positions) to **every** kind of
traded-material imbalance across the full GM corpus, and benchmarks the
`fact_sheet._compensation_read` on real, engine-verified compensation.

## Method

`build_imbalance_benchmark.py` — parallel, 3 phases (finding 22 infra):

1. **Harvest** (engine-free, 10 workers): walk every mainline of
   `gm_classical.pgn` (33,769 GM games); first position past move 12 where the
   material is *traded* — some piece type White has more of AND some type Black
   has more of (exchange, Q-for-pieces, minors-vs-rook, piece-for-pawns, ...).
   Value-neutral B-vs-N swaps filtered unless a major piece or ≥100cp is at
   stake. One position per game, deduped → **23,673 imbalance positions**.
2. **Label** (Stockfish, 9 workers): MultiPV=4 @1M nodes; sample of 1,200.
   Cached to `labeled_cache.jsonl` (crash-safe; phase 3 re-runs off it).
3. **Read + freeze**: drop |engine cp| > 100 (decisive — those are just
   winning), run the compensation read on the equalish survivors, freeze to
   `imbalance_benchmark.jsonl` (one position: fen, type, naive_cp, engine_cp,
   top ucis, our read).

## Results — STRATIFIED run (2295 labeled, ≤150/type, `STRATIFY=1`)

The authoritative run: 16 imbalance types, capped at 150 each so the sharp
major-piece imbalances get real n (an earlier uniform 1,200-sample drowned them
under `other`/`minor_mixed`). Harvest = first-position-per-type-per-game →
66,407 imbalance positions. **918 equalish (40%), 1,375 dropped as decisive.**

**Finding 1 — equalish rate FALLS with sharpness (corrects the uniform run's
inflated "70%").** The sharper the material trade, the more often one side
simply miscalculated:

| band | types | equalish |
|---|---|---|
| value-even / subtle | other 73%, minor_mixed 63%, Q_vs_mixed 59% | ~60–73% |
| exchange-class | exchange 42%, exchange_for_pawns 37%, 2minors_vs_rook 32% | ~30–42% |
| queen sacs | Q_vs_2rooks 35%, Q_vs_R+minor 30%, **Q_vs_2minors 16%** | ~16–35% |

Q-for-two-minors at **16% equalish** (24/150) independently confirms the
earlier dedicated probe: this imbalance is usually just winning for the queen.

**Finding 2 — where compensation IS real, static features name the majority.**
Read fired on **207/918 (23%)**: static-explained **119 (57%)**, concrete
**88 (43%)**, null 711. Activity is the workhorse for queen sacs (the down side
has more, more-active pieces): `Q_vs_R+minor` activity 12, `double_exchange`
activity 10.

**Finding 3 — the line-walk resolves 93% of "concrete".** Of the 88 concrete:
`regained 61 · harvest 19 · pressure 2 · dynamic 6` — only **6 stay
irreducibly dynamic**. Across all 207 fired compensations, **201 (97%)** carry
a specific board reason. Magnitude: full 189 · partial 18.

## The line-walk: "concrete" is not a dead end (2026-07-24)

The 49 positions the read first called `concrete` ("no static feature explains
it") were then resolved by WALKING the engine lines — `_concrete_from_lines`
reads `line_theories` (each PV to quiescence, with SEE-settled material +
durable terms) plus the root settled material and classifies:

| kind | n / 88 | meaning |
|---|---|---|
| **regained** | 61 | the deficit CLOSES down a line — it wins the material back (names the move) |
| **harvest** | 19 | a term only decisive at the endpoint survives across lines (finding 2) |
| **pressure** | 2 | claws material back but stays nominally down — names mechanism + material + move |
| **dynamic** | 6 | genuinely irreducible — a standing threat, the honest "read the board" |

(The `regained`/`pressure` split gate is "does the deficit close to at worst a
pawn down" — `best_leaf >= -100`, not "near even": a line that wins the material
back AND MORE is fully regained, not pressure, else the sentence contradicts
itself with "wins back a rook … though still down".)

**47 of 49 (96%) of the opaque `concrete` bucket now carries a specific,
calculated reason; only 2 stay irreducibly dynamic.** So across the 96 fired
compensations, 94 (98%) get a concrete explanation — the compensation is either
a named static form, or a named line-mechanism (regained material via a move,
a harvest term, or continuing pressure). Wording states the CHESS fact, never
"the engine's lines" (owner 2026-07-24: "I don't wanna bring up engine lines").
Example strings on ground truth:

- *White is down the exchange — full comp — the material comes straight back with **Ra7**.*
- *White is down two pawns — full comp — the play brings **more active pieces**.*
- *White is down a rook for two pawns — full comp — lasting pressure claws the material back (**Qe7+**), though White stays nominally down.*

Real coaching sentences the read produced on ground truth:

- *White is down a rook and a pawn for a bishop — full compensation — pieces far more active.*
- *Black is down a knight for a pawn — full compensation — holds a space bind.*
- *White is down the exchange — full compensation — the material comes straight back with Ra7.*
- *Black is down a rook — full compensation — pieces far more active, White's passive.*

## Initiative, computed and validated (2026-07-25)

`src/initiative.py` — the deterministic initiative score (owner: "can we build
a deterministic system to calculate initiative? Go figure."). Literature-
grounded definition ("threats that cannot be ignored; the currency is tempo;
the initiative is arithmetic about forcing moves"): STATIC component from
geometry only (tempo-weighted safe checks, SEE≥0 captures, loose-piece
threats, restriction) + LINE component from the caller's pvs (forcing-fraction
of each side's moves in the eval-equal PVs — "does best play keep forcing").
Weights prior-tier; anti-symmetric under mirror (exact).

**Validated discriminatively** (`validate_initiative.py`, n=1,581 real-deficit
positions from the labeled cache): does the underdog's initiative
differential predict whether the compensation HELD (engine equalish) vs
FAILED (decisive for the material-up side)?

    STATIC-only AUC 0.673   ·   COMBINED AUC 0.740

Hold-rate ladder by underdog initiative differential (combined), monotone:

    < −0.3 → 15%   ·  −0.3..−0.1 → 26%  ·  ±0.1 → 54%
    +0.1..+0.3 → 72%  ·  > +0.3 → 86%

Down material with a big initiative edge, you hold 86% of the time; down
material AND out-forced, 15%. Caveats: the static AUC (0.673) is the fully
engine-free number; the combined score's forcing-fraction is read from the
same MultiPV bank that supplies the label's eval (not label-circular — the
fraction is about move TYPES, not cp — but same-bank). Not yet wired into
the fact sheet.

## Files

- `build_imbalance_benchmark.py` — the pipeline (reproducible; `SEED=17`).
- `imbalance_benchmark.jsonl` — the frozen benchmark (845 equalish positions).
- `report.txt` — the per-type table from the run.
- `labeled_cache.jsonl` — intermediate engine labels (gitignored; regenerable).
