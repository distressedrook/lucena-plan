"""activity_outcome_phase — the activity-differential vs outcome numbers
RE-RUN on the real phase classifier (2026-07-23, follows activity_outcome:
that study used ply windows 8-20 / 21-40 / 41-60 as a phase proxy; this one
buckets every sampled position by lucena_core.reads.game_phase with stream
hysteresis — a game never returns to an earlier phase).

Same instrument otherwise: per game, the White-minus-Black mean piece
activity percentile averaged within each PHASE, tested against White's
score (Pearson r + decile dose-response).

Output: printed tables + research/experiments/reports/activity_outcome_phase.png.
Run: .venv/python research/experiments/studies/activity_outcome_phase.py [--games N]
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core.board import Board as LBoard
from lucena_core import positional
from lucena_core.reads import game_phase

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
OUT = ("/Users/avismara/Development/lucena/lucena-plans/research/experiments/"
       "reports/activity_outcome_phase.png")
PHASES = ("opening", "middlegame", "endgame")
RANK = {p: i for i, p in enumerate(PHASES)}
MAX_PLY = 80
STEP = 2
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
                sums = {p: [0.0, 0] for p in PHASES}
                b = game.board()
                rank = 0                      # hysteresis: phases only advance
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    if ply > MAX_PLY:
                        break
                    if ply < 8 or ply % STEP:
                        continue
                    fen = b.fen()
                    rank = max(rank, RANK[game_phase(fen)["phase"]])
                    phase = PHASES[rank]
                    d = positional.analyze_positional(LBoard(fen))
                    ft = d["terms"]["activity"]["features"]
                    side = {}
                    for color in ("white", "black"):
                        pieces = ft.get(f"pieces_{color}", [])
                        if pieces:
                            side[color] = (sum(e["norm"] for e in pieces)
                                           / len(pieces))
                    if len(side) < 2:
                        continue
                    sums[phase][0] += side["white"] - side["black"]
                    sums[phase][1] += 1
                row = {"score": WSCORE[result]}
                for p, (s, n) in sums.items():
                    row[p] = s / n if n else None
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
    fig, axes = plt.subplots(1, len(PHASES), figsize=(16, 5), sharey=True)

    for ax, phase in zip(axes, PHASES):
        pts = [(r[phase], r["score"]) for r in rows if r[phase] is not None]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = pearson(xs, ys)
        print(f"\n== {phase} (n={len(pts)}) ==")
        print(f"  Pearson r(activity diff, White score) = {r:+.3f}")
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
        ax.set_title(f"{phase}\nr = {r:+.3f}")
        ax.set_xlabel("mean activity diff (W - B)")
    axes[0].set_ylabel("mean White score")
    fig.suptitle(f"activity differential vs outcome, REAL phase classifier "
                 f"(GM corpus, {len(rows)} games, hysteresis, plies 8-{MAX_PLY})")
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print(f"\nplot -> {OUT}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
