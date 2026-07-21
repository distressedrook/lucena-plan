"""4-way plan experiment, PASS A (engine-only; NO forks, NO subprocess —
gRPC channels do not survive fork, so this process must never fork).

Finds equalish GM positions (|cp| <= 50 at 1M nodes, ply 28), computes the
engine PV extended to >= 12 plies, the actual continuation, and the random
control line. Writes positions + lines (UCI) to ev_positions.jsonl.
Pass B adds Maia rollouts; Pass C computes signatures + the report.
"""
from __future__ import annotations

import json
import os
import random
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/chess-lab/explainer")
sys.path.insert(0, "/Users/avismara/Development/chess-lab")
from probes import Probes
import grpc
from lucena.engine.v1 import engine_pb2 as pb

PLY_AT = 28
HORIZON = 12
EQUAL_CP = 50
TARGET = 120
OUT = "/Users/avismara/Development/chess-plans/experiments/ev_positions.jsonl"

probes = Probes()


def analyze(fen: str):
    last = None
    for _ in range(3):
        try:
            r = probes._truth.Analyze(
                pb.AnalyzeReq(fen=fen, limit=pb.Limit(nodes=1000000, threads=1),
                              multipv=1), timeout=90)
            return r.lines
        except grpc.RpcError as e:
            last = e
    raise last


def engine_line(b: chess.Board):
    cur = b.copy()
    line = []
    cp0 = None
    for _ in range(3):
        ls = analyze(cur.fen())
        if not ls:
            break
        if cp0 is None:
            cp0 = ls[0].eval.cp
        for san in ls[0].pv_san:
            try:
                mv = cur.parse_san(san)
            except ValueError:
                return cp0, line
            line.append(mv)
            cur.push(mv)
        if len(line) >= HORIZON:
            break
    return (cp0, line) if cp0 is not None else (None, [])


def random_line(b: chess.Board, seed: int):
    rng = random.Random(seed)
    cur = b.copy()
    out = []
    for _ in range(HORIZON):
        legal = list(cur.legal_moves)
        if not legal:
            break
        mv = rng.choice(legal)
        out.append(mv)
        cur.push(mv)
    return out


if __name__ == "__main__":
    rows, scanned = [], 0
    with open("/Users/avismara/Development/chess-plans/data/gm_classical.pgn",
              encoding="latin-1") as f, open(OUT, "w") as g:
        while len(rows) < TARGET:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            scanned += 1
            moves = list(game.mainline_moves())
            if len(moves) < PLY_AT + HORIZON + 4:
                continue
            b = game.board()
            for mv in moves[:PLY_AT]:
                b.push(mv)
            try:
                cp0, el = engine_line(b)
            except Exception as e:
                print(f"engine error at game {scanned}: {e}", flush=True)
                continue
            if cp0 is None or abs(cp0) > EQUAL_CP or len(el) < 8:
                continue
            row = {"n": scanned, "cp": cp0, "fen": b.fen(),
                   "engine": [m.uci() for m in el],
                   "actual": [m.uci() for m in moves[PLY_AT:PLY_AT + HORIZON]],
                   "random": [m.uci() for m in random_line(b, scanned)]}
            rows.append(row)
            g.write(json.dumps(row) + "\n")
            g.flush()
            if len(rows) % 10 == 0:
                print(f"{len(rows)}/{TARGET} positions (scanned {scanned})",
                      flush=True)
    print(f"PASS A DONE: {len(rows)} positions, scanned {scanned}", flush=True)
