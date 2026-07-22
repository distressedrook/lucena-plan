"""kstudy_reduce — the k-study payload: how many Maia rollouts buy a stable
per-position plan-frequency estimate.

Each ksample row holds `samples`: K independent Maia rollout label-sets for one
anchor position. For that position and each plan, the frequency estimate at
budget k is (# of the first k rollouts that named the plan) / k. The question
is at what k that estimate stops moving.

Two curves, both averaged over (position, plan) cells that are ever non-zero:
  - incremental[k] = mean |freq_k - freq_{k-1}|   (honest: no ground truth)
  - to_final[k]    = mean |freq_k - freq_K|        (gap to the full budget)
K* = smallest k with incremental[k] < SETTLE. That K* is the number to use as
the Maia contract in suggest.py's VERIFY tier.

Also: per-plan K-budget marginal P(plan) across positions with binomial SE, and
the Maia-vs-actual marginal gap (the "over-indexes outposts" audit at scale).

Writes kstudy_report.txt (dashboard reads it). Safe to run on a partial set;
it reports how many of the 12 shards it saw.

    ./kstudy_reduce.py
"""
from __future__ import annotations

import glob
import json
import math

BASE = "/Users/avismara/Development/lucena/lucena-plans/experiments"
SHARDS = f"{BASE}/maia_shards"
OUT = f"{BASE}/kstudy_report.txt"
EXPECTED_KSHARDS = 12
SETTLE = 0.03           # incremental delta below this = "stable"


def load_rows() -> tuple[list[dict], int]:
    rows = []
    shards = sorted(glob.glob(f"{SHARDS}/ksample_[0-9]*.jsonl"))
    for p in shards:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    # merge K-extension shards (kstudy_extend.py): +8 samples per anchor.
    # Vocabulary guard: the originals were labeled under an older grammar, so
    # extension labels are FILTERED to the vocabulary realized in the
    # original samples — otherwise new-grammar plans fake a jump at k=9.
    ext = {}
    for p in sorted(glob.glob(f"{SHARDS}/ksample_ext_*.jsonl")):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    e = json.loads(line)
                    ext[(e["n"], e["anchor"])] = e["ext_samples"]
    if ext:
        vocab = {lab for r in rows for s in r["samples"] for lab in s}
        for r in rows:
            e = ext.get((r["n"], r["anchor"]))
            if e:
                r["samples"] = r["samples"] + [
                    [lab for lab in s if lab in vocab] for s in e]
    return rows, len(shards)


def reduce_rows(rows: list[dict]) -> dict:
    if not rows:
        return {}
    K = min(len(r["samples"]) for r in rows)     # common budget (should be 8)

    # ---- convergence curves over (position, plan) cells ----
    # incr[k] and fin[k] accumulate |Δ|; cnt counts cells contributing.
    incr = [0.0] * (K + 1)
    fin = [0.0] * (K + 1)
    cnt = 0
    for r in rows:
        samples = r["samples"][:K]
        plans = set()
        for s in samples:
            plans.update(s)
        if not plans:
            continue
        for plan in plans:
            hits = [1 if plan in s else 0 for s in samples]
            # running frequency at each budget k = 1..K
            run = []
            c = 0
            for k in range(1, K + 1):
                c += hits[k - 1]
                run.append(c / k)
            final = run[-1]
            for k in range(1, K + 1):
                if k >= 2:
                    incr[k] += abs(run[k - 1] - run[k - 2])
                fin[k] += abs(run[k - 1] - final)
            cnt += 1

    incremental = [incr[k] / cnt for k in range(1, K + 1)]   # index 0 -> k=1 (0)
    to_final = [fin[k] / cnt for k in range(1, K + 1)]

    # K* = first k>=2 whose incremental delta is below SETTLE
    kstar = None
    for k in range(2, K + 1):
        if incremental[k - 1] < SETTLE:
            kstar = k
            break

    # ---- per-plan marginal at full budget K, across positions ----
    # freq per position = share of K rollouts naming the plan; marginal = mean.
    plan_freqs: dict[str, list[float]] = {}
    actual_marg: dict[str, int] = {}
    npos = len(rows)
    for r in rows:
        samples = r["samples"][:K]
        seen = set()
        for s in samples:
            seen.update(s)
        for plan in seen:
            f = sum(1 for s in samples if plan in s) / K
            plan_freqs.setdefault(plan, []).append(f)
        for plan in r.get("actual_slow", []):
            actual_marg[plan] = actual_marg.get(plan, 0) + 1

    per_plan = []
    for plan, fs in plan_freqs.items():
        p = sum(fs) / npos                        # marginal over ALL positions
        se = math.sqrt(max(p * (1 - p), 0) / (npos * K))
        act = actual_marg.get(plan, 0) / npos
        per_plan.append((plan, p, se, act))
    per_plan.sort(key=lambda t: -t[1])

    return {
        "K": K, "npos": npos, "cells": cnt,
        "incremental": incremental, "to_final": to_final,
        "kstar": kstar, "settle": SETTLE, "per_plan": per_plan,
    }


