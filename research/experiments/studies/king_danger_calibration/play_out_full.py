#!/usr/bin/env python3
"""The definitive version of finding 23/24 (2026-07-24): finding 23 found
0/194 "catastrophes" under perfect play, isolated variable, material
clean — but finding 24 showed that's an artifact of a too-short horizon
(20 plies): a spot-checked position with a confirmed -2.9 engine eval
took 118 plies to actually convert to mate, and was still only -308cp at
ply 20. So "0/194" measured fast collapse, not eventual outcome.

This plays out ALL 194 positions from validate_clean_engine.py's sample
to ACTUAL CONCLUSION — checkmate, draw (stalemate/insufficient material/
50-move/repetition), or a generous 200-ply cap — no artificial crash
threshold, no short horizon. The real final score.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time

ROOT = "/Users/avismara/Development/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")

import chess
import chess.engine

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "clean_engine_report.json")
OUT = os.path.join(HERE, "play_out_full_report.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"

NODES = 100_000
MAX_PLIES = 200
N_WORKERS = 9              # leave one core for orchestration
TASK_TIMEOUT_SEC = 240      # generous: a full 200-ply game at ~0.3-0.5s/
                          # move can take ~60-100s; give real headroom


def _play_out(row):
    global _ENGINE
    engine = _ENGINE
    risk_white = row["color"] == "white"
    b = chess.Board(row["fen"])
    plies = 0
    while not b.is_game_over() and plies < MAX_PLIES:
        info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
        mv = info.get("pv", [None])[0]
        if mv is None or mv not in b.legal_moves:
            break
        b.push(mv)
        plies += 1

    outcome = b.outcome(claim_draw=True)
    final_info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
    final_cp = final_info["score"].white().score(mate_score=100_000)
    final_risk = final_cp if risk_white else -final_cp

    if outcome is None:
        result = "undecided_at_cap"
    elif outcome.winner is None:
        result = "draw"
    else:
        mated_white = outcome.winner  # winner=True means White won
        # winner is the side that WON; the at-risk side lost iff winner
        # is the opposite color from risk
        risk_lost = (outcome.winner == (not risk_white))
        result = "at_risk_lost" if risk_lost else "at_risk_won"

    return {**row, "plies_played": plies, "final_cp_risk_pov": final_risk,
           "termination": str(outcome.termination) if outcome else None,
           "result": result}


def _init_engine():
    global _ENGINE
    _ENGINE = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    _ENGINE.configure({"Threads": 1, "Hash": 128})


def main():
    rows = json.load(open(SOURCE))["rows"]
    print(f"playing out {len(rows)} positions, {N_WORKERS} workers, "
         f"cap {MAX_PLIES} plies, {NODES} nodes/move", flush=True)
    t0 = time.time()

    results = []
    with mp.Pool(N_WORKERS, initializer=_init_engine) as pool:
        pending = [(row, pool.apply_async(_play_out, (row,)))
                  for row in rows]
        for i, (row, ar) in enumerate(pending):
            try:
                r = ar.get(timeout=TASK_TIMEOUT_SEC)
            except mp.TimeoutError:
                r = {**row, "plies_played": None, "final_cp_risk_pov": None,
                    "termination": None, "result": "timeout_skipped"}
            results.append(r)
            if (i + 1) % 20 == 0:
                elapsed = time.time() - t0
                lost = sum(1 for x in results if x["result"] == "at_risk_lost")
                print(f"  {i + 1}/{len(rows)}  lost={lost}  "
                     f"elapsed={elapsed:.0f}s", flush=True)

    elapsed = time.time() - t0
    print(f"\ndone in {elapsed:.0f}s")

    from collections import Counter, defaultdict
    tally = Counter(r["result"] for r in results)
    print(f"\nFINAL SCORE (n={len(results)}): {dict(tally)}")

    bins = [(0, 40), (40, 100), (100, 200), (200, 350), (350, 773)]
    by_bin = defaultdict(list)
    for r in results:
        for lo, hi in bins:
            if lo <= r["danger"] < hi:
                by_bin[(lo, hi)].append(r)
    print(f"\n{'bin':<12}{'n':>5}{'lost':>7}{'drew':>7}{'held':>7}"
         f"{'undecided':>11}{'mean_plies':>12}")
    reliability = []
    for lo, hi in bins:
        rs = by_bin.get((lo, hi), [])
        if not rs:
            continue
        lost = sum(1 for r in rs if r["result"] == "at_risk_lost")
        drew = sum(1 for r in rs if r["result"] == "draw")
        held = sum(1 for r in rs if r["result"] == "at_risk_won")
        undecided = sum(1 for r in rs if r["result"] == "undecided_at_cap")
        plies = [r["plies_played"] for r in rs if r["plies_played"]]
        mean_plies = sum(plies) / len(plies) if plies else 0
        print(f"{f'{lo}-{hi}':<12}{len(rs):>5}{lost:>7}{drew:>7}{held:>7}"
             f"{undecided:>11}{mean_plies:>12.1f}")
        reliability.append({"bin": [lo, hi], "n": len(rs), "lost": lost,
                            "drew": drew, "held": held,
                            "undecided": undecided,
                            "loss_rate": round(lost / len(rs), 3),
                            "mean_plies": round(mean_plies, 1)})

    json.dump({"n": len(results), "tally": dict(tally),
              "reliability": reliability, "elapsed_sec": round(elapsed, 1),
              "results": results}, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
