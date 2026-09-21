#!/usr/bin/env python3
"""Sharpness audit (2026-07-24): does dynamism.py's bucket track what the
literature means by sharpness — the degree to which a position punishes
the next mistake?

Two independent gold standards, fresh local Stockfish per position:
  PUNISH   MultiPV=6 @ 150k nodes: mean cp loss of alternatives 2..6 vs
           best (clipped at 300) + playable breadth (# within 50cp).
           The "how many decent moves exist" axis (WDL-sharpness cousin
           computable without a WDL head).
  GB       Guid-Bratko instability: best-move changes over a depth sweep
           (d = 6,8,10,12,14), each change weighted by |eval jump|.
           The "does calculation change the verdict" axis.

Also measured, because the code read indicts them:
  - imbalance/compensation fires on RAW material: count positions where
    |raw - cp| >= 90 but |adjusted - cp| < 90 (a pending recapture
    masquerading as compensation — the residual study's anchor lesson).
  - forced-recapture confound: SHARP-by-narrowness positions whose best
    move is a SEE>0 capture (the 'only move' is trivially findable).

Stratified sample over current buckets so every bucket is represented.
"""
from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict

ROOT = "/Users/avismara/Projects/active/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")
sys.path.insert(0, f"{ROOT}/lucena-plans/src")

import chess
import chess.engine

from dynamism import dynamism, EQUAL_BAND
from lucena_core.metrics import material_stability
from lucena_core.see import see as core_see

BENCH = f"{ROOT}/lucena-plans/research/gpu_benchmark/benchmark_v1.jsonl"
ENG = f"{ROOT}/lucena-plans/research/experiments/eng_shards"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "audit_report.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"
PER_BUCKET = 60
DEPTHS = (6, 8, 10, 12, 14)


MAIA = f"{ROOT}/lucena-plans/research/experiments/maia_shards_2400v1800"


def load_roots():
    """(fen, pvs, rolls) — the production contract: 4 PVs + K=16 Maia
    rollouts at the 25-ply horizon (banked raw UCIs)."""
    pvs = {}
    for name in sorted(os.listdir(ENG)):
        for line in open(os.path.join(ENG, name)):
            r = json.loads(line)
            pvs[r["id"]] = r["pvs"]
    rolls = {}
    for name in sorted(os.listdir(MAIA)):
        for line in open(os.path.join(MAIA, name)):
            r = json.loads(line)
            rolls.setdefault(r["id"], r["samples"])
    out = []
    for line in open(BENCH):
        s = json.loads(line)
        if s["id"] in pvs and abs(pvs[s["id"]][0]["cp"]) <= 300:
            out.append((s["fen"], pvs[s["id"]], rolls.get(s["id"])))
    n_roll = sum(1 for _, _, r in out if r)
    print(f"{len(out)} roots, {n_roll} with maia rolls")
    return out


def gold_punish(engine, fen):
    b = chess.Board(fen)
    infos = engine.analyse(b, chess.engine.Limit(nodes=150_000), multipv=6)
    cps = []
    for info in infos:
        s = info["score"].white().score(mate_score=2_000)
        cps.append(s if b.turn == chess.WHITE else s)
    # order best-first from the mover's POV
    stm = 1 if b.turn == chess.WHITE else -1
    vals = sorted((stm * c for c in cps), reverse=True)
    if len(vals) < 2:
        return None
    losses = [min(vals[0] - v, 300) for v in vals[1:]]
    breadth = sum(1 for v in vals if vals[0] - v <= 50)
    return {"punish": sum(losses) / len(losses), "breadth": breadth,
            "n_moves": len(vals)}


def gold_gb(engine, fen):
    b = chess.Board(fen)
    prev_move, prev_cp, score = None, None, 0.0
    for d in DEPTHS:
        info = engine.analyse(b, chess.engine.Limit(depth=d))
        mv = info.get("pv", [None])[0]
        cp = info["score"].white().score(mate_score=2_000)
        if prev_move is not None and mv != prev_move:
            score += abs(cp - prev_cp)
        prev_move, prev_cp = mv, cp
    return score


