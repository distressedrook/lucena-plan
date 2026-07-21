"""PASS C: plan_diff signatures over all four legs + the agreement report."""
from __future__ import annotations

import collections
import json
import statistics
import sys

import chess

sys.path.insert(0, "/Users/avismara/Development/chess-plans")
from plan_diff import labels

A = "/Users/avismara/Development/chess-plans/experiments/ev_positions25.jsonl"
B = "/Users/avismara/Development/chess-plans/experiments/ev_maia25.jsonl"
OUT = "/Users/avismara/Development/chess-plans/experiments/engine_vs_human_plans25.jsonl"

if __name__ == "__main__":
    pos = [json.loads(l) for l in open(A)]
    maia = {r["n"]: r["maia"] for r in (json.loads(l) for l in open(B))}
    rows = []
    for r in pos:
        b = chess.Board(r["fen"])
        row = {"n": r["n"], "cp": r["cp"]}
        for leg in ("engine", "actual", "random"):
            row[leg] = sorted(labels(b, [chess.Move.from_uci(u) for u in r[leg]]))
        row["maia"] = sorted(labels(
            b, [chess.Move.from_uci(u) for u in maia.get(r["n"], [])]))
        rows.append(row)
    with open(OUT, "w") as g:
        for r in rows:
            g.write(json.dumps(r) + "\n")

    def jac(a, b):
        a, b = set(a), set(b)
        return len(a & b) / len(a | b) if a | b else None

    print(f"positions: {len(rows)}")
    evfrac = {leg: statistics.mean(1.0 if r[leg] else 0.0 for r in rows)
              for leg in ("engine", "maia", "actual", "random")}
    print("eventful-line rate:", {k: f"{100*v:.0f}%" for k, v in evfrac.items()})
    for pair in (("engine", "actual"), ("maia", "actual"), ("engine", "maia"),
                 ("engine", "random"), ("actual", "random"), ("maia", "random")):
        js = [jac(r[pair[0]], r[pair[1]]) for r in rows]
        js = [j for j in js if j is not None]
        both = sum(1 for r in rows if set(r[pair[0]]) & set(r[pair[1]]))
        print(f"{pair[0]:>7} vs {pair[1]:<7}: mean Jaccard "
              f"{statistics.mean(js):.3f} | >=1 shared plan in "
              f"{100*both/len(rows):.0f}% of positions")
    evs = collections.Counter()
    for r in rows:
        for src in ("engine", "maia", "actual", "random"):
            for e in r[src]:
                evs[(e.split(':')[1], src)] += 1
    kinds = sorted({k for k, _ in evs})
    print(f"\n{'plan':>26} | {'engine':>6} | {'maia':>5} | {'actual':>6} | "
          f"{'random':>6} | E&A both")
    for k in kinds:
        ea = sum(1 for r in rows
                 if any(e.split(':')[1] == k for e in r["engine"])
                 and any(e.split(':')[1] == k for e in r["actual"]))
        print(f"{k:>26} | {evs[(k,'engine')]:>6} | {evs[(k,'maia')]:>5} | "
              f"{evs[(k,'actual')]:>6} | {evs[(k,'random')]:>6} | {ea:>5}")
