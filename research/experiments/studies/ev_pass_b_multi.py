"""Multi-line agreeability, PASS B (Maia leg, 40-60 gated).

K=16 Maia3-2400 rollouts (25 plies) per position on the SAME 120 positions.
RULING (2026-07-22): a rollout may deviate from Maia's top move ONLY at
genuinely contested human choices — policy p_i/(p_1+p_i) >= 0.40 (the
"40-60 band"). Everywhere else the line is forced to the human favorite.
Uses Maia's actual policy probabilities (the pipe emits uci:policy pairs),
not rank weights. Plus 16 seeded random lines as the distributional floor.
Raw UCIs only — relabelable forever.

Run AFTER kstudy_extend finishes (single docker pipe). Duplicate lines among
the 16 are DATA (few contested nodes => concentrated agreement mass); pass C
reports distinct-line counts alongside.
"""
from __future__ import annotations

import json
import os
import random
import select
import subprocess
import time

import chess

SRC = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/ev_positions25.jsonl"
OUT = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/ev_multi_maia.jsonl"
K = 16
HORIZON = 25
BAND = 0.40                    # p_i/(p_1+p_i) >= BAND -> contested choice

_SRV = ("import sys\n"
        "from lucena_engine.maia import MaiaEngine\n"
        "m=MaiaEngine()\n"
        "print('READY',flush=True)\n"
        "for line in sys.stdin:\n"
        "    fen=line.strip()\n"
        "    if not fen: break\n"
        "    ms=m.top_human_moves(fen,2400,n=5)\n"
        "    print(' '.join(f\"{x['uci']}:{x['policy']:.6f}\" for x in ms),"
        "flush=True)")

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


def top_policy(fen: str) -> list[tuple[str, float]]:
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
            out = []
            for tok in line.split():
                u, p = tok.rsplit(":", 1)
                out.append((u, float(p)))
            return out
        except (BrokenPipeError, OSError, ValueError):
            try:
                _pipe.terminate()
            except Exception:
                pass
            _pipe = None
            time.sleep(10)
    raise RuntimeError("maia pipe irrecoverable")


def rollout_gated(b: chess.Board, rng: random.Random) -> list[chess.Move]:
    cur = b.copy()
    out = []
    while len(out) < HORIZON and not cur.is_game_over():
        cand = []
        for u, p in top_policy(cur.fen()):
            try:
                m = cur.parse_uci(u)
                cand.append((m, p))
            except ValueError:
                continue
        if not cand:
            break
        top_m, top_p = cand[0]
        contested = [(top_m, top_p)] + [
            (m, p) for m, p in cand[1:]
            if top_p + p > 0 and p / (top_p + p) >= BAND]
        if len(contested) == 1:
            mv = top_m                       # forced to the human favorite
        else:
            ws = [p for _, p in contested]
            mv = rng.choices([m for m, _ in contested], weights=ws)[0]
        out.append(mv)
        cur.push(mv)
    return out


if __name__ == "__main__":
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            done = {json.loads(l)["n"] for l in f if l.strip()}
    rows = [json.loads(l) for l in open(SRC)]
    print(f"{len(rows)} positions, {len(done)} done", flush=True)
    with open(OUT, "a") as out:
        for i, r in enumerate(rows):
            if r["n"] in done:
                continue
            b = chess.Board(r["fen"])
            samples = []
            for k in range(K):
                rng = random.Random(r["n"] * 663_003 + k)   # disjoint space
                line = rollout_gated(b, rng)
                samples.append([m.uci() for m in line])
            rnds = []
            for j in range(K):
                rng = random.Random(r["n"] * 7919 + 100 + j)
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
            out.write(json.dumps({"n": r["n"], "samples": samples,
                                  "randoms": rnds},
                                 separators=(",", ":")) + "\n")
            out.flush()
            print(f"pos {i + 1}/{len(rows)} (n={r['n']})", flush=True)
    print("PASS B MULTI DONE", flush=True)
