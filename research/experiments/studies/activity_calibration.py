"""activity_calibration — fit the 0-1 activity normalization to GM practice
(2026-07-23 user request: "practical range stretched to use the whole
[0,1]").

The theoretical bounds (worst PST + zero mobility .. best PST + geometric
mobility ceiling) compress real pieces into ~0.3-0.7 — the extremes never
occur in play. This study samples the GM corpus, collects the RAW per-piece
activity scores (lucena_core.positional._activity_term's `score`: tapered
PeSTO placement + weighted mobility) per piece type, and prints per-type
quantile grids (21 points, p0..p100 step 5) for embedding in positional.py.

The resulting `norm` is a PERCENTILE: 0.62 = "more active than 62% of
same-type pieces in sampled GM positions" — the whole [0,1] is used by
construction, and the number has a plain-language reading.

Sampling: every 8th ply from ply 12 (skip the book shuffle), all games.

Run: .venv/python research/experiments/studies/activity_calibration.py [--games N]
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-core/python")
from lucena_core.board import Board as LBoard
from lucena_core import positional

PGN = "/Users/avismara/Projects/active/lucena/lucena-plans/research/data/gm_classical.pgn"
START_PLY = 12
EVERY = 8
WORKERS = 8
QSTEP = 5   # quantile grid: p0, p5, ... p100


def chunk(offsets):
    scores = {"N": [], "B": [], "R": [], "Q": []}
    with open(PGN, encoding="latin-1") as f:
        for off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                b = game.board()
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    if i < START_PLY or (i - START_PLY) % EVERY:
                        continue
                    d = positional.analyze_positional(LBoard(b.fen()))
                    ft = d["terms"]["activity"]["features"]
                    for color in ("white", "black"):
                        for e in ft.get(f"pieces_{color}", []):
                            scores[e["piece"]].append(e["score"])
            except Exception:
                continue
    return scores


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
    merged = {"N": [], "B": [], "R": [], "Q": []}
    with Pool(WORKERS) as pool:
        for part in pool.imap_unordered(chunk, chunks):
            for k, v in part.items():
                merged[k].extend(v)
    print(f"# sampled from {len(offsets)} games "
          f"({ {k: len(v) for k, v in merged.items()} } piece observations)")
    print("_ACT_QUANTILES = {")
    for pc in ("N", "B", "R", "Q"):
        v = sorted(merged[pc])
        qs = [v[min(len(v) - 1, round(q / 100 * (len(v) - 1)))]
              for q in range(0, 101, QSTEP)]
        print(f'    "{pc}": {[round(x, 1) for x in qs]},')
    print("}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
