#!/usr/bin/env python3
"""Re-score the audited sample under the patched dynamism (adjusted-
material compensation) using the STORED gold numbers — no new engine
calls — plus a mirror-invariance check of the geometry components."""
from __future__ import annotations

import json
import os
import sys

ROOT = "/Users/avismara/Development/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")
sys.path.insert(0, f"{ROOT}/lucena-plans/src")

import chess

from dynamism import dynamism
from audit_sharpness import load_roots

HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "audit_report.json")))["rows"]

roots = {fen: (pvs, rolls) for fen, pvs, rolls in load_roots()}

moved = 0
order = ["DEAD", "QUIET", "DYNAMIC", "SHARP", "RAZOR"]
per = {b: [] for b in order}
scores, punish = [], []
for r in rows:
    pvs, rolls = roots[r["fen"]]
    d = dynamism(r["fen"], pvs, rolls)
    if d["bucket"] != r["bucket"]:
        moved += 1
    per[d["bucket"]].append(r["punish"])
    scores.append(d["score"])
    punish.append(r["punish"])

print(f"re-bucketed {moved}/{len(rows)} positions")
print(f"{'bucket':<9}{'n':>4} {'punish':>8}")
for b in order:
    if per[b]:
        print(f"{b:<9}{len(per[b]):>4} "
              f"{sum(per[b]) / len(per[b]):>8.1f}")

import numpy as np
ra = np.argsort(np.argsort(scores))
rb = np.argsort(np.argsort(punish))
print(f"spearman(score, punish) = {float(np.corrcoef(ra, rb)[0, 1]):.3f}")

# mirror invariance (geometry-only legs): score(fen) == score(mirror)
bad = 0
for r in rows[:120]:
    m = chess.Board(r["fen"]).mirror().fen()
    a = dynamism(r["fen"], None, None)
    b = dynamism(m, None, None)
    if a["score"] != b["score"]:
        bad += 1
        if bad <= 3:
            print("mirror mismatch:", r["fen"], a["score"], b["score"])
print(f"mirror check (geometry legs, 120 fens): {bad} mismatches")
