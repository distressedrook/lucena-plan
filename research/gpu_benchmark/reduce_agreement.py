"""reduce_agreement — merge the two benchmark legs into the agreeability
report. RUNS ON THE ANALYSIS MACHINE (needs plan_diff / the current
grammar), not the GPU box: the whole point of banking raw UCIs is that the
grammar lives here.

Inputs:
  benchmark_v1.jsonl       actual_ucis + random_ucis (the GM leg + floor)
  eng_shards/engine_*.jsonl  MultiPV lines per id (engine_bench.py)
  maia_shards/bench_*.jsonl  K rollouts per id (gpu_bench.py)

Labels every line under the current grammar and reports, per plan family,
the metric that survives the union-saturation problem (per-plan, not
any-overlap):
  engine confirmation  P(GM's plan in an EVAL-EQUAL engine line)
  maia typicality      P(GM's plan in >= FLOORx of K rollouts)
both vs the benchmark's own random control.

    python3 reduce_agreement.py benchmark_v1.jsonl eng_shards/ maia_shards/
"""
from __future__ import annotations

import collections
import glob
import json
import statistics
import sys

import chess

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
from plan_diff import labels

EQUAL_BAND = 50


def lab(fen, ucis, h=25, t=6):
    return labels(chess.Board(fen),
                  [chess.Move.from_uci(u) for u in ucis], h, t)


def fams(ls):
    return {x.split(":", 1)[1].split(":")[0] for x in ls}


def load(dirpath, pattern):
    out = {}
    for p in sorted(glob.glob(f"{dirpath}/{pattern}")):
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                out[r["id"]] = r
    return out


if __name__ == "__main__":
    bench = {json.loads(l)["id"]: json.loads(l) for l in open(sys.argv[1])}
    eng = load(sys.argv[2], "engine_*.jsonl") if len(sys.argv) > 2 else {}
    maia = load(sys.argv[3], "bench_*.jsonl") if len(sys.argv) > 3 else {}
    print(f"positions {len(bench)} | engine leg {len(eng)} | maia leg {len(maia)}")

    conf = collections.Counter()          # GM plan in an equal engine line
    conf_r = collections.Counter()        # ... in a random line (floor)
    typ = collections.Counter()           # GM plan in >=2 maia rolls
    tot_e = collections.Counter()
    tot_m = collections.Counter()
    mult = []
    for _id, r in bench.items():
        af = fams(lab(r["fen"], r["actual_ucis"]))
        if _id in eng:
            pvs = eng[_id]["pvs"]
            cp1 = pvs[0]["cp"] if pvs else 0
            equal = [p for p in pvs if abs(p["cp"] - cp1) <= EQUAL_BAND]
            mult.append(len(equal))
            U = set().union(*[fams(lab(r["fen"], p["ucis"]))
                              for p in equal]) if equal else set()
            R = set().union(*[fams(lab(r["fen"], u))
                              for u in [r["random_ucis"]]])
            for f in af:
                tot_e[f] += 1
                if f in U:
                    conf[f] += 1
                if f in R:
                    conf_r[f] += 1
        if _id in maia:
            sm = [fams(lab(r["fen"], s)) for s in maia[_id]["samples"]]
            for f in af:
                tot_m[f] += 1
                if sum(1 for x in sm if f in x) >= 2:
                    typ[f] += 1

    if mult:
        print(f"\nequal-eval lines/position: mean {statistics.mean(mult):.1f}")
    print(f"\n{'plan':>22} | {'eng confirm':>11} | {'(floor)':>8} | "
          f"{'maia typical':>12}")
    allf = sorted(set(tot_e) | set(tot_m),
                  key=lambda f: -(tot_e[f] + tot_m[f]))
    for f in allf:
        ce = f"{100*conf[f]/tot_e[f]:.0f}% ({tot_e[f]})" if tot_e[f] >= 6 else "-"
        fl = f"{100*conf_r[f]/tot_e[f]:.0f}%" if tot_e[f] >= 6 else "-"
        cm = f"{100*typ[f]/tot_m[f]:.0f}% ({tot_m[f]})" if tot_m[f] >= 6 else "-"
        print(f"{f:>22} | {ce:>11} | {fl:>8} | {cm:>12}")
