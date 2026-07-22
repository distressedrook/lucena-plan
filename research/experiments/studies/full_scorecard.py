"""full_scorecard — the calibration scorecard at full 4000-position scale
(the 300-position k-study version scaled up using the banked GPU shards).
Runs standalone; writes full_scorecard_report.txt.
"""
from __future__ import annotations

import chess
import collections
import glob
import json
import statistics
import sys

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
from plan_diff import labels

D = "/Users/avismara/Development/lucena/lucena-plans/research/experiments"


def fam(l):
    return l.split(":", 1)[1] if ":" in l else l


if __name__ == "__main__":
    bench = {json.loads(l)["id"]: json.loads(l)
             for l in open(f"{D}/benchmark_v1.jsonl")}
    maia = {}
    for p in sorted(glob.glob(f"{D}/maia_shards/bench_*.jsonl")):
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                maia[r["id"]] = r

    rows = []
    n_done = 0
    for _id, r in bench.items():
        m = maia.get(_id)
        if not m:
            continue
        b = chess.Board(r["fen"])
        actual = labels(b, [chess.Move.from_uci(u) for u in r["actual_ucis"]],
                        25, 6)
        sample_labs = [labels(b, [chess.Move.from_uci(u) for u in s], 25, 6)
                       for s in m["samples"]]
        rows.append({"actual": actual, "sample_labs": sample_labs})
        n_done += 1
        if n_done % 500 == 0:
            print(f"  {n_done} positions labeled", flush=True)

    N = len(rows)
    out = [f"scored positions: {N} (K=16 Maia samples each)"]

    cov = sum(1 for r in rows if r["actual"])
    out.append(f"COVERAGE: {cov}/{N} ({100*cov/N:.0f}%)")

    for thr in (0.5, 0.3):
        tp = fp = fn = 0
        js = []
        for r in rows:
            c = collections.Counter()
            for sl in r["sample_labs"]:
                for l in set(sl):
                    c[l] += 1
            k = len(r["sample_labs"])
            pred = {l for l, v in c.items() if v / k >= thr}
            act = set(r["actual"])
            tp += len(pred & act)
            fp += len(pred - act)
            fn += len(act - pred)
            u = pred | act
            js.append(len(pred & act) / len(u) if u else 1.0)
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        out.append(f"PREDICTION (Maia freq >= {thr:.0%}): precision {prec:.2f}, "
                   f"recall {rec:.2f}, F1 {f1:.2f}, "
                   f"Jaccard {statistics.mean(js):.3f}")

    bins = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        c = collections.Counter()
        for sl in r["sample_labs"]:
            for l in set(sl):
                c[l] += 1
        k = len(r["sample_labs"])
        act = set(r["actual"])
        for l, v in c.items():
            f_ = v / k
            b_ = min(int(f_ * 5), 4)
            bins[b_][1] += 1
            if l in act:
                bins[b_][0] += 1
    out.append("CALIBRATION:")
    for b_ in range(5):
        played, tot = bins[b_]
        if tot:
            lo, hi = b_ * 0.2, (b_ + 1) * 0.2
            out.append(f"  {lo:.1f}-{hi:.1f}: GM played {played/tot:.1%}, "
                       f"n={tot}")

    fam_tp = collections.Counter()
    fam_pred = collections.Counter()
    fam_act = collections.Counter()
    for r in rows:
        c = collections.Counter()
        for sl in r["sample_labs"]:
            for l in set(sl):
                c[l] += 1
        k = len(r["sample_labs"])
        pred = {l for l, v in c.items() if v / k >= 0.3}
        act = set(r["actual"])
        for l in pred:
            fam_pred[fam(l)] += 1
            if l in act:
                fam_tp[fam(l)] += 1
        for l in act:
            fam_act[fam(l)] += 1
    out.append("PER-PLAN (freq>=0.3 predictor; n>=30):")
    for f in sorted(fam_act, key=lambda x: -fam_act[x]):
        if fam_act[f] < 30:
            continue
        p = fam_tp[f] / fam_pred[f] if fam_pred[f] else 0
        rc = fam_tp[f] / fam_act[f] if fam_act[f] else 0
        out.append(f"  {f:>26}: prec {p:.2f}, rec {rc:.2f}, n={fam_act[f]}")

    text = "\n".join(out)
    print(text)
    with open(f"{D}/full_scorecard_report.txt", "w") as g:
        g.write(text + "\n")
