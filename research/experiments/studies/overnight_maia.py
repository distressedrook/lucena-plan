"""OVERNIGHT MAIA RUN — calibrate the future-generator itself.

Leg A (~4,000 anchors): one deterministic Maia3-2400 rollout (25 plies) per
anchor -> labels at both regimes. Morning yields the Maia-leg lift table
(vs the actual/random tables from the geometry calibration) and
P(plan | structure) over REACHABLE futures — the suggester's priors.

Leg B (~300 anchors): k=8 sampled rollouts per anchor (client-side sampling
from Maia's top-5 ranked moves, seeded, rank-weighted — stock maia3-uci
emits ranks, not probabilities; approximation documented) -> how many
rollouts until plan frequencies stabilize. This calibrates the product's
k (latency/quality knob).

Shard-checkpointed, resume-safe, pipe survives container restarts.
Anchors are drawn from the geometry calibration's shards (same positions).
"""
from __future__ import annotations

import glob
import json
import os
import random
import select
import subprocess
import sys
import time

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-plans/src")
from plan_diff import labels

LIFT_SHARDS = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/lift_shards"
OUT_DIR = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/maia_shards"
PGN = "/Users/avismara/Projects/active/lucena/lucena-plans/research/data/gm_classical.pgn"
N_ARGMAX = 4000
N_KSTUDY = 300
K = 8
HORIZON = 25
PER_SHARD = 100
RANK_W = [0.45, 0.25, 0.15, 0.10, 0.05]

_SRV = ("import sys\n"
        "from lucena_engine.maia import MaiaEngine\n"
        "m=MaiaEngine()\n"
        "print('READY',flush=True)\n"
        "for line in sys.stdin:\n"
        "    fen=line.strip()\n"
        "    if not fen: break\n"
        "    ms=m.top_human_moves(fen,2400,n=5)\n"
        "    print(' '.join(x['uci'] for x in ms),flush=True)")

_pipe = None


def _spawn():
    p = subprocess.Popen(
        ["docker", "exec", "-i", "lucena-app-1", "python3", "-u", "-c", _SRV],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    r, _, _ = select.select([p.stdout], [], [], 90.0)
    if not r or p.stdout.readline().strip() != "READY":
        p.terminate()
        raise BrokenPipeError("maia spawn failed")
    return p


def top5(fen: str) -> list[str]:
    global _pipe
    for _ in range(6):
        try:
            if _pipe is None or _pipe.poll() is not None:
                _pipe = _spawn()
            _pipe.stdin.write(fen + "\n")
            r, _, _ = select.select([_pipe.stdout], [], [], 30.0)
            if not r:
                raise BrokenPipeError("timeout")
            line = _pipe.stdout.readline().strip()
            if not line:
                raise BrokenPipeError("empty")
            return line.split()
        except (BrokenPipeError, OSError):
            try:
                _pipe.terminate()
            except Exception:
                pass
            _pipe = None
            time.sleep(10)
    raise RuntimeError("maia pipe irrecoverable")


def rollout(b: chess.Board, rng: random.Random | None) -> list[chess.Move]:
    cur = b.copy()
    out = []
    while len(out) < HORIZON and not cur.is_game_over():
        ucis = top5(cur.fen())
        legal = []
        for u in ucis:
            try:
                m = cur.parse_uci(u)
                legal.append(m)
            except ValueError:
                continue
        if not legal:
            break
        if rng is None:
            mv = legal[0]
        else:
            w = RANK_W[:len(legal)]
            mv = rng.choices(legal, weights=w)[0]
        out.append(mv)
        cur.push(mv)
    return out


def load_anchors():
    rows = []
    for p in sorted(glob.glob(f"{LIFT_SHARDS}/shard_*.jsonl")):
        with open(p) as f:
            rows.extend(json.loads(l) for l in f)
    rng = random.Random(2026)
    rng.shuffle(rows)
    with_struct = [r for r in rows if r["structures"]]
    rest = [r for r in rows if not r["structures"]]
    picked = (with_struct[:N_ARGMAX // 2]
              + rest[:N_ARGMAX - len(with_struct[:N_ARGMAX // 2])])
    return picked[:N_ARGMAX], picked[:N_KSTUDY]


def fen_at(pgn_file, game_offsets, n, anchor):
    pgn_file.seek(game_offsets[n])
    game = chess.pgn.read_game(pgn_file)
    b = game.board()
    for i, mv in enumerate(game.mainline_moves()):
        if i >= anchor:
            break
        b.push(mv)
    return b


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    offsets = {}
    n = 0
    with open(PGN, "rb") as f:
        off = f.tell()
        for line in iter(f.readline, b""):
            if line.startswith(b"[Event "):
                n += 1
                offsets[n] = off
            off = f.tell()
    argmax_anchors, k_anchors = load_anchors()
    print(f"anchors: argmax {len(argmax_anchors)}, k-study {len(k_anchors)}",
          flush=True)
    pgn_f = open(PGN, encoding="latin-1")

    # ---- Leg A: argmax rollouts, sharded
    shards = [(i, argmax_anchors[i * PER_SHARD:(i + 1) * PER_SHARD])
              for i in range((len(argmax_anchors) + PER_SHARD - 1) // PER_SHARD)]
    for sid, batch in shards:
        path = f"{OUT_DIR}/argmax_{sid:03d}.jsonl"
        if os.path.exists(path):
            continue
        with open(path + ".tmp", "w") as out:
            for r in batch:
                try:
                    b = fen_at(pgn_f, offsets, r["n"], r["anchor"])
                    line = rollout(b, None)
                    out.write(json.dumps({
                        "n": r["n"], "anchor": r["anchor"],
                        "result": r["result"], "structures": r["structures"],
                        "actual_slow": r["as"], "random_slow": r["rs"],
                        "maia_fast": sorted(labels(b, line, 12, 2)),
                        "maia_slow": sorted(labels(b, line, 25, 6)),
                    }, separators=(",", ":")) + "\n")
                except Exception as e:
                    print(f"anchor error n={r['n']}: {e}", flush=True)
        os.rename(path + ".tmp", path)
        print(f"argmax shard {sid:03d}/{len(shards) - 1} done", flush=True)

    # ---- Leg B: k sampled rollouts
    for sid in range((len(k_anchors) + 24) // 25):
        path = f"{OUT_DIR}/ksample_{sid:03d}.jsonl"
        if os.path.exists(path):
            continue
        batch = k_anchors[sid * 25:(sid + 1) * 25]
        with open(path + ".tmp", "w") as out:
            for r in batch:
                try:
                    b = fen_at(pgn_f, offsets, r["n"], r["anchor"])
                    samples = []
                    for k in range(K):
                        rng = random.Random(r["n"] * 100 + r["anchor"] * 10 + k)
                        line = rollout(b, rng)
                        samples.append(sorted(labels(b, line, 25, 6)))
                    out.write(json.dumps({
                        "n": r["n"], "anchor": r["anchor"],
                        "structures": r["structures"],
                        "actual_slow": r["as"], "samples": samples,
                    }, separators=(",", ":")) + "\n")
                except Exception as e:
                    print(f"k-anchor error n={r['n']}: {e}", flush=True)
        os.rename(path + ".tmp", path)
        print(f"ksample shard {sid:03d} done", flush=True)
    print("OVERNIGHT MAIA DONE", flush=True)
