"""kstudy_extend — extend the k-study from K=8 to K=16 on the SAME anchors.

Reads the banked ksample_*.jsonl rows (the 300 anchors, with their original
8 samples) and rolls 8 MORE independent Maia3-2400 sampled rollouts each,
using a disjoint seed space. Writes ksample_ext_*.jsonl shards carrying BOTH
the raw UCI lines (so the whole bank can be relabeled under any future
grammar) and the labels under the current grammar.

The reducer (kstudy_reduce) merges orig+ext and, to avoid the v4/v5
vocabulary mismatch faking a jump at k=9, restricts the convergence curve to
labels realized in the ORIGINAL samples.

Shard-checkpointed, resume-safe, same pipe-survival machinery as
overnight_maia. ~2,400 rollouts ~= the original k-leg's cost.
"""
from __future__ import annotations

import glob
import json
import os
import random

import chess

import overnight_maia as om          # reuse pipe, rollout, fen_at, labels
from plan_diff import labels

OUT_DIR = om.OUT_DIR
K_EXT = 8                            # samples 8..15 -> total K=16
PER_SHARD = 25


def load_k_rows() -> list[dict]:
    rows = []
    for p in sorted(glob.glob(f"{OUT_DIR}/ksample_[0-9]*.jsonl")):
        with open(p) as f:
            rows.extend(json.loads(l) for l in f if l.strip())
    return rows


if __name__ == "__main__":
    offsets = {}
    n = 0
    with open(om.PGN, "rb") as f:
        off = f.tell()
        for line in iter(f.readline, b""):
            if line.startswith(b"[Event "):
                n += 1
                offsets[n] = off
            off = f.tell()
    rows = load_k_rows()
    print(f"extending {len(rows)} k-anchors by {K_EXT} samples each", flush=True)
    pgn_f = open(om.PGN, encoding="latin-1")

    for sid in range((len(rows) + PER_SHARD - 1) // PER_SHARD):
        path = f"{OUT_DIR}/ksample_ext_{sid:03d}.jsonl"
        if os.path.exists(path):
            continue
        batch = rows[sid * PER_SHARD:(sid + 1) * PER_SHARD]
        with open(path + ".tmp", "w") as out:
            for r in batch:
                try:
                    b = om.fen_at(pgn_f, offsets, r["n"], r["anchor"])
                    ucis, labs = [], []
                    for k in range(K_EXT):
                        # disjoint seed space from the original run
                        rng = random.Random(
                            r["n"] * 100000 + r["anchor"] * 100 + 8 + k)
                        line = om.rollout(b, rng)
                        ucis.append([m.uci() for m in line])
                        labs.append(sorted(labels(b, line, 25, 6)))
                    out.write(json.dumps({
                        "n": r["n"], "anchor": r["anchor"],
                        "ext_ucis": ucis, "ext_samples": labs,
                    }, separators=(",", ":")) + "\n")
                except Exception as e:
                    print(f"ext error n={r['n']}: {e}", flush=True)
        os.rename(path + ".tmp", path)
        print(f"ext shard {sid:03d} done", flush=True)
    print("KSTUDY EXTENSION DONE", flush=True)
