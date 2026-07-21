"""Analysis over the overnight shards: lift tables with Wilson CIs per plan
per regime, the structure->plan evidence table, and plan->outcome prices."""
from __future__ import annotations

import collections
import glob
import json
import math
import statistics

SHARDS = "/Users/avismara/Development/chess-plans/experiments/lift_shards"


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def fam(l):
    return l.split(":")[1]


if __name__ == "__main__":
    rows = []
    for path in sorted(glob.glob(f"{SHARDS}/shard_*.jsonl")):
        with open(path) as f:
            rows.extend(json.loads(l) for l in f)
    N = len(rows)
    print(f"anchors: {N}")

    for regime, aleg, rleg in (("FAST h12/t2", "af", "rf"),
                               ("SLOW h25/t6", "as", "rs")):
        a_cnt = collections.Counter()
        r_cnt = collections.Counter()
        for r in rows:
            for l in set(map(fam, r[aleg])):
                a_cnt[l] += 1
            for l in set(map(fam, r[rleg])):
                r_cnt[l] += 1
        print(f"\n== {regime} ==")
        print(f"{'plan':>26} | {'P(actual)':>9} | {'P(random)':>9} | "
              f"{'lift':>5} | lift 95% CI")
        for k in sorted(set(a_cnt) | set(r_cnt)):
            pa, pr = a_cnt[k] / N, r_cnt[k] / N
            lo_a, hi_a = wilson(a_cnt[k], N)
            lo_r, hi_r = wilson(r_cnt[k], N)
            lift = pa / pr if pr else float("inf")
            lo = lo_a / hi_r if hi_r else float("inf")
            hi = hi_a / lo_r if lo_r else float("inf")
            print(f"{k:>26} | {100*pa:>8.2f}% | {100*pr:>8.2f}% | "
                  f"{lift:>5.2f} | [{lo:.2f}, {hi if hi != float('inf') else 999:.2f}]")

    # plan -> outcome (slow regime, actual leg, family+side -> mover score)
    print("\n== plan -> outcome (actual futures, h25; score of the plan's side) ==")
    sc = collections.defaultdict(list)
    base = []
    for r in rows:
        s = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[r["result"]]
        base.append(s)
        for l in set(r["as"]):
            side, f = l.split(":")[0], fam(l)
            sc[f].append(s if side == "W" else 1.0 - s)
    print(f"  baseline (White persp mean): {statistics.mean(base):.3f}")
    for k in sorted(sc):
        if len(sc[k]) >= 50:
            print(f"  {k:>26}: {statistics.mean(sc[k]):.3f} (n={len(sc[k])})")

    # structure -> plan table (top structures x slow-regime actual plans)
    print("\n== structure -> plan rates (actual h25; owner-side plans only) ==")
    struct_rows = collections.defaultdict(list)
    for r in rows:
        for st in r["structures"]:
            struct_rows[st].append(r)
    for st, rs in sorted(struct_rows.items(), key=lambda kv: -len(kv[1]))[:12]:
        nm, owner = st.rsplit(":", 1)
        cnt = collections.Counter()
        for r in rs:
            for l in set(r["as"]):
                if l.startswith(owner + ":"):
                    cnt[fam(l)] += 1
        top = ", ".join(f"{k} {100*v/len(rs):.0f}%" for k, v in cnt.most_common(4))
        print(f"  {st:>24} (n={len(rs):>5}): {top}")