def main():
    roots = load_roots()
    rng = random.Random(3)
    rng.shuffle(roots)

    by_bucket = defaultdict(list)
    for fen, pvs, rolls in roots:
        d = dynamism(fen, pvs, rolls)
        by_bucket[d["bucket"]].append((fen, pvs, d))
        if all(len(v) >= PER_BUCKET * 3 for v in by_bucket.values()) \
                and len(by_bucket) >= 4:
            break

    sample = []
    for bk, rows in by_bucket.items():
        sample += rows[:PER_BUCKET]
    print({k: min(len(v), PER_BUCKET) for k, v in by_bucket.items()})

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": 4, "Hash": 512})
    rows = []
    try:
        for fen, pvs, d in sample:
            g = gold_punish(engine, fen)
            if g is None:
                continue
            gb = gold_gb(engine, fen)
            ms = material_stability(fen)
            cp1 = pvs[0]["cp"]
            comp_raw = abs(ms["raw_cp"] - cp1)
            comp_adj = abs(ms["adjusted_cp"] - cp1)
            b = chess.Board(fen)
            first = chess.Move.from_uci(pvs[0]["ucis"][0])
            best_is_grab = (b.is_capture(first)
                            and core_see(fen, first.uci()) > 0)
            rows.append({"fen": fen, "bucket": d["bucket"],
                         "score": d["score"],
                         "comps": [c[0] for c in d["components"]],
                         "punish": round(g["punish"], 1),
                         "breadth": g["breadth"], "gb": round(gb, 1),
                         "comp_raw": comp_raw, "comp_adj": comp_adj,
                         "best_is_grab": best_is_grab})
    finally:
        engine.quit()

    # ---- report
    order = ["DEAD", "QUIET", "DYNAMIC", "SHARP", "RAZOR"]
    print(f"\n{'bucket':<9}{'n':>4} {'punish':>8} {'breadth':>8} {'GB':>7}")
    per = {}
    for bk in order:
        rs = [r for r in rows if r["bucket"] == bk]
        if not rs:
            continue
        mp = sum(r["punish"] for r in rs) / len(rs)
        mb = sum(r["breadth"] for r in rs) / len(rs)
        mg = sum(r["gb"] for r in rs) / len(rs)
        per[bk] = {"n": len(rs), "punish": round(mp, 1),
                   "breadth": round(mb, 2), "gb": round(mg, 1)}
        print(f"{bk:<9}{len(rs):>4} {mp:>8.1f} {mb:>8.2f} {mg:>7.1f}")

    def spearman(a, b_):
        import numpy as np
        ra = np.argsort(np.argsort(a))
        rb = np.argsort(np.argsort(b_))
        return float(np.corrcoef(ra, rb)[0, 1])

    sc = [r["score"] for r in rows]
    print(f"\nspearman(dyn score, punish)  = "
          f"{spearman(sc, [r['punish'] for r in rows]):.3f}")
    print(f"spearman(dyn score, breadth) = "
          f"{spearman(sc, [r['breadth'] for r in rows]):.3f}")
    print(f"spearman(dyn score, GB)      = "
          f"{spearman(sc, [r['gb'] for r in rows]):.3f}")

    fires_raw = [r for r in rows if r["comp_raw"] >= 90]
    false_comp = [r for r in fires_raw if r["comp_adj"] < 90]
    print(f"\ncompensation on raw material: fires {len(fires_raw)}, "
          f"of which {len(false_comp)} are pending-recapture mirages "
          f"(adjusted closes the gap)")

    sharp_narrow = [r for r in rows if r["bucket"] in ("SHARP", "RAZOR")]
    grabby = [r for r in sharp_narrow if r["best_is_grab"]]
    if sharp_narrow:
        gp = (sum(r["punish"] for r in grabby) / len(grabby)
              if grabby else 0)
        rest = [r for r in sharp_narrow if not r["best_is_grab"]]
        rp = sum(r["punish"] for r in rest) / len(rest) if rest else 0
        print(f"SHARP/RAZOR with best-move = SEE>0 capture: "
              f"{len(grabby)}/{len(sharp_narrow)} "
              f"(punish {gp:.0f} vs {rp:.0f} for the rest)")

    json.dump({"per_bucket": per, "rows": rows}, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
