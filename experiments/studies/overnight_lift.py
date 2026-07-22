"""OVERNIGHT RUN — corpus-scale calibration of the plan namer (no engine,
no Maia: actual continuations vs seeded random lines, pure geometry).

Per GM game, anchors at plies 20/30/40/50 (game permitting). Per anchor:
  actual leg  — the next 25 plies as played
  random leg  — 25 seeded random legal plies
each parsed at BOTH regimes: h12/tail2 (fast families) and h25/tail6 (slow).
Rows carry the anchor's structure flags and the game result, so one pass
yields: (1) per-plan per-horizon lift with CIs, (2) the structure->plan
evidence table at scale, (3) refreshed plan->outcome prices.

Output: shards experiments/lift_shards/shard_*.jsonl + final report.
Resume-safe: existing shards are skipped.
"""
from __future__ import annotations

import json
import os
import random
import sys
from multiprocessing import Pool

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans")
from plan_diff import labels, snapshot

PGN = "/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn"
SHARDS = "/Users/avismara/Development/lucena/lucena-plans/experiments/lift_shards"
ANCHORS = (20, 30, 40, 50)
H_FAST, T_FAST = 12, 2
H_SLOW, T_SLOW = 25, 6
GAMES_PER_SHARD = 500
WORKERS = 8


def process_games(args):
    shard_id, offsets = args
    path = f"{SHARDS}/shard_{shard_id:04d}.jsonl"
    if os.path.exists(path):
        return shard_id, -1
    rows = 0
    with open(PGN, encoding="latin-1") as f, open(path + ".tmp", "w") as out:
        for n, off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                res = game.headers.get("Result", "*")
                if res not in ("1-0", "0-1", "1/2-1/2"):
                    continue
                moves = list(game.mainline_moves())
            except Exception:
                continue
            for a in ANCHORS:
                if len(moves) < a + H_SLOW + 1:
                    continue
                b = game.board()
                for mv in moves[:a]:
                    b.push(mv)
                actual = moves[a:a + H_SLOW]
                rng = random.Random(n * 1000 + a)
                cur = b.copy()
                rnd = []
                for _ in range(H_SLOW):
                    lg = list(cur.legal_moves)
                    if not lg:
                        break
                    m = rng.choice(lg)
                    rnd.append(m)
                    cur.push(m)
                try:
                    row = {
                        "n": n, "anchor": a, "result": res,
                        "structures": sorted(f"{nm}:{'W' if o else 'B'}"
                                             for nm, o in snapshot(b)["structures"]),
                        "af": sorted(labels(b, actual, H_FAST, T_FAST)),
                        "as": sorted(labels(b, actual, H_SLOW, T_SLOW)),
                        "rf": sorted(labels(b, rnd, H_FAST, T_FAST)),
                        "rs": sorted(labels(b, rnd, H_SLOW, T_SLOW)),
                    }
                except Exception:
                    continue
                out.write(json.dumps(row, separators=(",", ":")) + "\n")
                rows += 1
    os.rename(path + ".tmp", path)
    return shard_id, rows


def index_games():
    """(game_number, byte_offset) for every game in the pgn."""
    out = []
    n = 0
    with open(PGN, "rb") as f:
        off = f.tell()
        for line in iter(f.readline, b""):
            if line.startswith(b"[Event "):
                n += 1
                out.append((n, off))
            off = f.tell()
    return out


if __name__ == "__main__":
    os.makedirs(SHARDS, exist_ok=True)
    idx = index_games()
    print(f"indexed {len(idx)} games", flush=True)
    shards = [(i, idx[i * GAMES_PER_SHARD:(i + 1) * GAMES_PER_SHARD])
              for i in range((len(idx) + GAMES_PER_SHARD - 1) // GAMES_PER_SHARD)]
    done = 0
    with Pool(WORKERS) as pool:
        for sid, rows in pool.imap_unordered(process_games, shards):
            done += 1
            print(f"shard {sid:04d}: {rows if rows >= 0 else 'skipped'} rows "
                  f"({done}/{len(shards)} shards)", flush=True)
    print("ALL SHARDS DONE", flush=True)
    os.system(f"~/Development/chess-lab/.venv/bin/python "
              f"/Users/avismara/Development/lucena/lucena-plans/experiments/"
              f"studies/lift_report.py")
