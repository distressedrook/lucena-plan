"""activity_progression — how the normalized (GM-percentile) activity
scores move through plies 8-20, full GM corpus (2026-07-23 user request:
"plot the progression ... and extract useful patterns; parallelize").

Per ply 8..20, aggregated over all games (8 workers, sums only — no
per-position rows kept):
  1. mean norm per piece TYPE (N/B/R/Q) — the development curves;
  2. mean SIDE score (mean of a side's piece norms), White vs Black —
     the tempo story;
  3. mean side score split by the game's eventual RESULT for that side
     (win / draw / loss) — does the ply-8-20 activity edge already carry
     outcome signal?

Output: research/experiments/reports/activity_progression.png + printed table.
Run: .venv/python research/experiments/studies/activity_progression.py [--games N]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core.board import Board as LBoard
from lucena_core import positional

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
OUT = ("/Users/avismara/Development/lucena/lucena-plans/research/experiments/"
       "reports/activity_progression.png")
PLIES = range(8, 21)
WORKERS = 8
SCORE = {"1-0": {"white": 1.0, "black": 0.0}, "0-1": {"white": 0.0, "black": 1.0},
         "1/2-1/2": {"white": 0.5, "black": 0.5}}
BUCKET = {1.0: "win", 0.5: "draw", 0.0: "loss"}


def chunk(offsets):
    # sums[ply] -> {"type:N": (sum, n), "side:white": (sum, n),
    #               "res:win": (sum, n), ...}
    sums = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    with open(PGN, encoding="latin-1") as f:
        for off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                result = game.headers.get("Result", "*")
                if result not in SCORE:
                    continue
                b = game.board()
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    if ply < PLIES.start:
                        continue
                    if ply >= PLIES.stop:
                        break
                    d = positional.analyze_positional(LBoard(b.fen()))
                    ft = d["terms"]["activity"]["features"]
                    for color in ("white", "black"):
                        pieces = ft.get(f"pieces_{color}", [])
                        if not pieces:
                            continue
                        for e in pieces:
                            c = sums[ply][f"type:{e['piece']}"]
                            c[0] += e["norm"]; c[1] += 1
                        side = sum(e["norm"] for e in pieces) / len(pieces)
                        c = sums[ply][f"side:{color}"]
                        c[0] += side; c[1] += 1
                        c = sums[ply][f"res:{BUCKET[SCORE[result][color]]}"]
                        c[0] += side; c[1] += 1
            except Exception:
                continue
    return {p: {k: tuple(v) for k, v in d.items()} for p, d in sums.items()}


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
    total = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    with Pool(WORKERS) as pool:
        for part in pool.imap_unordered(chunk, chunks):
            for ply, d in part.items():
                for k, (s, n) in d.items():
                    total[ply][k][0] += s
                    total[ply][k][1] += n

    def mean(ply, key):
        s, n = total[ply][key]
        return s / n if n else None

    plies = sorted(total)
    print(f"games: {len(offsets)}   plies {plies[0]}..{plies[-1]}")
    hdr = ["ply", "N", "B", "R", "Q", "White", "Black", "win", "draw", "loss"]
    print("  ".join(f"{h:>6}" for h in hdr))
    series = defaultdict(list)
    for p in plies:
        row = [p]
        for k in ("type:N", "type:B", "type:R", "type:Q",
                  "side:white", "side:black",
                  "res:win", "res:draw", "res:loss"):
            m = mean(p, k)
            series[k].append(m)
            row.append(m)
        print("  ".join(f"{v:>6}" if isinstance(v, int)
                        else f"{v:>6.3f}" for v in row))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    ax = axes[0]
    for k, label in (("type:N", "knights"), ("type:B", "bishops"),
                     ("type:R", "rooks"), ("type:Q", "queens")):
        ax.plot(plies, series[k], marker="o", label=label)
    ax.set_title("mean activity percentile by piece type")
    ax.set_xlabel("ply"); ax.set_ylabel("norm (GM percentile)")
    ax.legend(); ax.grid(alpha=0.3)
    ax = axes[1]
    ax.plot(plies, series["side:white"], marker="o", label="White")
    ax.plot(plies, series["side:black"], marker="o", label="Black")
    ax.set_title("mean side activity: White vs Black")
    ax.set_xlabel("ply"); ax.legend(); ax.grid(alpha=0.3)
    ax = axes[2]
    for k, label in (("res:win", "eventual win"), ("res:draw", "draw"),
                     ("res:loss", "eventual loss")):
        ax.plot(plies, series[k], marker="o", label=label)
    ax.set_title("side activity by eventual result")
    ax.set_xlabel("ply"); ax.legend(); ax.grid(alpha=0.3)
    fig.suptitle(f"normalized activity progression, plies 8-20 "
                 f"(GM corpus, {len(offsets)} games)")
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print(f"\nplot -> {OUT}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