def render(res: dict, nshards: int) -> str:
    if not res:
        return (f"k-study: 0/{EXPECTED_KSHARDS} ksample shards reduced "
                f"(no rows yet)")
    K = res["K"]
    L = []
    done = "COMPLETE" if nshards >= EXPECTED_KSHARDS else "PARTIAL"
    L.append(f"K-STUDY CONVERGENCE  [{done}: {nshards}/{EXPECTED_KSHARDS} "
             f"ksample shards, {res['npos']} positions, {res['cells']} "
             f"(pos,plan) cells, budget K={K}]")
    L.append("")
    if res["kstar"]:
        L.append(f"VERDICT: estimate settles at K*={res['kstar']} "
                 f"(incremental Δ < {res['settle']:.02f}). "
                 f"Use K={res['kstar']} rollouts for the Maia VERIFY contract.")
    else:
        L.append(f"VERDICT: still drifting at K={K} "
                 f"(incremental Δ never < {res['settle']:.02f}); "
                 f"Maia estimates need MORE than {K} rollouts — re-quote lift.")
    L.append("")
    L.append(f"  {'k':>2} | {'incr Δ':>8} | {'gap→K':>8} | curve")
    for k in range(1, K + 1):
        inc = res["incremental"][k - 1]
        gap = res["to_final"][k - 1]
        bar = "#" * round(gap * 60)
        mark = "  <- K*" if res["kstar"] == k else ""
        L.append(f"  {k:>2} | {inc:>8.4f} | {gap:>8.4f} | {bar}{mark}")
    L.append("")
    L.append("per-plan marginal at full budget (Maia freq vs GM-actual rate):")
    L.append(f"  {'plan':>22} | {'maia P':>7} | {'±SE':>6} | {'actual':>7} | gap")
    for plan, p, se, act in res["per_plan"]:
        gap = p - act
        flag = "  OVER" if gap > 0.05 else "  under" if gap < -0.05 else ""
        L.append(f"  {plan:>22} | {p:>6.3f} | {se:>6.4f} | {act:>6.3f} "
                 f"| {gap:>+6.3f}{flag}")
    return "\n".join(L)


def main() -> str:
    rows, nshards = load_rows()
    # rows already extended to 16 samples form the K=16 curve (the study's
    # target); un-extended rows would clamp K=min back to 8 and freeze the
    # panel at the stale K=8 verdict while the extension streams in
    ext_rows = [r for r in rows if len(r["samples"]) >= 16]
    parts = []
    if ext_rows:
        res16 = reduce_rows(ext_rows)
        hdr = (f"[K=16 EXTENSION: {len(ext_rows)}/{len(rows)} anchors "
               f"extended so far]")
        parts.append(hdr + "\n" + render(res16, nshards))
    base = reduce_rows(rows) if not ext_rows else None
    if base:
        parts.append(render(base, nshards))
    elif not ext_rows:
        parts.append(render({}, nshards))
    text = "\n".join(parts)
    with open(OUT, "w") as f:
        f.write(text + "\n")
    return text


if __name__ == "__main__":
    print(main())
