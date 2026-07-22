"""engine_bench — the MultiPV leg of the agreeability benchmark.

For each benchmark_v1 position: MultiPV=N at fixed nodes, each line walked
and extended to HORIZON plies. Writes engine_XXXX.jsonl shards keyed by the
SAME id as the Maia leg, so the two merge trivially at home. The random
control is already in benchmark_v1 (random_ucis) — this leg only produces
the engine PVs. Raw UCIs + cp only; labeling happens on the analysis box.

    python3 engine_bench.py benchmark_v1.jsonl eng_shards/ [--multipv 4]
            [--nodes 1000000] [--backend uci --engine /path/to/engine]

Backends (the analyze(fen, nodes, multipv) -> [(cp, [uci...])] seam):
  uci   (default) any UCI engine speaking MultiPV — python-chess drives it.
        Point --engine at your in-memory-loaded binary. For agreeability to
        match the home run's numbers use the SAME engine we calibrate with;
        a different engine is a valid benchmark but not comparable to the
        120-position home result.
  grpc  the lucena Truth service (exact parity with home). Needs chess-lab
        on PYTHONPATH + the server up; see GRPCBackend.

CP is from the SIDE-TO-MOVE's perspective at the root, normalized to White
so the eval-equal gate |cp - cp_best| is symmetric. Shards of 50, resume-
safe. This leg is CPU search — it does NOT use the GPU; run it on cores
(here or at home) while the GPU does the Maia leg.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import chess
import chess.engine

HORIZON = 25
PER_SHARD = 50


# ---------------------------------------------------------------- backends

class UCIBackend:
    """Any UCI engine with MultiPV. One persistent process."""

    def __init__(self, path: str):
        self.eng = chess.engine.SimpleEngine.popen_uci(path)

    def analyze(self, fen: str, nodes: int, multipv: int):
        board = chess.Board(fen)
        info = self.eng.analyse(board, chess.engine.Limit(nodes=nodes),
                                multipv=multipv)
        out = []
        for line in info:
            score = line["score"].white().score(mate_score=100000)
            pv = [m.uci() for m in line.get("pv", [])]
            out.append((score if score is not None else 0, pv))
        return out

    def close(self):
        self.eng.quit()


class GRPCBackend:
    """The lucena Truth service — exact parity with the home experiment."""

    def __init__(self):
        import sys
        sys.path.insert(0, "/Users/avismara/Development/chess-lab/explainer")
        sys.path.insert(0, "/Users/avismara/Development/chess-lab")
        from probes import Probes
        from lucena.engine.v1 import engine_pb2 as pb
        import grpc
        self.probes, self.pb, self.grpc = Probes(), pb, grpc

    def analyze(self, fen: str, nodes: int, multipv: int):
        b = chess.Board(fen)
        last = None
        for _ in range(3):
            try:
                r = self.probes._truth.Analyze(
                    self.pb.AnalyzeReq(
                        fen=fen, limit=self.pb.Limit(nodes=nodes, threads=1),
                        multipv=multipv), timeout=90)
                out = []
                for line in r.lines:
                    cur, ucis = b.copy(), []
                    for san in line.pv_san:
                        try:
                            m = cur.parse_san(san)
                        except ValueError:
                            break
                        ucis.append(m.uci())
                        cur.push(m)
                    cp = line.eval.cp if b.turn == chess.WHITE else -line.eval.cp
                    out.append((cp, ucis))
                return out
            except self.grpc.RpcError as e:
                last = e
        raise last

    def close(self):
        pass


# ---------------------------------------------------------------- extend

def extend(backend, b: chess.Board, line: list[str], nodes: int) -> list[str]:
    cur = b.copy()
    for u in line:
        cur.push(chess.Move.from_uci(u))
    while len(line) < HORIZON and not cur.is_game_over():
        res = backend.analyze(cur.fen(), max(nodes // 4, 100000), 1)
        if not res or not res[0][1]:
            break
        for u in res[0][1]:
            line.append(u)
            cur.push(chess.Move.from_uci(u))
            if len(line) >= HORIZON:
                break
    return line


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("outdir")
    ap.add_argument("--multipv", type=int, default=4)
    ap.add_argument("--nodes", type=int, default=1_000_000)
    ap.add_argument("--backend", default="uci", choices=["uci", "grpc"])
    ap.add_argument("--engine", default=None,
                    help="UCI engine path (backend=uci)")
    args = ap.parse_args()

    backend = (UCIBackend(args.engine) if args.backend == "uci"
               else GRPCBackend())
    rows = [json.loads(l) for l in open(args.bench)]
    os.makedirs(args.outdir, exist_ok=True)
    nshards = (len(rows) + PER_SHARD - 1) // PER_SHARD
    try:
        for sid in range(nshards):
            path = f"{args.outdir}/engine_{sid:04d}.jsonl"
            if os.path.exists(path):
                continue
            batch = rows[sid * PER_SHARD:(sid + 1) * PER_SHARD]
            t0 = time.time()
            with open(path + ".tmp", "w") as out:
                for r in batch:
                    b = chess.Board(r["fen"])
                    res = backend.analyze(r["fen"], args.nodes, args.multipv)
                    pvs = []
                    for cp, ucis in res[:args.multipv]:
                        full = extend(backend, b, list(ucis), args.nodes)
                        pvs.append({"cp": cp, "ucis": full})
                    out.write(json.dumps({"id": r["id"], "pvs": pvs},
                                         separators=(",", ":")) + "\n")
            os.rename(path + ".tmp", path)
            print(f"shard {sid:04d}/{nshards - 1} done "
                  f"({time.time() - t0:.0f}s)", flush=True)
    finally:
        backend.close()
    print("ENGINE BENCH DONE", flush=True)
