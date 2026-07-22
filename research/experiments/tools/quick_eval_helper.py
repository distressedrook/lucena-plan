"""quick_eval_helper — a single fixed-node engine eval for one FEN, as JSON
on stdout. Runs UNDER lucena-tactics' venv (gRPC/protobuf live there) — same
pattern as engine_roll_helper.py, but far cheaper: single line, no PV
extension, no rollout. This is for fact_sheet.py's ASSESSMENT line, which
needs "who stands better, roughly how much" — not a full verified plan
roll (that's verify.py's job, at 1M nodes / ~57s).

Fixed 100k nodes matches the teaching-set certification convention
(finding 3): ~1-2s/position, deterministic, same input -> same output.

    <lucena-tactics>/.venv/bin/python quick_eval_helper.py "<FEN>"
-> {"cp": int}   (White POV, centipawns)
"""
from __future__ import annotations

import json
import sys

import chess

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[4] / "common"))
from engine_client.probes import Probes
import grpc
from engine_client._pb import engine_pb2 as pb

NODES = 100_000
probes = Probes()


def quick_eval(fen: str) -> int:
    # eval.cp is SIDE-TO-MOVE POV at the root; the docstring always
    # claimed "White POV" but this never actually normalized it (2026-07-22
    # bug — every Black-to-move ASSESSMENT built via this fallback had its
    # sign flipped). Matches the fix in engine_roll_helper.py.
    white_pov = chess.Board(fen).turn == chess.WHITE
    last = None
    for _ in range(3):
        try:
            r = probes._truth.Analyze(
                pb.AnalyzeReq(fen=fen, limit=pb.Limit(nodes=NODES, threads=1),
                              multipv=1), timeout=30)
            cp = r.lines[0].eval.cp
            return cp if white_pov else -cp
        except grpc.RpcError as e:
            last = e
    raise last


if __name__ == "__main__":
    print(json.dumps({"cp": quick_eval(sys.argv[1])}))
