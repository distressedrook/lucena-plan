# benchmark_v1 — the benchmark runner kit (standalone)

**The job:** produce two kinds of *futures* for each of 4,000 frozen chess
positions and write the raw move sequences to shard files —

  1. **Maia leg** — K Maia3-2400 rollouts/position (`gpu_bench.py`, GPU).
  2. **Engine leg** — MultiPV=4 search lines/position (`engine_bench.py`,
     CPU cores; needed only for the AGREEABILITY benchmark, not for the
     Maia-lift/K\* calibration).

No chess theory, plan detection, or labeling happens here — this box is a
**futures factory**. The move sequences go back to the analysis machine,
where they're labeled under whatever plan grammar is current. The two legs
are keyed by the same `id` and merge trivially there.

This folder is self-contained: `python-chess` + a Maia backend (+ a UCI
engine for the engine leg) — nothing from the parent project.

**Which legs you need:**
- Maia-lift / per-structure K\* / P(plan|structure) priors  → **Maia leg only**.
- Multi-line *agreeability* (engine-equal-lines vs Maia vs GM) → **both legs**.

## What's here

| file | what |
|---|---|
| `benchmark_v1.jsonl` | **the frozen eval set** — 4,000 positions, one JSON/line: `id`, `fen`, `anchor`, `result`, `structures`, `kstudy` (bool), `actual_ucis` (the game's real continuation), `random_ucis` (a seeded control). **Never edit this file.** Its sha256 is pinned in the manifest. |
| `benchmark_v1.manifest.json` | provenance: source corpus, anchor scheme, seeds, sha256, git commit. |
| `gpu_bench.py` | **Maia-leg runner** (GPU). Produces `bench_XXXX.jsonl` shards of 50 positions. Resume-safe. |
| `engine_bench.py` | **engine-leg runner** (CPU). Produces `engine_XXXX.jsonl` shards. Resume-safe. |
| `check_shards.py` | sanity check either leg before shipping back (coverage, legality). |
| `reduce_agreement.py` | the merge+report — **runs on the analysis machine**, not here (it needs the plan grammar). Included for reference. |
| `requirements.txt` | `python-chess` + a note on the backends. |

## The commands

**Maia leg (GPU):**
```bash
python3 gpu_bench.py benchmark_v1.jsonl maia_shards/ --k 16
```
Rows: `{"id":"n1883_a30","k":16,"samples":[[uci,...] x16]}` — K rollouts of
25 plies. `--k 16` is the safe default; the k-study settled at **K\*=9**, so
`--k 10` captures nearly all signal at ~60% the cost if GPU time is tight.

**Engine leg (CPU cores — only for agreeability):**
```bash
python3 engine_bench.py benchmark_v1.jsonl eng_shards/ \
        --backend uci --engine /path/to/your/engine --multipv 4 --nodes 1000000
```
Rows: `{"id":"n1883_a30","pvs":[{"cp":29,"ucis":[...25...]}, x4]}` — the top
4 lines, extended to 25 plies, cp normalized to White. This leg is **CPU
search — it does NOT use the GPU**; run it on cores in parallel with the
Maia leg (or run it back on the analysis machine — the `id` keys make the
two independently mergeable). The random control is already inside
`benchmark_v1` (`random_ucis`), so the engine leg produces only the PVs.

Engine-leg comparability note: for the agreeability numbers to match the
home calibration, use the SAME engine we calibrate with. A different UCI
engine (e.g. Stockfish) is a *valid* self-consistent benchmark but its
eval-equal set differs, so it's not comparable to the home 120-position
result — label it as such.

## The backend (pick one)

The runner talks to Maia through one seam: `top_policy(fen) -> [(uci,
policy_prob), ...]`. Two implementations:

**A. docker (default)** — the lucena image, which already contains the
Maia3-2400 weights. Give it the GPU:

```bash
docker run -d --name lucena-app-1 --gpus all <lucena-image>
python3 gpu_bench.py benchmark_v1.jsonl out_shards/ --k 16 --backend docker
```

The container name defaults to `lucena-app-1` (override `--container`). The
weights live inside the image; copy the image over (`docker save | docker
load`) — that's the only large artifact to move.

**B. lc0 + weights** — if you'd rather run bare metal. `gpu_bench.py` has a
stub `Lc0Backend`; fill in `top_policy` to call your `lc0` with
`--verbose-move-stats` (or UCI `go nodes 1` + parse the per-move `P:`
policy from the info strings), returning the top-5 `(uci, policy)` pairs.
Then `--backend lc0`.

**Correctness bar for either backend:** `top_policy` must return moves
ranked by Maia **policy** (human-likeness), with the policy probability —
NOT engine eval, NOT rank only. The rollout uses the policy to decide where
a human choice is genuinely contested (the 40–60 rule below).

## What the rollout does (so you can trust it)

Each rollout walks 25 plies. At every position it asks Maia for the top-5
human moves. It plays Maia's favorite **unless** a second move is genuinely
competitive — `p_i / (p_1 + p_i) >= 0.40`, the "40–60 band" — in which case
it samples among the contested moves weighted by policy. So forced/obvious
positions are deterministic; real human decision points branch. Seeds are
derived from the position id (`n<game>_a<anchor>`), so **the same rollout is
reproducible on any machine** — two GPUs running disjoint shard ranges
produce the identical bank.

Duplicate rollouts among the K are DATA, not waste: a position with few
contested nodes concentrates its probability mass, and that concentration
is part of what we measure.

## When it's done

```bash
python3 check_shards.py benchmark_v1.jsonl maia_shards/            # maia leg
python3 check_shards.py benchmark_v1.jsonl eng_shards/  --engine   # engine leg
# each -> positions covered 4000/4000, illegal lines 0, COMPLETE
```

Then copy the shard folder(s) back to the analysis machine's
`chess-plans/experiments/` directory. The reducers there label the raw
moves under the current grammar and produce: per-plan lift with tight CIs
at 13× the current scale, per-structure-family K\*, the P(plan|structure)
priors (Maia leg), and — with both legs — the per-plan agreeability table
(`reduce_agreement.py`: engine-confirmation vs Maia-typicality vs the
random floor).

## Rules (for whoever/whatever runs this)

- **Do not modify `benchmark_v1.jsonl`.** It's a frozen eval set; changing
  positions breaks comparability with every past and future run. If you
  need different positions, that's `benchmark_v2`, exported on the analysis
  machine, not edited here.
- **Do not label or interpret rollouts here.** This box emits raw UCI move
  sequences. Plan naming is grammar-versioned and lives on the analysis
  machine — keeping it there is what lets one bank be re-scored under future
  grammars.
- **Backend must be policy-ranked Maia-2400.** A different model or an
  eval-ranked backend silently produces a different experiment.
- The whole run is ~1.6M Maia calls (4000 × 16 × 25). On a GPU that's
  roughly 1–2h; on CPU it's ~2 days. If it's taking days, the GPU isn't
  being used — check the container has `--gpus all`.
