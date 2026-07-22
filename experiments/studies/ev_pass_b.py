"""PASS B (Maia-only; NO gRPC in this process): add Maia3-2400 rollouts to
Pass A's positions via the lucena-app container's FEN->move pipe."""
from __future__ import annotations

import json
import select
import subprocess
import time

import chess

HORIZON = int(__import__("os").environ.get("EV_HORIZON", "12"))
MAIA_ELO = 2400
IN = "/Users/avismara/Development/lucena/lucena-plans/experiments/ev_positions.jsonl"
OUT = "/Users/avismara/Development/lucena/lucena-plans/experiments/ev_maia.jsonl"

_SRV = ("import sys\n"
        "from lucena_engine.maia import MaiaEngine\n"
        "m=MaiaEngine()\n"
        "print('READY',flush=True)\n"
        "for line in sys.stdin:\n"
        "    fen=line.strip()\n"
        "    if not fen: break\n"
        f"    print(m.top_human_moves(fen,{MAIA_ELO},n=1)[0]['uci'],flush=True)")

_maia = None


def _spawn():
    p = subprocess.Popen(
        ["docker", "exec", "-i", "lucena-app-1", "python3", "-u", "-c", _SRV],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    ready, _, _ = select.select([p.stdout], [], [], 60.0)
    if not ready or p.stdout.readline().strip() != "READY":
        p.terminate()
        raise BrokenPipeError("maia server failed to start")
    return p


def maia_line(b: chess.Board):
    global _maia
    cur = b.copy()
    out = []
    fails = 0
    while len(out) < HORIZON and not cur.is_game_over() and fails < 5:
        try:
            if _maia is None or _maia.poll() is not None:
                _maia = _spawn()
            _maia.stdin.write(cur.fen() + "\n")
            ready, _, _ = select.select([_maia.stdout], [], [], 20.0)
            if not ready:
                raise BrokenPipeError("reply timeout")
            uci = _maia.stdout.readline().strip()
            if not uci:
                raise BrokenPipeError("empty reply")
            mv = cur.parse_uci(uci)
        except (BrokenPipeError, OSError, ValueError) as e:
            fails += 1
            try:
                _maia.terminate()
            except Exception:
                pass
            _maia = None
            time.sleep(5)
            continue
        out.append(mv)
        cur.push(mv)
    return out


if __name__ == "__main__":
    rows = [json.loads(l) for l in open(IN)]
    with open(OUT, "w") as g:
        for i, r in enumerate(rows):
            b = chess.Board(r["fen"])
            line = maia_line(b)
            g.write(json.dumps({"n": r["n"],
                                "maia": [m.uci() for m in line]}) + "\n")
            g.flush()
            if (i + 1) % 10 == 0:
                print(f"{i + 1}/{len(rows)} rollouts", flush=True)
    print("PASS B DONE", flush=True)
