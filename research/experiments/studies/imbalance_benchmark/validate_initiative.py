#!/usr/bin/env python3
"""Validate the initiative score (src/initiative.py) against the labeled
imbalance cache — the same discipline as king_danger: a number is only real
once it predicts something it should.

Test: among REAL-DEFICIT positions (naive |gap| >= 150), the material-down
side either HELD (engine equalish, |cp| <= 100) or FAILED (engine decisive
FOR the material-up side). Does the underdog's initiative differential
separate the two classes?  Reported for the static-only score (geometry, no
engine) and the combined score (static + PV forcing-fraction), plus AUC via
Mann-Whitney and the per-bin hold rate.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/Users/avismara/Projects/active/lucena/lucena-plans"
sys.path.insert(0, os.path.join(ROOT, "src"))
import chess
from initiative import initiative

cache = [json.loads(l) for l in open(os.path.join(HERE, "labeled_cache.jsonl"))]

rows = []
for r in cache:
    naive = r.get("naive_cp")
    cp = r.get("cp")
    if naive is None or cp is None or abs(naive) < 150:
        continue
    underdog_white = naive < 0          # White is material-down
    # class: held (equalish) vs failed (decisive for the material-UP side)
    if abs(cp) <= 100:
        held = 1
    elif (cp > 100 and not underdog_white) or (cp < -100 and underdog_white):
        held = 0                        # material-up side is winning: comp failed
    else:
        continue                        # material-DOWN side is winning — different story
    try:
        iv = initiative(r["fen"], r["pvs"])
        iv_static = initiative(r["fen"], None)
    except Exception:
        continue
    sgn = 1 if underdog_white else -1
    rows.append({
        "held": held,
        "diff_comb": sgn * iv["diff"],           # underdog-favourable, engine-spread
        "diff_stat": sgn * (iv_static["white"]["score"]
                            - iv_static["black"]["score"]),  # geometry-only prior
        "type": r.get("type"),
    })

n1 = sum(r["held"] for r in rows); n0 = len(rows) - n1
print(f"n = {len(rows)} real-deficit positions: held {n1}, failed {n0}")

def auc(key):
    xs = sorted(rows, key=lambda r: r[key])
    # Mann-Whitney with midranks (ties)
    ranks = {}
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1][key] == xs[i][key]:
            j += 1
        mid = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[id(xs[k])] = mid
        i = j + 1
    r1 = sum(ranks[id(r)] for r in rows if r["held"])
    u1 = r1 - n1 * (n1 + 1) / 2
    return u1 / (n1 * n0)

try:
    from scipy.stats import mannwhitneyu
    import numpy as np
    for key, label in (("diff_stat", "STATIC-only"), ("diff_comb", "COMBINED")):
        a = [r[key] for r in rows if r["held"]]
        b = [r[key] for r in rows if not r["held"]]
        u, p = mannwhitneyu(a, b, alternative="greater")
        print(f"{label:12} AUC {auc(key):.3f}   mean held {np.mean(a):+.3f} "
              f"vs failed {np.mean(b):+.3f}   p(one-sided) {p:.2e}")
except ImportError:
    for key, label in (("diff_stat", "STATIC-only"), ("diff_comb", "COMBINED")):
        print(f"{label:12} AUC {auc(key):.3f}")

# hold-rate by combined-initiative bin — the reliability read
print("\nhold rate by underdog initiative differential (combined):")
bins = [(-2, -0.3), (-0.3, -0.1), (-0.1, 0.1), (0.1, 0.3), (0.3, 2)]
for lo, hi in bins:
    sel = [r for r in rows if lo <= r["diff_comb"] < hi]
    if not sel:
        continue
    hr = sum(r["held"] for r in sel) / len(sel)
    print(f"  [{lo:+.1f},{hi:+.1f})  n={len(sel):4}  held {hr:.0%}")
