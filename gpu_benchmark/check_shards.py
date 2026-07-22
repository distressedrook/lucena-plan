"""check_shards — sanity-check produced shards before shipping them back.
Verifies coverage and that every line is legal from its FEN. Handles both
legs: Maia rollouts (bench_*.jsonl, key "samples") and engine MultiPV
(engine_*.jsonl, key "pvs"). No grammar/labeling here.

    python3 check_shards.py benchmark_v1.jsonl out_shards/          # maia
    python3 check_shards.py benchmark_v1.jsonl eng_shards/ --engine # engine
"""
from __future__ import annotations

import glob
import json
import sys

import chess


def legal(fen, ucis):
    b = chess.Board(fen)
    for u in ucis:
        try:
            m = chess.Move.from_uci(u)
            if m not in b.legal_moves:
                return False
            b.push(m)
        except ValueError:
            return False
    return True


if __name__ == "__main__":
    bench = {json.loads(l)["id"]: json.loads(l) for l in open(sys.argv[1])}
    fens = {i: r["fen"] for i, r in bench.items()}
    engine_mode = "--engine" in sys.argv
    pattern = "engine_*.jsonl" if engine_mode else "bench_*.jsonl"
    seen, total, bad, ks = set(), 0, 0, set()
    for p in sorted(glob.glob(f"{sys.argv[2]}/{pattern}")):
        for line in open(p):
            if not line.strip():
                continue
            r = json.loads(line)
            seen.add(r["id"])
            lines = ([pv["ucis"] for pv in r["pvs"]] if engine_mode
                     else r["samples"])
            if not engine_mode:
                ks.add(r.get("k"))
            for ln in lines:
                total += 1
                if not legal(fens[r["id"]], ln):
                    bad += 1
    print(f"leg               : {'engine MultiPV' if engine_mode else 'maia rollouts'}")
    print(f"positions covered : {len(seen)}/{len(bench)}")
    if not engine_mode:
        print(f"K values seen     : {sorted(k for k in ks if k)}")
    print(f"total lines       : {total}")
    print(f"illegal lines     : {bad}")
    missing = set(bench) - seen
    if missing:
        print(f"MISSING {len(missing)} positions, e.g. {sorted(missing)[:5]}")
    else:
        print("COMPLETE — ready to ship back to experiments/")
