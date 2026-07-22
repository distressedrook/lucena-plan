"""Do the engine and strong humans pursue the SAME plans from equal positions?

For each equalish GM middlegame position (|cp| <= 50 at 1M nodes, ply 28):
  engine leg — the engine's PV, extended to >= 12 plies by re-analyzing at
               the PV tail (deterministic fixed nodes)
  actual leg — the 12 plies the GMs actually played
  random leg — 12 random legal plies (chance baseline, seeded per position)
  maia leg   — Maia3-2400 self-play rollout (12 plies, Temperature 0 argmax,
               SelfElo=OppoElo=2400), served by the lucena-app container's
               Maia3-23M via a persistent FEN->move pipe
Run plan_signatures over each; report per-event rates and pairwise agreement
benchmarked against the random baseline.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/research/experiments")
sys.path.insert(0, "/Users/avismara/Development/chess-lab/explainer")
sys.path.insert(0, "/Users/avismara/Development/chess-lab")
os.environ["EXPLAINER_NODES"] = "1000000"
# gRPC channels do NOT survive fork(): every subprocess.Popen after channel
# creation corrupts the poll set ("FD from fork parent still in poll list")
# and wedges the channel forever. Fork support on; channel created lazily
# AFTER the Maia subprocess exists, and recreated after any respawn.
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "1"
os.environ["GRPC_POLL_STRATEGY"] = "poll"
from probes import Probes
from plan_diff import labels as signature   # the snapshot/diff/parse namer

PLY_AT = 28
HORIZON = 12
EQUAL_CP = 50
TARGET = 120

probes = None                      # created lazily, always after the last fork

import grpc
from lucena.engine.v1 import engine_pb2 as pb


def _probes():
    global probes
    if probes is None:
        probes = Probes()
    return probes


class _L:
    def __init__(self, l):
        self.cp, self.san = l.eval.cp, list(l.pv_san)


def analyze_deadline(fen: str, timeout: float = 60.0):
    """probes.analyze with a gRPC deadline + retries — a lost in-flight
    request must fail fast, not hang the run forever."""
    last = None
    for _ in range(3):
        try:
            r = _probes()._truth.Analyze(
                pb.AnalyzeReq(fen=fen,
                              limit=pb.Limit(nodes=1000000, threads=1),
                              multipv=1),
                timeout=timeout)
            return [_L(l) for l in r.lines]
        except grpc.RpcError as e:
            last = e
    raise last


def engine_line(b: chess.Board) -> tuple[int, list[chess.Move]] | None:
    cur = b.copy()
    line = []
    cp0 = None
    for _ in range(3):
        ls = analyze_deadline(cur.fen())
        if not ls:
            break
        if cp0 is None:
            cp0 = ls[0].cp
        for san in ls[0].san:
            try:
                mv = cur.parse_san(san)
            except ValueError:
                return (cp0, line)
            line.append(mv)
            cur.push(mv)
        if len(line) >= HORIZON:
            break
    return (cp0, line) if cp0 is not None else None


import subprocess

_maia = None
MAIA_ELO = 2400
_SRV = ("import sys\n"
        "from lucena_engine.maia import MaiaEngine\n"
        "m=MaiaEngine()\n"
        "print('READY',flush=True)\n"
        "for line in sys.stdin:\n"
        "    fen=line.strip()\n"
        "    if not fen: break\n"
        f"    print(m.top_human_moves(fen,{MAIA_ELO},n=1)[0]['uci'],flush=True)")


def _maia_spawn():
    import select
    p = subprocess.Popen(
        ["docker", "exec", "-i", "lucena-app-1", "python3", "-u", "-c", _SRV],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    ready, _, _ = select.select([p.stdout], [], [], 60.0)
    if not ready or p.stdout.readline().strip() != "READY":
        p.terminate()
        raise BrokenPipeError("maia server failed to start")
    return p


def maia_line(b: chess.Board) -> list[chess.Move]:
    """Maia3-2400 self-play rollout via the lucena-app container; survives
    container restarts by respawning the pipe and continuing the rollout."""
    global _maia
    cur = b.copy()
    out = []
    while len(out) < HORIZON and not cur.is_game_over():
        try:
            if _maia is None or _maia.poll() is not None:
                global probes
                _maia = _maia_spawn()
                probes = None      # channel predates this fork: recreate it
            _maia.stdin.write(cur.fen() + "\n")
            import select
            ready, _, _ = select.select([_maia.stdout], [], [], 20.0)
            if not ready:
                raise BrokenPipeError("maia reply timeout")
            uci = _maia.stdout.readline().strip()
            if not uci:
                raise BrokenPipeError("empty reply")
            mv = cur.parse_uci(uci)
        except (BrokenPipeError, OSError, ValueError):
            try:
                _maia.terminate()
            except Exception:
                pass
            _maia = None
            import time
            time.sleep(5)
            continue
        out.append(mv)
        cur.push(mv)
    return out


def random_line(b: chess.Board, seed: int) -> list[chess.Move]:
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
    _maia = _maia_spawn()          # fork FIRST; the gRPC channel comes after
    rows = []
    scanned = 0
    with open("/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn",
              encoding="latin-1") as f:
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
                el = engine_line(b)
            except Exception:
                continue
            if el is None or abs(el[0]) > EQUAL_CP or len(el[1]) < 8:
                continue
            sig_e = signature(b, el[1])
            sig_a = signature(b, moves[PLY_AT:PLY_AT + HORIZON])
            sig_m = signature(b, maia_line(b))
            sig_r = signature(b, random_line(b, seed=scanned))
            rows.append({"n": scanned, "cp": el[0],
                         "engine": sorted(sig_e), "actual": sorted(sig_a),
                         "maia": sorted(sig_m), "random": sorted(sig_r)})
            if len(rows) % 20 == 0:
                print(f"{len(rows)}/{TARGET} positions "
                      f"(scanned {scanned})", flush=True)

    out = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/engine_vs_human_plans.jsonl"
    with open(out, "w") as g:
        for r in rows:
            g.write(json.dumps(r) + "\n")

    def jac(a, b):
        a, b = set(a), set(b)
        return len(a & b) / len(a | b) if a | b else None

    print(f"\npositions: {len(rows)}")
    for pair in (("engine", "actual"), ("maia", "actual"), ("engine", "maia"),
                 ("engine", "random"), ("actual", "random"),
                 ("maia", "random")):
        js = [jac(r[pair[0]], r[pair[1]]) for r in rows]
        js = [j for j in js if j is not None]
        both = sum(1 for r in rows if set(r[pair[0]]) & set(r[pair[1]]))
        print(f"{pair[0]:>7} vs {pair[1]:<7}: mean Jaccard "
              f"{statistics.mean(js):.3f} | >=1 shared event in "
              f"{100*both/len(rows):.0f}% of positions")
    import collections
    evs = collections.Counter()
    for r in rows:
        for src in ("engine", "maia", "actual", "random"):
            for e in r[src]:
                evs[(e.split(':')[1], src)] += 1
    kinds = sorted({k for k, _ in evs})
    print(f"\n{'event':>18} | {'engine':>6} | {'maia':>6} | {'actual':>6} | "
          f"{'random':>6} | agree(E&A)")
    for k in kinds:
        ea = sum(1 for r in rows
                 if any(e.split(':')[1] == k for e in r["engine"])
                 and any(e.split(':')[1] == k for e in r["actual"]))
        print(f"{k:>18} | {evs[(k,'engine')]:>6} | {evs[(k,'maia')]:>6} | "
              f"{evs[(k,'actual')]:>6} | {evs[(k,'random')]:>6} | {ea:>5}")
    if _maia:
        _maia.terminate()
