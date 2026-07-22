"""Multi-line agreeability, PASS A (engine leg; NO forks — gRPC).

Same 120 positions as the four-way experiment (read from ev_positions25.jsonl).
Per position: MultiPV=4 at 1M nodes, each PV walked and extended to 25 plies
(extension analyzes at 250k nodes, multipv=1), plus 4 seeded random lines as
the union floor. Writes ev_multi.jsonl with raw UCIs — label-free, so the
bank is relabelable under any grammar.

Metrics land in pass C: any-line agreement (GM plan in ANY engine line) vs
the 4-random union floor, and plan multiplicity (distinct plans across PVs —
the first measurement of "how many sound plans does a position hold").
Maia leg (K sampled rollouts, same positions) = ev_pass_b_multi.py, queued
behind the k-study extension on the docker pipe.
"""
from __future__ import annotations

import json
import os
import random
import sys

import chess

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[4] / "common"))
from engine_client.probes import Probes
import grpc
from engine_client._pb import engine_pb2 as pb

SRC = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/ev_positions25.jsonl"
OUT = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/ev_multi.jsonl"
MULTIPV = 4
HORIZON = 25
MAIN_NODES = 1_000_000
EXT_NODES = 250_000

probes = Probes()


def analyze(fen: str, nodes: int, multipv: int):
    last = None
    for _ in range(3):
        try:
            r = probes._truth.Analyze(
                pb.AnalyzeReq(fen=fen, limit=pb.Limit(nodes=nodes, threads=1),
                              multipv=multipv), timeout=90)
            return r.lines
        except grpc.RpcError as e:
            last = e
    raise last


def walk_pv(b: chess.Board, pv_san) -> list[chess.Move]:
    cur = b.copy()
    out = []
    for san in pv_san:
        try:
            mv = cur.parse_san(san)
        except ValueError:
            break
        out.append(mv)
        cur.push(mv)
        if len(out) >= HORIZON:
            break
    return out


def extend(b: chess.Board, line: list[chess.Move]) -> list[chess.Move]:
    cur = b.copy()
    for mv in line:
        cur.push(mv)
    while len(line) < HORIZON and not cur.is_game_over():
        ls = analyze(cur.fen(), EXT_NODES, 1)
        if not ls or not ls[0].pv_san:
            break
        added = walk_pv(cur, ls[0].pv_san)
        if not added:
            break
        for mv in added:
            line.append(mv)
            cur.push(mv)
            if len(line) >= HORIZON:
                break
    return line


if __name__ == "__main__":
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            done = {json.loads(l)["n"] for l in f if l.strip()}
    rows = [json.loads(l) for l in open(SRC)]
    print(f"{len(rows)} positions, {len(done)} already done", flush=True)
    with open(OUT, "a") as out:
        for i, r in enumerate(rows):
            if r["n"] in done:
                continue
            b = chess.Board(r["fen"])
            ls = analyze(r["fen"], MAIN_NODES, MULTIPV)
            pvs = []
            for line in ls[:MULTIPV]:
                mvs = extend(b, walk_pv(b, line.pv_san))
                pvs.append({"cp": line.eval.cp,
                            "ucis": [m.uci() for m in mvs]})
            rnds = []
            for j in range(MULTIPV):
                rng = random.Random(r["n"] * 7919 + j)
                cur = b.copy()
                rl = []
                for _ in range(HORIZON):
                    lg = list(cur.legal_moves)
                    if not lg:
                        break
                    m = rng.choice(lg)
                    rl.append(m.uci())
                    cur.push(m)
                rnds.append(rl)
            out.write(json.dumps({
                "n": r["n"], "fen": r["fen"], "actual": r["actual"],
                "pvs": pvs, "randoms": rnds,
            }, separators=(",", ":")) + "\n")
            out.flush()
            print(f"pos {i + 1}/{len(rows)} done (n={r['n']}, "
                  f"{len(pvs)} pvs)", flush=True)
    print("PASS A MULTI DONE", flush=True)
