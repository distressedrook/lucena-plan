"""Extend the 120 saved positions' futures to 25 plies.
Engine: continue PV-extension with more searches (fork-free process).
Actual: re-read the GM pgn (free). Random: re-roll 25 plies, same seeds.
Writes ev_positions25.jsonl. Maia 25-ply rollouts run separately (ev_pass_b
with HORIZON=25 via env)."""
from __future__ import annotations

import json
import random
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/chess-lab/explainer")
sys.path.insert(0, "/Users/avismara/Development/chess-lab")
from probes import Probes
import grpc
from lucena.engine.v1 import engine_pb2 as pb

HORIZON = 25
PLY_AT = 28
IN = "/Users/avismara/Development/lucena/lucena-plans/experiments/ev_positions.jsonl"
OUT = "/Users/avismara/Development/lucena/lucena-plans/experiments/ev_positions25.jsonl"

probes = Probes()


def analyze(fen):
    last = None
    for _ in range(3):
        try:
            return probes._truth.Analyze(
                pb.AnalyzeReq(fen=fen, limit=pb.Limit(nodes=1000000, threads=1),
                              multipv=1), timeout=90).lines
        except grpc.RpcError as e:
            last = e
    raise last


def extend_engine(b0, ucis):
    cur = b0.copy()
    line = [chess.Move.from_uci(u) for u in ucis]
    for mv in line:
        cur.push(mv)
    tries = 0
    while len(line) < HORIZON and tries < 4 and not cur.is_game_over():
        ls = analyze(cur.fen())
        if not ls or not ls[0].pv_san:
            break
        for san in ls[0].pv_san:
            try:
                mv = cur.parse_san(san)
            except ValueError:
                return line
            line.append(mv)
            cur.push(mv)
            if len(line) >= HORIZON:
                break
        tries += 1
    return line


if __name__ == "__main__":
    rows = [json.loads(l) for l in open(IN)]
    wanted = {r["n"]: r for r in rows}
    actual25 = {}
    n = 0
    with open("/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn",
              encoding="latin-1") as f:
        while len(actual25) < len(wanted):
            game = chess.pgn.read_game(f)
            if game is None:
                break
            n += 1
            if n in wanted:
                moves = list(game.mainline_moves())
                actual25[n] = [m.uci() for m in moves[PLY_AT:PLY_AT + HORIZON]]
    done = 0
    with open(OUT, "w") as g:
        for r in rows:
            b0 = chess.Board(r["fen"])
            el = extend_engine(b0, r["engine"])
            rng = random.Random(r["n"])
            cur = b0.copy()
            rnd = []
            for _ in range(HORIZON):
                lg = list(cur.legal_moves)
                if not lg:
                    break
                mv = rng.choice(lg)
                rnd.append(mv)
                cur.push(mv)
            g.write(json.dumps({"n": r["n"], "cp": r["cp"], "fen": r["fen"],
                                "engine": [m.uci() for m in el],
                                "actual": actual25.get(r["n"], r["actual"]),
                                "random": [m.uci() for m in rnd]}) + "\n")
            g.flush()
            done += 1
            if done % 20 == 0:
                print(f"{done}/{len(rows)} extended", flush=True)
    print("EXTEND DONE", flush=True)
