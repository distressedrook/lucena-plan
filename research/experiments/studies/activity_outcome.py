"""activity_outcome — does the ACTIVITY DIFFERENTIAL predict who wins?
(2026-07-23 user request, following activity_progression: the progression
study aggregated each side independently, which nearly washed the outcome
signal out; the honest test is WITHIN-GAME — the same game's White-minus-
Black mean piece-activity percentile against White's score.)

Per game, the side-activity differential (mean piece norm, White - Black)
is averaged over three phase windows:
    opening      plies  8-20
    middlegame   plies 21-40
    late         plies 41-60
and each window's differential is tested against White's score two ways:
  1. Pearson r (differential vs score 0/0.5/1);
  2. the dose-response curve: White's mean score per differential decile
     (the SIMPLIFY/AVOID-TRADES evidence style — the curve IS the finding).

Output: printed tables + research/experiments/reports/activity_outcome.png.
Run: .venv/python research/experiments/studies/activity_outcome.py [--games N]
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-core/python")
from lucena_core.board import Board as LBoard
from lucena_core import positional

PGN = "/Users/avismara/Projects/active/lucena/lucena-plans/research/data/gm_classical.pgn"
OUT = ("/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/"
       "reports/activity_outcome.png")
WINDOWS = {"opening 8-20": (8, 20), "middlegame 21-40": (21, 40),
           "late 41-60": (41, 60)}
STEP = 2          # evaluate every 2nd ply inside a window (halves the cost;
                  # the differential moves slowly)
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
                sums = {k: [0.0, 0] for k in WINDOWS}
                b = game.board()
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    if ply > 60:
                        break
                    if ply < 8 or ply % STEP:
                        continue
                    d = positional.analyze_positional(LBoard(b.fen()))
                    ft = d["terms"]["activity"]["features"]
                    side = {}
                    for color in ("white", "black"):
                        pieces = ft.get(f"pieces_{color}", [])
                        if pieces:
                            side[color] = (sum(e["norm"] for e in pieces)
                                           / len(pieces))
                    if len(side) < 2:
                        continue
                    diff = side["white"] - side["black"]
                    for k, (lo, hi) in WINDOWS.items():
                        if lo <= ply <= hi:
                            sums[k][0] += diff
                            sums[k][1] += 1
                row = {"score": WSCORE[result]}
                for k, (s, n) in sums.items():
                    row[k] = s / n if n else None
                rows.append(row)
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
    print(f"games scored: {len(rows)}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(WINDOWS), figsize=(16, 5), sharey=True)

    for ax, wname in zip(axes, WINDOWS):
        pts = [(r[wname], r["score"]) for r in rows if r[wname] is not None]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = pearson(xs, ys)
        print(f"\n== {wname} (n={len(pts)}) ==")
        print(f"  Pearson r(activity diff, White score) = {r:+.3f}")
        # dose-response: score by differential decile
        order = sorted(pts)
        dec = len(order) // 10
        centers, means = [], []
        print("  decile  diff-range           mean White score")
        for i in range(10):
            seg = order[i * dec:(i + 1) * dec] if i < 9 else order[9 * dec:]
            lo, hi = seg[0][0], seg[-1][0]
            m = sum(p[1] for p in seg) / len(seg)
            centers.append(sum(p[0] for p in seg) / len(seg))
            means.append(m)
            print(f"    {i}    [{lo:+.3f} .. {hi:+.3f}]   {m:.3f}  "
                  f"(n={len(seg)})")
        ax.plot(centers, means, marker="o")
        ax.axhline(0.5, color="gray", lw=0.8, ls="--")
        ax.axvline(0.0, color="gray", lw=0.8, ls="--")
        ax.set_title(f"{wname}\nr = {r:+.3f}")
        ax.set_xlabel("mean activity diff (W - B)")
    axes[0].set_ylabel("mean White score")
    fig.suptitle(f"activity differential vs outcome (GM corpus, "
                 f"{len(rows)} games)")
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print(f"\nplot -> {OUT}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
