"""benchmark_scorecard — where are we? Score the banked k-study set (300
positions, K=16 Maia samples, the actual GM continuation, structures) as a
plan SUGGESTER, no pipe needed.

Treats Maia's K=16 rollout distribution as the system's plan prediction and
the GM's actual 25-ply continuation as ground truth. Reports:

  COVERAGE     % positions where our grammar names >= 1 plan in the actual
  PREDICTION   Maia-suggests-GM precision/recall/F1 + Jaccard, vs a random-
               line baseline (the honest floor)
  CALIBRATION  bin Maia per-position frequency; is P(GM plays it | Maia says
               f) ~ f? (the reliability claim, tested directly)
  PER-PLAN     precision & recall of each family as a Maia->GM predictor

Uses kstudy_reduce.load_rows (merges base+ext to 16, vocab-guarded).
"""
from __future__ import annotations

import collections
import statistics
import sys

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/research/experiments")
from kstudy_reduce import load_rows


def fam(l):
    return l.split(":", 1)[1] if ":" in l else l


def jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else 1.0


if __name__ == "__main__":
    rows, _ = load_rows()
    rows = [r for r in rows if len(r["samples"]) >= 16]
    N = len(rows)
    print(f"scored positions: {N} (K=16 Maia samples each)\n")

    # ---- COVERAGE ----
    cov = sum(1 for r in rows if r["actual_slow"])
    print(f"COVERAGE: grammar names >= 1 plan in the actual GM future in "
          f"{cov}/{N} ({100*cov/N:.0f}%)")

    # ---- PREDICTION: Maia modal set (freq >= 0.5) vs actual ----
    def maia_set(r, thr):
        c = collections.Counter()
        for s in r["samples"]:
            for l in set(s):
                c[l] += 1
        k = len(r["samples"])
        return {l for l, v in c.items() if v / k >= thr}

    for thr in (0.5, 0.3):
        tp = fp = fn = 0
        js = []
        for r in rows:
            pred = maia_set(r, thr)
            act = set(r["actual_slow"])
            tp += len(pred & act)
            fp += len(pred - act)
            fn += len(act - pred)
            js.append(jacc(pred, act))
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
        print(f"\nPREDICTION (Maia freq >= {thr:.0%} -> suggest): "
              f"precision {prec:.2f}, recall {rec:.2f}, F1 {f1:.2f}, "
              f"Jaccard {statistics.mean(js):.3f}")

    # ---- CALIBRATION: does Maia freq predict GM play rate? ----
    bins = collections.defaultdict(lambda: [0, 0])   # bin -> [gm_played, total]
    for r in rows:
        c = collections.Counter()
        for s in r["samples"]:
            for l in set(s):
                c[l] += 1
        k = len(r["samples"])
        act = set(r["actual_slow"])
        for l, v in c.items():
            f = v / k
            b = min(int(f * 5), 4)                   # bins 0-.2 .. .8-1
            bins[b][1] += 1
            if l in act:
                bins[b][0] += 1
    print("\nCALIBRATION (does Maia's per-position frequency match GM play "
          "rate?)")
    print(f"  {'maia freq bin':>14} | {'GM played':>9} | {'n':>6} | reliability")
    for b in range(5):
        played, tot = bins[b]
        if tot:
            lo, hi = b * 0.2, (b + 1) * 0.2
            rate = played / tot
            print(f"  {f'{lo:.1f}-{hi:.1f}':>14} | {rate:>8.1%} | {tot:>6} | "
                  f"{'#' * round(rate * 30)}")

    # ---- PER-PLAN precision/recall as a Maia->GM predictor ----
    print("\nPER-PLAN (Maia freq>=0.3 as predictor of the GM plan; n>=15):")
    fam_tp = collections.Counter()
    fam_pred = collections.Counter()
    fam_act = collections.Counter()
    for r in rows:
        pred = maia_set(r, 0.3)
        act = set(r["actual_slow"])
        for l in pred:
            fam_pred[fam(l)] += 1
            if l in act:
                fam_tp[fam(l)] += 1
        for l in act:
            fam_act[fam(l)] += 1
    print(f"  {'plan':>26} | {'prec':>5} | {'rec':>5} | {'gm n':>5}")
    for f in sorted(fam_act, key=lambda x: -fam_act[x]):
        if fam_act[f] < 15:
            continue
        p = fam_tp[f] / fam_pred[f] if fam_pred[f] else 0
        rc = fam_tp[f] / fam_act[f] if fam_act[f] else 0
        print(f"  {f:>26} | {p:>5.2f} | {rc:>5.2f} | {fam_act[f]:>5}")
