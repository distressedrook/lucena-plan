"""plan_frequency_by_strength — what plans actually get EXECUTED in Maia
rollouts, independent of the GM benchmark move, compared across opponent
strength bands (2400v2400 baseline vs 2400v1300 / 2400v1800).

Unlike reduce_agreement.py (does the GM's plan show up in rollouts?), this
just labels every rollout line for its own sake and tallies plan-family
frequency, then diffs the frequency distributions across shard sets to
surface which plans weaker opponents play into more/less often.

Parallel across shard files (one process per bench_XXXX.jsonl) — labeling
16 rollouts x ~25 plies is the bottleneck, not I/O.

    python3 plan_frequency_by_strength.py benchmark_v1.jsonl \
        maia_shards:2400v2400 maia_shards_2400v1800:2400v1800 maia_shards_2400v1300:2400v1300
"""
from __future__ import annotations

import collections
import glob
import json
import multiprocessing
import os
import sys

BENCH = {}  # populated per-worker by _init_worker


def _init_worker(bench_path):
    global BENCH
    import json as _json
    BENCH = {r["id"]: r for r in
             (_json.loads(l) for l in open(bench_path)) }


def _label_file(path):
    # imported inside the worker so each process gets its own module state
    import chess
    sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-plans/src")
    from plan_diff import labels

    def lab(fen, ucis, h=25, t=6):
        return labels(chess.Board(fen),
                      [chess.Move.from_uci(u) for u in ucis], h, t)

    def fams(ls):
        return {x.split(":", 1)[1].split(":")[0] for x in ls}

    fam_lines = collections.Counter()
    total_lines = 0
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        fen = BENCH[r["id"]]["fen"]
        for s in r["samples"]:
            fs = fams(lab(fen, s))
            for f in fs:
                fam_lines[f] += 1
            total_lines += 1
    return fam_lines, total_lines


def freq(bench_path, dirpath, workers):
    files = sorted(glob.glob(f"{dirpath}/bench_*.jsonl"))
    fam_lines = collections.Counter()
    total = 0
    with multiprocessing.Pool(workers, initializer=_init_worker,
                               initargs=(bench_path,)) as pool:
        for fc, n in pool.imap_unordered(_label_file, files):
            fam_lines.update(fc)
            total += n
    return fam_lines, total, len(files)


if __name__ == "__main__":
    bench_path = sys.argv[1]
    workers = min(len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity")
                  else multiprocessing.cpu_count(), 8)

    sets = []
    for arg in sys.argv[2:]:
        path, _, tag = arg.partition(":")
        tag = tag or path
        sets.append((tag, path))

    results = {}
    for tag, path in sets:
        fam_lines, total, nfiles = freq(bench_path, path, workers)
        results[tag] = (fam_lines, total)
        print(f"{tag}: {nfiles} shard files, {total} rollout lines", file=sys.stderr)

    allf = sorted(
        set().union(*[fc for fc, _ in results.values()]),
        key=lambda f: -sum(fc[f] for fc, _ in results.values()))

    header = f"{'plan':>22} | " + " | ".join(f"{tag:>14}" for tag, _ in sets)
    print(header)
    print("-" * len(header))
    for f in allf:
        row = []
        for tag, _ in sets:
            fc, total = results[tag]
            pct = 100 * fc[f] / total if total else 0.0
            row.append(f"{pct:5.1f}% ({fc[f]:>5})")
        print(f"{f:>22} | " + " | ".join(f"{r:>14}" for r in row))
