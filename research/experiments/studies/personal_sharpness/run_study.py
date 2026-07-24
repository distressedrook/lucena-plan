#!/usr/bin/env python3
"""Personal-sharpness study over the audited sharpness sample (which
carries the objective punishment gold): Maia policy at 3 anchor levels +
engine child evals -> sharpness_profile per position. Banks the raw legs
(policy + child evals) JSONL so the metric is re-scorable without new
Maia/engine calls (the eng_shards precedent).

Reports:
  - danger / trap_mass distributions per level + the monotone-easing rate
    (danger should fall with rating — internal validity of the concept)
  - the 2-D matrix: objective dynamism bucket x trap bucket @1300/1800
  - correlation of danger_L with the objective punish gold
  - the off-diagonal gold cell examples: objectively-quiet cohort traps
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

ROOT = "/Users/avismara/Development/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")
sys.path.insert(0, f"{ROOT}/lucena-plans/src")

import chess
import chess.engine

from lucena_engine.maia import MaiaEngine
from personal_sharpness import sharpness_profile

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "..", "sharpness_audit", "audit_report.json")
BANK = os.path.join(HERE, "bank.jsonl")
OUT = os.path.join(HERE, "study_report.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"
LEVELS = (1300, 1800, 2400)
TOP_N = 6
CHILD_NODES = 60_000


def build_bank(rows):
    os.environ.setdefault(
        "LUCENA_MAIA",
        f"{ROOT}/.venv-maia/bin/python {ROOT}/engine/scripts/maia_policy_uci.py")
    maia = MaiaEngine()
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": 4, "Hash": 512})
    done = set()
    if os.path.exists(BANK):
        done = {json.loads(l)["fen"] for l in open(BANK)}
    try:
        with open(BANK, "a") as out:
            for i, r in enumerate(rows):
                fen = r["fen"]
                if fen in done:
                    continue
                b = chess.Board(fen)
                policy = {}
                union = set()
                for elo in LEVELS:
                    rs = maia.top_human_moves(fen, elo, n=TOP_N)
                    policy[elo] = [{"uci": x["uci"],
                                    "policy": x.get("policy")} for x in rs]
                    union |= {x["uci"] for x in rs}
                child = {}
                for u in sorted(union):
                    mv = chess.Move.from_uci(u)
                    if mv not in b.legal_moves:
                        continue
                    b2 = b.copy(stack=False)
                    b2.push(mv)
                    info = engine.analyse(
                        b2, chess.engine.Limit(nodes=CHILD_NODES))
                    child[u] = info["score"].white().score(mate_score=2_000)
                out.write(json.dumps({"fen": fen, "policy": policy,
                                      "child_cp": child}) + "\n")
                out.flush()
                if (i + 1) % 25 == 0:
                    print(f"banked {i + 1}/{len(rows)}")
    finally:
        maia.close()
        engine.quit()


def main():
    rows = json.load(open(AUDIT))["rows"]
    build_bank(rows)
    bank = {json.loads(l)["fen"]: json.loads(l) for l in open(BANK)}

    import numpy as np
    per_level = defaultdict(list)
    matrix = {e: Counter() for e in LEVELS}
    gold_pairs = defaultdict(list)
    monotone = 0
    scored = 0
    cohort_traps = []
    results = []
    for r in rows:
        bk = bank.get(r["fen"])
        if bk is None:
            continue
        pol = {int(e): v for e, v in bk["policy"].items()}
        prof = sharpness_profile(r["fen"], None, pol, bk["child_cp"])
        if not prof["levels"]:
            continue
        scored += 1
        monotone += bool(prof.get("monotone_easing"))
        for elo, s in prof["levels"].items():
            per_level[elo].append(s)
            matrix[elo][(r["bucket"], s["bucket"])] += 1
            gold_pairs[elo].append((s["danger"], r["punish"]))
        s13 = prof["levels"].get(1300)
        if s13 and s13["bucket"] == "TRAP" and \
                r["bucket"] in ("DEAD", "QUIET", "DYNAMIC"):
            cohort_traps.append({"fen": r["fen"], "objective": r["bucket"],
                                 **{k: s13[k] for k in
                                    ("danger", "trap_mass")},
                                 "trap_move": s13.get("trap_move")})
        results.append({"fen": r["fen"], "objective": r["bucket"],
                        "punish": r["punish"], "profile": {
                            e: {k: v for k, v in s.items() if k != "rows"}
                            for e, s in prof["levels"].items()}})

    print(f"scored {scored}/{len(rows)}; "
          f"monotone easing (danger falls with rating): "
          f"{monotone}/{scored} = {monotone / scored:.0%}")
    print(f"\n{'elo':>6} {'danger':>8} {'trap_mass':>10} "
          f"{'TRAP':>6} {'SLIP':>6} {'SAFE':>6}")
    for elo in LEVELS:
        ss = per_level[elo]
        bkts = Counter(s["bucket"] for s in ss)
        print(f"{elo:>6} {np.mean([s['danger'] for s in ss]):>8.1f} "
              f"{np.mean([s['trap_mass'] for s in ss]):>10.3f} "
              f"{bkts['TRAP']:>6} {bkts['SLIPPERY']:>6} {bkts['SAFE']:>6}")

    for elo in LEVELS:
        a = np.array([d for d, _ in gold_pairs[elo]])
        g = np.array([p for _, p in gold_pairs[elo]])
        ra, rg = np.argsort(np.argsort(a)), np.argsort(np.argsort(g))
        print(f"spearman(danger_{elo}, objective punish) = "
              f"{float(np.corrcoef(ra, rg)[0, 1]):.3f}")

    print(f"\nobjective x personal (@1300), counts:")
    obj_order = ["DEAD", "QUIET", "DYNAMIC", "SHARP", "RAZOR"]
    print(f"{'':<9}" + "".join(f"{p:>10}" for p in ("SAFE", "SLIPPERY",
                                                    "TRAP")))
    for ob in obj_order:
        print(f"{ob:<9}" + "".join(
            f"{matrix[1300][(ob, pb)]:>10}"
            for pb in ("SAFE", "SLIPPERY", "TRAP")))

    print(f"\ncohort traps (objectively calm, TRAP@1300): "
          f"{len(cohort_traps)}")
    for t in cohort_traps[:6]:
        tm = t["trap_move"] or {}
        print(f"  [{t['objective']}] {t['fen']}")
        print(f"     danger {t['danger']} trap_mass {t['trap_mass']} — "
              f"{tm.get('san')} (p={tm.get('policy')}, "
              f"loses {tm.get('loss')}cp)")

    json.dump({"results": results, "cohort_traps": cohort_traps},
              open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
