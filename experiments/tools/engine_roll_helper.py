"""engine_roll_helper — MultiPV roll for one FEN, as JSON on stdout.

Runs UNDER chess-lab's venv (gRPC/protobuf live there). rolls.py shells
out to this so the library itself stays in plain python3 and roll-free
(the (fen, pvs, rolls) contract).

    <chesslab-venv>/python engine_roll_helper.py "<FEN>" [multipv] [horizon]
-> {"pvs":[{"cp":int,"ucis":[...]}, ...]}
"""
from __future__ import annotations

import json
import sys

import chess

sys.path.insert(0, "/Users/avismara/Development/chess-lab/explainer")
sys.path.insert(0, "/Users/avismara/Development/chess-lab")
from probes import Probes
import grpc
from lucena.engine.v1 import engine_pb2 as pb

MAIN_NODES = 1_000_000
EXT_NODES = 250_000
probes = Probes()


def analyze(fen, nodes, multipv):
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


def walk(b, pv_san, horizon):
    cur, out = b.copy(), []
    for san in pv_san:
        try:
            mv = cur.parse_san(san)
        except ValueError:
            break
        out.append(mv)
        cur.push(mv)
        if len(out) >= horizon:
            break
    return out


def extend(b, line, horizon):
    cur = b.copy()
    for mv in line:
        cur.push(mv)
    while len(line) < horizon and not cur.is_game_over():
        ls = analyze(cur.fen(), EXT_NODES, 1)
        if not ls or not ls[0].pv_san:
            break
        add = walk(cur, ls[0].pv_san, horizon - len(line))
        if not add:
            break
        for mv in add:
            line.append(mv)
            cur.push(mv)
    return line


if __name__ == "__main__":
    fen = sys.argv[1]
    multipv = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    horizon = int(sys.argv[3]) if len(sys.argv) > 3 else 25
    b = chess.Board(fen)
    ls = analyze(fen, MAIN_NODES, multipv)
    pvs = []
    for line in ls[:multipv]:
        mvs = extend(b, walk(b, line.pv_san, horizon), horizon)
        # eval.cp is SIDE-TO-MOVE POV at the root; normalize to White POV
        # to match the banked eng_shards convention (gpu_benchmark/
        # engine_bench.py does this — this script didn't, 2026-07-22 bug:
        # every Black-to-move ASSESSMENT built from a live roll had its
        # sign flipped). The EQUAL_BAND relative comparisons in verify.py
        # were never affected (same-query PVs share one POV either way).
        cp = line.eval.cp if b.turn == chess.WHITE else -line.eval.cp
        pvs.append({"cp": cp, "ucis": [m.uci() for m in mvs]})
    print(json.dumps({"pvs": pvs}))
