#!/usr/bin/env python3
"""Residual-attribution study, stage 2: validate the PV-inherited labels.

The harvest labels interior positions with their line's ROOT cp (minimax
consistency of a PV). Before trusting that, relabel a stratified sample
with fresh fixed-node Stockfish and measure agreement:

  - roots:      banked cp vs fresh cp  (cross-version / node-count drift)
  - interiors:  inherited cp vs fresh cp, by ply depth into the line

Report MAE + bias per stratum. If interior MAE at ply p blows past ~60cp,
cap the harvest at shallower prefixes (the label noise would drown R).
"""
from __future__ import annotations

import json
import os
import random
import sys

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "dataset.jsonl")
OUT = os.path.join(HERE, "label_validation.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"
NODES = 200_000
PER_STRATUM = 60


def fresh_cp(engine, fen: str) -> int | None:
    b = chess.Board(fen)
    info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
    s = info["score"].white().score(mate_score=10_000)
    return s


def main():
    rows = [json.loads(l) for l in open(DATA)]
    by_ply: dict[int, list] = {}
    for r in rows:
        by_ply.setdefault(r["ply"], []).append(r)

    rng = random.Random(11)
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": 4, "Hash": 256})
    report = {}
    try:
        for ply in sorted(by_ply):
            sample = rng.sample(by_ply[ply],
                                min(PER_STRATUM, len(by_ply[ply])))
            diffs = []
            for r in sample:
                cp = fresh_cp(engine, r["fen"])
                if cp is None:
                    continue
                diffs.append(cp - r["cp"])
            n = len(diffs)
            mae = sum(abs(d) for d in diffs) / n
            bias = sum(diffs) / n
            med = sorted(abs(d) for d in diffs)[n // 2]
            report[ply] = {"n": n, "mae": round(mae, 1),
                           "median_abs": med, "bias": round(bias, 1)}
            print(f"ply {ply:2d}: n={n}  MAE={mae:6.1f}  median|d|={med}"
                  f"  bias={bias:+.1f}")
    finally:
        engine.quit()
    json.dump(report, open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
