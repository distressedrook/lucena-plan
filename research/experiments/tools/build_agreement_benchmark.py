"""build_agreement_benchmark — PARALLELIZED reduce_agreement: the per-plan
engine-confirm / floor / maia-typical benchmark across all 4,000 positions,
plus WITNESS positions per family (so the HTML report can show real
examples, not just aggregate percentages).

Same inputs/metric as research/gpu_benchmark/reduce_agreement.py (that script stays
the source of truth for the metric definition; this is the parallel,
witness-collecting build step feeding gen_agreement_html.py):
  benchmark_v1.jsonl         actual_ucis + random_ucis (GM leg + floor)
  eng_shards/engine_*.jsonl  MultiPV lines per id
  maia_shards/bench_*.jsonl  K rollouts per id

Output: research/experiments/agreement_benchmark.json — {
  "meta": {positions, engine_leg, maia_leg, mean_equal_lines},
  "families": {fam: {tot_e, conf, conf_r, tot_m, typ,
                      eng_witnesses: [id,...], maia_witnesses: [id,...]}}
}

Run: python3 research/experiments/build_agreement_benchmark.py
"""
from __future__ import annotations

import collections
import glob
import json
import statistics
import sys
import time
from multiprocessing import Pool

import chess

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
from plan_diff import labels

BENCH = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/benchmark_v1.jsonl"
ENG = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/eng_shards"
MAIA = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/maia_shards"
OUT = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/agreement_benchmark.json"
EQUAL_BAND = 50
WORKERS = 8
WITNESS_CAP = 12   # example positions kept per family per leg


def lab(fen, ucis, h=25, t=6):
    return labels(chess.Board(fen), [chess.Move.from_uci(u) for u in ucis], h, t)


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


def process_one(args):
    """One position -> the per-family increments it contributes. Returns a
    small dict, cheap to ship back across the process boundary; the parent
    aggregates. Keeping this per-position (not per-chunk) keeps witness
    provenance simple at negligible extra Pool overhead (4000 calls is
    fine at chunksize=8)."""
    _id, r, has_eng, eng_pvs, has_maia, maia_samples = args
    af = fams(lab(r["fen"], r["actual_ucis"]))
    out = {"id": _id, "n_equal": 0, "eng": {}, "maia": {}}
    if has_eng:
        cp1 = eng_pvs[0]["cp"] if eng_pvs else 0
        equal = [p for p in eng_pvs if abs(p["cp"] - cp1) <= EQUAL_BAND]
        out["n_equal"] = len(equal)
        U = set().union(*[fams(lab(r["fen"], p["ucis"]))
                          for p in equal]) if equal else set()
        R = fams(lab(r["fen"], r["random_ucis"]))
        for f in af:
            out["eng"][f] = (f in U, f in R)
    if has_maia:
        sm = [fams(lab(r["fen"], s)) for s in maia_samples]
        for f in af:
            hits = sum(1 for x in sm if f in x)
            out["maia"][f] = hits >= 2
    return out


if __name__ == "__main__":
    t0 = time.time()
    bench = {json.loads(l)["id"]: json.loads(l) for l in open(BENCH)}
    eng = load(ENG, "engine_*.jsonl")
    maia = load(MAIA, "bench_*.jsonl")
    print(f"positions {len(bench)} | engine leg {len(eng)} | maia leg {len(maia)}")

    jobs = []
    for _id, r in bench.items():
        e = eng.get(_id)
        m = maia.get(_id)
        jobs.append((_id, r, e is not None, e["pvs"] if e else None,
                    m is not None, m["samples"] if m else None))

    conf = collections.Counter()
    conf_r = collections.Counter()
    typ = collections.Counter()
    tot_e = collections.Counter()
    tot_m = collections.Counter()
    eng_witnesses = collections.defaultdict(list)
    maia_witnesses = collections.defaultdict(list)
    mult = []

    with Pool(WORKERS) as pool:
        for i, res in enumerate(pool.imap_unordered(process_one, jobs,
                                                     chunksize=8)):
            if res["n_equal"] or res["eng"]:
                mult.append(res["n_equal"])
            for f, (hit, floor_hit) in res["eng"].items():
                tot_e[f] += 1
                if hit:
                    conf[f] += 1
                    if len(eng_witnesses[f]) < WITNESS_CAP:
                        eng_witnesses[f].append(res["id"])
                if floor_hit:
                    conf_r[f] += 1
            for f, typical in res["maia"].items():
                tot_m[f] += 1
                if typical:
                    typ[f] += 1
                    if len(maia_witnesses[f]) < WITNESS_CAP:
                        maia_witnesses[f].append(res["id"])
            if (i + 1) % 500 == 0:
                print(f"  {i+1}/{len(jobs)} ({time.time()-t0:.0f}s)",
                      file=sys.stderr, flush=True)

    allf = sorted(set(tot_e) | set(tot_m))
    families = {}
    for f in allf:
        families[f] = {
            "tot_e": tot_e[f], "conf": conf[f], "conf_r": conf_r[f],
            "tot_m": tot_m[f], "typ": typ[f],
            "eng_witnesses": eng_witnesses[f], "maia_witnesses": maia_witnesses[f],
        }
    meta = {
        "positions": len(bench), "engine_leg": len(eng), "maia_leg": len(maia),
        "mean_equal_lines": statistics.mean(mult) if mult else 0,
        "generated_in_s": round(time.time() - t0, 1),
    }
    with open(OUT, "w") as f:
        json.dump({"meta": meta, "families": families}, f, indent=1)
    print(f"done in {time.time()-t0:.0f}s -> {OUT}")
