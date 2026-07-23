"""plan_when_winning — filter Maia rollout lines to those where the FIRST
MOVER ends up winning, then compare what plans get executed, across
opponent-strength bands. "First mover" = the side to move in the
position's starting FEN (per user ruling 2026-07-22: shard convention is
first-mover=2400[-conditioned], second-mover=weaker OppoElo).

Static positional eval (lucena_engine.positional, term-sum, no search) is
used for speed at this scale (~192k lines) -- not a search-verified
result, a fast directional signal for "who ended up ahead."

Parallel across shard files.

    python3 plan_when_winning.py benchmark_v1.jsonl \
        maia_shards:2400v2400 maia_shards_2400v1800:2400v1800 maia_shards_2400v1300:2400v1300 \
        [--thresh 150]
"""
from __future__ import annotations

import collections
import glob
import json
import multiprocessing
import os
import sys

ENGINE_PY = "/Users/avismara/Development/lucena/engine/python"
SRC = "/Users/avismara/Development/lucena/lucena-plans/src"

BENCH = {}


def _init_worker(bench_path):
    global BENCH
    BENCH = {r["id"]: r for r in (json.loads(l) for l in open(bench_path))}


def _process_file(args):
    path, thresh = args
    import chess
    sys.path.insert(0, ENGINE_PY)
    sys.path.insert(0, SRC)
    from lucena_core.positional import analyze_positional
    from lucena_core.board import Board as LBoard
    from plan_diff import labels

    def lab(fen, ucis, h=25, t=6):
        return labels(chess.Board(fen),
                      [chess.Move.from_uci(u) for u in ucis], h, t)

    def fams(ls):
        return {x.split(":", 1)[1].split(":")[0] for x in ls}

    def static_cp(final_fen):
        pos = analyze_positional(LBoard(final_fen))
        return sum(t["cp"] for t in pos["terms"].values())

    win_fam = collections.Counter()
    win_lines = 0
    lose_fam = collections.Counter()
    lose_lines = 0
    even_lines = 0
    total = 0

    if not os.path.exists(path):
        return win_fam, win_lines, lose_fam, lose_lines, even_lines, total

    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        fen = BENCH[r["id"]]["fen"]
        first_mover = chess.Board(fen).turn  # True=White
        for s in r["samples"]:
            total += 1
            board = chess.Board(fen)
            for u in s:
                try:
                    board.push_uci(u)
                except ValueError:
                    break
            cp_white = static_cp(board.fen())
            cp_first_mover = cp_white if first_mover else -cp_white
            fs = fams(lab(fen, s))
            if cp_first_mover >= thresh:
                win_lines += 1
                for f in fs:
                    win_fam[f] += 1
            elif cp_first_mover <= -thresh:
                lose_lines += 1
                for f in fs:
                    lose_fam[f] += 1
            else:
                even_lines += 1
    return win_fam, win_lines, lose_fam, lose_lines, even_lines, total


def run(bench_path, dirpath, thresh, workers):
    files = sorted(glob.glob(f"{dirpath}/bench_*.jsonl"))
    win_fam = collections.Counter()
    lose_fam = collections.Counter()
    win_lines = lose_lines = even_lines = total = 0
    tasks = [(f, thresh) for f in files]
    with multiprocessing.Pool(workers, initializer=_init_worker,
                               initargs=(bench_path,)) as pool:
        for wf, wl, lf, ll, el, tot in pool.imap_unordered(_process_file, tasks):
            win_fam.update(wf)
            lose_fam.update(lf)
            win_lines += wl
            lose_lines += ll
            even_lines += el
            total += tot
    return win_fam, win_lines, lose_fam, lose_lines, even_lines, total


if __name__ == "__main__":
    bench_path = sys.argv[1]
    thresh = 150
    posargs = []
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--thresh":
            thresh = int(sys.argv[i + 1]); i += 2
        else:
            posargs.append(sys.argv[i]); i += 1

    sets = []
    for arg in posargs:
        path, _, tag = arg.partition(":")
        sets.append((tag or path, path))

    workers = min(multiprocessing.cpu_count(), 8)

    results = {}
    for tag, path in sets:
        win_fam, win_lines, lose_fam, lose_lines, even_lines, total = run(
            bench_path, path, thresh, workers)
        results[tag] = (win_fam, win_lines, lose_fam, lose_lines, even_lines, total)
        print(f"{tag}: {total} lines | first-mover WIN {win_lines} "
              f"({100*win_lines/total:.1f}%) | LOSE {lose_lines} "
              f"({100*lose_lines/total:.1f}%) | EVEN {even_lines} "
              f"({100*even_lines/total:.1f}%)  [thresh={thresh}cp]", file=sys.stderr)

    allf = sorted(
        set().union(*[wf for wf, *_ in results.values()]),
        key=lambda f: -sum(wf[f] for wf, *_ in results.values()))

    header = f"{'plan':>24} | " + " | ".join(
        f"{tag+' WIN':>13} | {tag+' LOSE':>13} | {'delta pp':>8}" for tag, _ in sets)
    print(header)
    print("-" * len(header))
    for f in allf:
        row = []
        for tag, _ in sets:
            win_fam, win_lines, lose_fam, lose_lines, *_ = results[tag]
            wp = 100 * win_fam[f] / win_lines if win_lines else 0.0
            lp = 100 * lose_fam[f] / lose_lines if lose_lines else 0.0
            row.append(f"{wp:5.1f}%({win_fam[f]:>5}) | {lp:5.1f}%({lose_fam[f]:>5}) | {wp-lp:+6.1f}")
        print(f"{f:>24} | " + " | ".join(row))
