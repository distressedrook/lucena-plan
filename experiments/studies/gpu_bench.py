"""gpu_bench — the benchmark_v1 runner for the GPU machine.

Self-contained: needs benchmark_v1.jsonl + python-chess + a Maia backend.
No lucena repo, no PGN corpus, no grammar — raw UCIs are banked; labeling
happens back on the analysis machine under whatever grammar is current.

    python3 gpu_bench.py benchmark_v1.jsonl out_shards/ [--k 16] [--backend docker]

Backends (the top_policy(fen) -> [(uci, policy), ...] seam):
  docker   the lucena image (docker exec lucena-app-1), works anywhere the
           image runs; give the GPU to the container for the speedup
  lc0      any lc0 binary + maia weights speaking UCI with policy output;
           fill in Lc0Backend.top_policy for your setup

Per position: K sampled rollouts (HORIZON plies) with the 40-60 policy gate
(deviate from the top move only when p_i/(p_1+p_i) >= 0.40), seeds derived
from the position id — bit-reproducible anywhere. Shards of 50 positions,
resume-safe. Bring the shards back to experiments/ and reduce there.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import select
import subprocess
import time

import chess

HORIZON = 25
BAND = 0.40
PER_SHARD = 50


# ---------------------------------------------------------------- backends

class DockerBackend:
    SRV = ("import sys\n"
           "from lucena_engine.maia import MaiaEngine\n"
           "m=MaiaEngine()\n"
           "print('READY',flush=True)\n"
           "for line in sys.stdin:\n"
           "    fen=line.strip()\n"
           "    if not fen: break\n"
           "    ms=m.top_human_moves(fen,2400,n=5)\n"
           "    print(' '.join(f\"{x['uci']}:{x['policy']:.6f}\" for x in ms),"
           "flush=True)")

    def __init__(self, container="lucena-app-1"):
        self.container = container
        self.pipe = None

    def _spawn(self):
        p = subprocess.Popen(
            ["docker", "exec", "-i", self.container, "python3", "-u", "-c",
             self.SRV],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            bufsize=1)
        r, _, _ = select.select([p.stdout], [], [], 90.0)
        if not r or p.stdout.readline().strip() != "READY":
            p.terminate()
            raise BrokenPipeError("maia spawn failed")
        return p

    def top_policy(self, fen):
        for _ in range(6):
            try:
                if self.pipe is None or self.pipe.poll() is not None:
                    self.pipe = self._spawn()
                self.pipe.stdin.write(fen + "\n")
                r, _, _ = select.select([self.pipe.stdout], [], [], 30.0)
                if not r:
                    raise BrokenPipeError("timeout")
                line = self.pipe.stdout.readline().strip()
                if not line:
                    raise BrokenPipeError("empty")
                return [(u, float(p)) for u, p in
                        (tok.rsplit(":", 1) for tok in line.split())]
            except (BrokenPipeError, OSError, ValueError):
                try:
                    self.pipe.terminate()
                except Exception:
                    pass
                self.pipe = None
                time.sleep(10)
        raise RuntimeError("maia pipe irrecoverable")


class Lc0Backend:
    """Fill in for a bare lc0+maia-weights setup (UCI 'go nodes 1' with
    --verbose-move-stats exposes per-move P: parse the info strings)."""

    def __init__(self, binary, weights):
        raise NotImplementedError("wire your lc0 invocation here")


# ---------------------------------------------------------------- rollout

def rollout_gated(backend, b: chess.Board, rng: random.Random):
    cur = b.copy()
    out = []
    while len(out) < HORIZON and not cur.is_game_over():
        cand = []
        for u, p in backend.top_policy(cur.fen()):
            try:
                cand.append((cur.parse_uci(u), p))
            except ValueError:
                continue
        if not cand:
            break
        top_m, top_p = cand[0]
        contested = [(top_m, top_p)] + [
            (m, p) for m, p in cand[1:]
            if top_p + p > 0 and p / (top_p + p) >= BAND]
        mv = top_m if len(contested) == 1 else \
            rng.choices([m for m, _ in contested],
                        weights=[p for _, p in contested])[0]
        out.append(mv)
        cur.push(mv)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("outdir")
    ap.add_argument("--k", type=int, default=16)
    ap.add_argument("--backend", default="docker")
    ap.add_argument("--container", default="lucena-app-1")
    args = ap.parse_args()

    backend = DockerBackend(args.container) if args.backend == "docker" \
        else Lc0Backend(None, None)
    rows = [json.loads(l) for l in open(args.bench)]
    os.makedirs(args.outdir, exist_ok=True)
    nshards = (len(rows) + PER_SHARD - 1) // PER_SHARD
    for sid in range(nshards):
        path = f"{args.outdir}/bench_{sid:04d}.jsonl"
        if os.path.exists(path):
            continue
        batch = rows[sid * PER_SHARD:(sid + 1) * PER_SHARD]
        t0 = time.time()
        with open(path + ".tmp", "w") as out:
            for r in batch:
                b = chess.Board(r["fen"])
                # deterministic across machines (str hash() is salted):
                # id = "n<gamenum>_a<anchor>"
                gn, an = r["id"][1:].split("_a")
                seed_base = int(gn) * 1000 + int(an)
                samples = []
                for k in range(args.k):
                    rng = random.Random(seed_base * 100 + k)
                    line = rollout_gated(backend, b, rng)
                    samples.append([m.uci() for m in line])
                out.write(json.dumps({"id": r["id"], "k": args.k,
                                      "samples": samples},
                                     separators=(",", ":")) + "\n")
        os.rename(path + ".tmp", path)
        print(f"shard {sid:04d}/{nshards - 1} done "
              f"({time.time() - t0:.0f}s)", flush=True)
    print("GPU BENCH DONE", flush=True)
