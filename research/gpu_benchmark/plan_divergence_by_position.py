"""plan_divergence_by_position — per-position "what plan actually gets
executed" comparison across opponent-strength shards, ranked by how much
the plan-family distribution shifts between bands.

The global aggregate (plan_frequency_by_strength.py) washes out real
per-position effects because most families aren't even candidates on most
boards. This instead computes, for EACH position, the family-frequency
vector over its K=16 rollout samples in each shard set, scores the shift
between bands with total-variation distance, and prints the positions
where opponent strength changes what actually gets played the most.

Parallel across shard files (same bench_XXXX.jsonl basename is assumed
aligned across the three shard directories -- same benchmark split).

    python3 plan_divergence_by_position.py benchmark_v1.jsonl \
        maia_shards:2400v2400 maia_shards_2400v1800:2400v1800 [maia_shards_2400v1300:2400v1300] \
        [--top 30]
"""
from __future__ import annotations

import collections
import glob
import json
import multiprocessing
import os
import sys

BENCH = {}


def _init_worker(bench_path):
    global BENCH
    BENCH = {r["id"]: r for r in (json.loads(l) for l in open(bench_path))}


def _process_file(args):
    basename, dirpaths_by_tag, baseline_tag = args
    import chess
    sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
    from plan_diff import labels

    def lab(fen, ucis, h=25, t=6):
        return labels(chess.Board(fen),
                      [chess.Move.from_uci(u) for u in ucis], h, t)

    def fams(ls):
        return {x.split(":", 1)[1].split(":")[0] for x in ls}

    per_tag = {}
    for tag, dirpath in dirpaths_by_tag.items():
        path = f"{dirpath}/{basename}"
        recs = {}
        if os.path.exists(path):
            for line in open(path):
                if line.strip():
                    r = json.loads(line)
                    recs[r["id"]] = r
        per_tag[tag] = recs

    ids = set(per_tag[baseline_tag])
    for tag in per_tag:
        ids &= set(per_tag[tag])

    out = []
    for _id in ids:
        fen = BENCH[_id]["fen"]
        dist = {}
        for tag, recs in per_tag.items():
            k = len(recs[_id]["samples"])
            c = collections.Counter()
            for s in recs[_id]["samples"]:
                for f in fams(lab(fen, s)):
                    c[f] += 1
            dist[tag] = {f: c[f] / k for f in c}
        out.append((_id, fen, dist))
    return out


def tv_distance(a, b):
    allf = set(a) | set(b)
    return 0.5 * sum(abs(a.get(f, 0.0) - b.get(f, 0.0)) for f in allf)


if __name__ == "__main__":
    bench_path = sys.argv[1]
    top_n = 30
    posargs = []
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--top":
            top_n = int(sys.argv[i + 1])
            i += 2
        else:
            posargs.append(sys.argv[i])
            i += 1

    dirpaths_by_tag = {}
    for arg in posargs:
        path, _, tag = arg.partition(":")
        tag = tag or path
        dirpaths_by_tag[tag] = path
    baseline_tag = next(iter(dirpaths_by_tag))
    compare_tags = [t for t in dirpaths_by_tag if t != baseline_tag]

    basenames = sorted(os.path.basename(p) for p in
                        glob.glob(f"{dirpaths_by_tag[baseline_tag]}/bench_*.jsonl"))

    workers = min(multiprocessing.cpu_count(), 8)
    tasks = [(b, dirpaths_by_tag, baseline_tag) for b in basenames]

    all_rows = []
    with multiprocessing.Pool(workers, initializer=_init_worker,
                               initargs=(bench_path,)) as pool:
        for chunk in pool.imap_unordered(_process_file, tasks):
            all_rows.extend(chunk)
    print(f"{len(all_rows)} positions scored", file=sys.stderr)

    scored = []
    for _id, fen, dist in all_rows:
        base = dist[baseline_tag]
        per_cmp = {t: tv_distance(base, dist[t]) for t in compare_tags}
        score = max(per_cmp.values())
        scored.append((score, _id, fen, base, dist, per_cmp))

    scored.sort(key=lambda x: -x[0])

    print(f"\ntop {top_n} positions by max TV-distance from {baseline_tag}:\n")
    for score, _id, fen, base, dist, per_cmp in scored[:top_n]:
        print(f"{_id}  score={score:.2f}  {' '.join(f'{t}={v:.2f}' for t, v in per_cmp.items())}")
        print(f"  fen: {fen}")
        for tag in dirpaths_by_tag:
            d = dist[tag]
            top = sorted(d.items(), key=lambda kv: -kv[1])[:5]
            print(f"  {tag:>12}: " + ", ".join(f"{f}={v:.2f}" for f, v in top))
        print()
