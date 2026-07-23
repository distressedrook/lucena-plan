"""center_control_outcome — does middlegame center control predict winning?
(2026-07-23 user request: "See if this score is consistently high in the
middlegames on the games that were won" — the region_control efficacy test,
same instrument as activity_outcome_phase.)

Per game, over MIDDLEGAME plies only (real phase classifier + hysteresis,
plies 8-80 step 2), two per-game statistics from region_control's center
share (White's share of d4/e4/d5/e5, attacker+occupation weighted):
  mean_share    — average center control through the middlegame
  hold_frac     — the CONSISTENCY stat: fraction of middlegame samples
                  with share >= 0.55 (holding the center, not just
                  visiting it)
Both tested against White's score: Pearson r, decile dose-response, and
the by-result group means the question asks for directly.

Output: printed tables + research/experiments/reports/center_control_outcome.png
Run: .venv/python research/experiments/studies/center_control_outcome.py [--games N]
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core import positional
from lucena_core.reads import game_phase

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
OUT = ("/Users/avismara/Development/lucena/lucena-plans/research/experiments/"
       "reports/center_control_outcome.png")
RANK = {"opening": 0, "middlegame": 1, "endgame": 2}
MAX_PLY = 80
STEP = 2
HOLD = 0.55
WORKERS = 8
WSCORE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}


def chunk(offsets):
    rows = []
    with open(PGN, encoding="latin-1") as f:
        for off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                result = game.headers.get("Result", "*")
                if result not in WSCORE:
                    continue
                b = game.board()
                shares = []
                rank = 0
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    if ply > MAX_PLY:
                        break
                    if ply < 8 or ply % STEP:
                        continue
                    fen = b.fen()
                    rank = max(rank, RANK[game_phase(fen)["phase"]])
                    if rank != 1:                 # middlegame only
                        continue
                    shares.append(
                        positional.region_control(fen)["center"]["white"])
                if len(shares) < 3:               # too little middlegame
                    continue
                rows.append({
                    "score": WSCORE[result],
                    "mean": sum(shares) / len(shares),
                    "hold": sum(1 for s in shares if s >= HOLD) / len(shares),
                })
            except Exception:
                continue
    return rows


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else 0.0


def main(max_games):
    offsets = []
    with open(PGN, encoding="latin-1") as f:
        while True:
            off = f.tell()
            line = f.readline()
            if not line:
                break
            if line.startswith("[Event "):
                offsets.append(off)
                if max_games and len(offsets) >= max_games:
                    break
    chunks = [offsets[i::WORKERS] for i in range(WORKERS)]
    rows = []
    with Pool(WORKERS) as pool:
        for part in pool.imap_unordered(chunk, chunks):
            rows.extend(part)
    print(f"games with a middlegame: {len(rows)}")

    # the direct answer: by-result group means (White's perspective; Black
    # wins mirror by symmetry of the share)
    print("\n  result (White)   mean center share   hold-frac (>= 0.55)")
    for label, sc in (("won", 1.0), ("drew", 0.5), ("lost", 0.0)):
        sel = [r for r in rows if r["score"] == sc]
        if sel:
            m = sum(r["mean"] for r in sel) / len(sel)
            h = sum(r["hold"] for r in sel) / len(sel)
            print(f"  {label:>6} (n={len(sel):>5})     {m:.3f}"
                  f"               {h:.3f}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, key, label in ((axes[0], "mean", "mean middlegame center share"),
                           (axes[1], "hold", f"hold-frac (share >= {HOLD})")):
        pts = sorted((r[key], r["score"]) for r in rows)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = pearson(xs, ys)
        print(f"\n== {label} ==")
        print(f"  Pearson r vs White score = {r:+.3f}")
        dec = len(pts) // 10
        centers, means = [], []
        for i in range(10):
            seg = pts[i * dec:(i + 1) * dec] if i < 9 else pts[9 * dec:]
            m = sum(p[1] for p in seg) / len(seg)
            centers.append(sum(p[0] for p in seg) / len(seg))
            means.append(m)
            print(f"    decile {i}  [{seg[0][0]:.3f} .. {seg[-1][0]:.3f}]"
                  f"   {m:.3f}")
        ax.plot(centers, means, marker="o")
        ax.axhline(0.5, color="gray", lw=0.8, ls="--")
        ax.set_title(f"{label}\nr = {r:+.3f}")
        ax.set_xlabel(label)
    axes[0].set_ylabel("mean White score")
    fig.suptitle(f"middlegame center control vs outcome (GM corpus, "
                 f"{len(rows)} games)")
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print(f"\nplot -> {OUT}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
