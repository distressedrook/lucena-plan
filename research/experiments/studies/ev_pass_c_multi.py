"""Multi-line agreeability, PASS C: the report.

Inputs: ev_multi.jsonl (4 engine PVs + 4 random lines) and, when present,
ev_multi_maia.jsonl (16 Maia samples + 16 random lines). Labels everything
under the CURRENT grammar (slow regime h25/t6) at run time — reruns free.

RULING (2026-07-22): an engine PV counts as an alternative PLAN only if its
eval is EQUAL to the best line (|cp_i - cp_1| <= EQUAL_BAND) — a losing 4th
line is not a sound plan. Multiplicity = number of equal-eval lines' plans.
The random-union floor is matched to the number of ADMITTED lines.

Metrics, all union-floored (a union of k lines must beat a union of k
random lines, not a single-line floor):
  any-line agreement    P(>=1 GM plan appears in ANY admitted line)
  plan multiplicity     distinct plan families across admitted PVs
  distributional        per GM plan: in how many of the 16 Maia samples?
"""
from __future__ import annotations

import collections
import json
import os
import statistics
import sys

import chess

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-plans/src")
from plan_diff import labels

D = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments"
EQUAL_BAND = 50               # |cp_i - cp_1| <= 50 -> the line is "equal"


def lab(fen, ucis):
    b = chess.Board(fen)
    return labels(b, [chess.Move.from_uci(u) for u in ucis], 25, 6)


def fams(ls):
    return {x.split(":", 1)[1].split(":")[0] for x in ls}


if __name__ == "__main__":
    rows = [json.loads(l) for l in open(f"{D}/ev_multi.jsonl")]
    maia = {}
    if os.path.exists(f"{D}/ev_multi_maia.jsonl"):
        maia = {r["n"]: r for r in
                (json.loads(l) for l in open(f"{D}/ev_multi_maia.jsonl"))}
    n = len(rows)
    print(f"positions: {n} (maia leg: {len(maia)})")

    any_hit = un_floor = 0
    single_hit = 0
    mults, mults_r = [], []
    cover_by_k = collections.Counter()     # GM plans found at PV rank k first
    m_any = m_floor = 0
    m_depth = []                           # per shared plan: samples containing it
    n_admitted = []
    for r in rows:
        actual = lab(r["fen"], r["actual"])
        af = fams(actual)
        # eval-equality gate: admit only PVs within EQUAL_BAND of the best
        cp1 = r["pvs"][0]["cp"] if r["pvs"] else 0
        admitted = [p for p in r["pvs"]
                    if abs(p["cp"] - cp1) <= EQUAL_BAND]
        n_admitted.append(len(admitted))
        pv_labs = [lab(r["fen"], p["ucis"]) for p in admitted]
        # floor matched to admitted count, not the full 4
        rn_labs = [lab(r["fen"], u) for u in r["randoms"][:len(admitted)]]
        pv_f = [fams(x) for x in pv_labs]
        rn_f = [fams(x) for x in rn_labs]
        union_pv = set().union(*pv_f) if pv_f else set()
        union_rn = set().union(*rn_f) if rn_f else set()
        if af & union_pv:
            any_hit += 1
        if af & union_rn:
            un_floor += 1
        if pv_f and af & pv_f[0]:
            single_hit += 1
        mults.append(len(union_pv))
        mults_r.append(len(union_rn))
        for f in af:
            for k, pf in enumerate(pv_f):
                if f in pf:
                    cover_by_k[k] += 1
                    break
        m = maia.get(r["n"])
        if m:
            sm = [fams(lab(r["fen"], u)) for u in m["samples"]]
            rm = [fams(lab(r["fen"], u)) for u in m["randoms"]]
            u_sm = set().union(*sm) if sm else set()
            u_rm = set().union(*rm) if rm else set()
            if af & u_sm:
                m_any += 1
            if af & u_rm:
                m_floor += 1
            for f in af & u_sm:
                m_depth.append(sum(1 for x in sm if f in x))

    print(f"\n== ENGINE MultiPV=4, eval-equal gate |dcp|<={EQUAL_BAND} ==")
    print(f"  admitted lines/position          : "
          f"mean {statistics.mean(n_admitted):.1f} | dist "
          + " ".join(f"{k}:{n_admitted.count(k)}" for k in (1, 2, 3, 4)))
    print(f"  single-PV agreement (rank1 only) : {100*single_hit/n:.0f}%")
    print(f"  ANY-line agreement (union of 4)  : {100*any_hit/n:.0f}%")
    print(f"  union floor (4 random lines)     : {100*un_floor/n:.0f}%")
    print(f"  discrimination (any/floor)       : "
          f"{any_hit/max(un_floor,1):.2f}x")
    print(f"  plan multiplicity across 4 PVs   : "
          f"mean {statistics.mean(mults):.1f} vs random-union "
          f"{statistics.mean(mults_r):.1f}")
    tot = sum(cover_by_k.values())
    if tot:
        print(f"  GM plans first found at PV rank  : "
              + " ".join(f"pv{k+1}:{100*cover_by_k[k]/tot:.0f}%"
                         for k in sorted(cover_by_k)))
    if maia:
        nm = len([r for r in rows if r["n"] in maia])
        print(f"\n== MAIA K=16 distributional ==")
        print(f"  any-sample agreement             : {100*m_any/nm:.0f}%")
        print(f"  union floor (16 random lines)    : {100*m_floor/nm:.0f}%")
        print(f"  discrimination                   : "
              f"{m_any/max(m_floor,1):.2f}x")
        if m_depth:
            print(f"  shared-plan depth (of 16 samples): "
                  f"median {statistics.median(m_depth):.0f}, "
                  f"mean {statistics.mean(m_depth):.1f}")
