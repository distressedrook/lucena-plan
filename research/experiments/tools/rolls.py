#!/usr/bin/env python3
"""rolls — the research harness's live roll producers.

THE ONLY place in this repo that reaches an engine or Maia at runtime.
The library itself is roll-free by contract: every verify/fact-sheet
entry point takes (fen, pvs, rolls) and only CHECKS lines. This module
is how the research side produces those lines:

  roll_engine(fen, horizon)  MultiPV=4 @1M nodes via
                             engine_roll_helper.py under chess-lab's venv
                             (gRPC/protobuf isolation — the backend does
                             NOT need this; it rolls with its own
                             in-process engine access).
  roll_maia(fen, horizon)    K=9 gated rollouts (K* from the k-study)
                             over the gpu_benchmark docker pipe.
  roll_both(fen, horizon)    {"pvs": ..., "rolls": ...} — the bank shape
                             verify.py's CLI and fact_sheet.py's CLI read.

Either producer returns None when its backend is down; verify degrades
and says so.

    ./rolls.py "<FEN>" [horizon] > bank.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import chess

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))          # lucena-plans/

CHESSLAB_PY = "/Users/avismara/Development/chess-lab/.venv/bin/python"
ENGINE_HELPER = os.path.join(_HERE, "engine_roll_helper.py")
K = 9                    # the k-study K* (settles at K*=9)


def roll_engine(fen: str, horizon: int, multipv: int = 4):
    """[{cp, ucis}] equal+unequal PVs, or None if the backend is down."""
    try:
        out = subprocess.run(
            [CHESSLAB_PY, ENGINE_HELPER, fen, str(multipv), str(horizon)],
            capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)["pvs"]
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None


_maia = None


def roll_maia(fen: str, horizon: int, k: int = K):
    """K gated rollouts as UCI lists, or None if the docker pipe is down."""
    global _maia
    try:
        sys.path.insert(0, os.path.join(_ROOT, "gpu_benchmark"))
        from gpu_bench import DockerBackend, rollout_gated
        import random
        import gpu_bench
        gpu_bench.HORIZON = horizon
        if _maia is None:
            _maia = DockerBackend()
        b = chess.Board(fen)
        seed = (hash(fen) & 0x7FFFFFFF)
        return [[m.uci() for m in rollout_gated(_maia, b,
                                                random.Random(seed * 100 + i))]
                for i in range(k)]
    except Exception:
        return None


def roll_both(fen: str, horizon: int = 25, k: int = K) -> dict:
    """One bank for one position: {"pvs": ..., "rolls": ...}."""
    return {"pvs": roll_engine(fen, horizon),
            "rolls": roll_maia(fen, horizon, k)}


if __name__ == "__main__":
    fen = sys.argv[1]
    horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    bank = roll_both(fen, horizon)
    print(json.dumps(bank))
    pvs, rolls = bank["pvs"], bank["rolls"]
    print(f"engine: {'down' if pvs is None else f'{len(pvs)} PVs'}; "
          f"maia: {'down' if rolls is None else f'{len(rolls)} rolls'}",
          file=sys.stderr)
