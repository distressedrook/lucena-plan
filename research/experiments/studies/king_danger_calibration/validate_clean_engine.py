#!/usr/bin/env python3
"""The clean controlled experiment (2026-07-24, owner request): "Stockfish
vs Stockfish is what we should look at. If the king's position is so bad,
it should checkmate itself. But the starting position must not have any
other issues — just a weak king."

v1 (calibrate.py) already tried engine-vs-engine and found ~0 catastrophes
— but it was NOT a clean test of this claim: it never isolated "nothing
else wrong" (material could be imbalanced, the ATTACKER's own king could
also be weak), and it was badly starved on genuinely dangerous positions
(only 2/300 above danger=200, since it sampled benchmark ROOTS only).

This version:
  - sources from the residual-attribution study's INTERIOR dataset (real
    danger variance lives a few moves into a line, not at GM-argmax
    roots) — no new harvesting needed, `adjusted_cp` is already computed
  - MATERIAL CLEAN: |adjusted_cp| <= MATERIAL_CLEAN_CP (near dead-even)
  - ATTACKER'S KING SAFE: the pressing side's own danger < ATTACKER_SAFE
    (so this isn't "both kings are a mess" — isolates the one variable)
  - both sides play the SAME engine's own best line (true self-play,
    both perfect by the engine's own lights)
  - HORIZON extended to 24 plies (v1/v2 used 16 for comparability across
    studies; here we specifically want to know whether perfect play CAN
    convert, so it gets more room to finish the job)
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
from collections import defaultdict

ROOT = "/Users/avismara/Projects/active/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")

import chess
import chess.engine
import numpy as np
from sklearn.isotonic import IsotonicRegression
from scipy.stats import spearmanr, pointbiserialr

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = (f"{ROOT}/lucena-plans/research/experiments/studies/"
          "residual_attribution/dataset.jsonl")
OUT_REPORT = os.path.join(HERE, "clean_engine_report.json")
OUT_TABLE = os.path.join(HERE, "clean_engine_table.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"

MATERIAL_CLEAN_CP = 30    # "no other issues" — near dead-even material
ATTACKER_SAFE_DANGER = 40  # the pressing side's OWN king must be safe
HORIZON = 20               # more room than v1/v2's 16 — does it convert
                          # AT ALL given room, not just quickly
                          # (owner: 20, not 24 — 2026-07-24)
CRASH_CP = -700
NODES = 150_000            # deeper than the human-facing studies: this
                          # IS the perfect-play claim, so search harder
PER_BIN = 60
N_WORKERS = 8
LABEL_TIMEOUT_SEC = 60
BINS = [(0, 40), (40, 100), (100, 200), (200, 350), (350, 773)]


def _king_danger_only(fen: str, color: str):
    from lucena_core.board import Board
    from lucena_core.positional import _king_safety_term
    from lucena_core.reads import occupancy
    try:
        b = Board(fen)
    except ValueError:
        return None
    occ = occupancy(b)
    phase_inc = {"N": 1, "B": 1, "R": 2, "Q": 4}
    gp = sum(phase_inc.get(p.piece, 0) for p in occ.values())
    ph = min(gp, 24) / 24.0
    ks = _king_safety_term(b, occ, ph)["features"]
    return ks


def harvest_candidates():
    by_bin = defaultdict(list)
    seen = set()
    n_checked = 0
    with open(DATASET) as f:
        for line in f:
            row = json.loads(line)
            fen = row["fen"]
            key = " ".join(fen.split()[:4])
            if key in seen:
                continue
            if abs(row.get("adjusted_cp", 9999)) > MATERIAL_CLEAN_CP:
                continue
            ks = _king_danger_only(fen, "white")
            if ks is None:
                continue
            n_checked += 1
            for at_risk, attacker in (("white", "black"), ("black", "white")):
                d = ks.get(at_risk, {}).get("danger")
                a_d = ks.get(attacker, {}).get("danger")
                if d is None or a_d is None or a_d >= ATTACKER_SAFE_DANGER:
                    continue
                for lo, hi in BINS:
                    if lo <= d < hi and len(by_bin[(lo, hi)]) < PER_BIN:
                        by_bin[(lo, hi)].append({"fen": fen, "color": at_risk,
                                                 "danger": d})
                        seen.add(key)
            if all(len(by_bin.get(b, [])) >= PER_BIN for b in BINS):
                break
    print(f"checked {n_checked} material-clean positions; "
          f"{ {f'{lo}-{hi}': len(by_bin.get((lo, hi), [])) for lo, hi in BINS} }")
    out = []
    for v in by_bin.values():
        out += v
    return out


def _label_one(row):
    global _ENGINE
    engine = _ENGINE
    risk_white = row["color"] == "white"
    b = chess.Board(row["fen"])
    plies = 0
    while plies < HORIZON and not b.is_game_over():
        info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
        mv = info.get("pv", [None])[0]
        if mv is None or mv not in b.legal_moves:
            break
        b.push(mv)
        plies += 1
        if b.is_checkmate():
            mated_white = b.turn == chess.WHITE
            if mated_white == risk_white:
                return {**row, "label": 1, "reason": f"mate_ply{plies}"}
            return {**row, "label": 0, "reason": "opponent_mated"}
    if b.is_game_over() and not b.is_checkmate():
        return {**row, "label": 0, "reason": "game_ended_non_mate"}
    end_info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
    end_cp = end_info["score"].white().score(mate_score=10_000)
    end_risk = end_cp if risk_white else -end_cp
    if end_risk <= CRASH_CP:
        return {**row, "label": 1, "reason": "eval_crash"}
    return {**row, "label": 0, "reason": "held"}


def _init_engine():
    global _ENGINE
    _ENGINE = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    _ENGINE.configure({"Threads": 1, "Hash": 128})


def label_all(sample):
    rows = []
    with mp.Pool(N_WORKERS, initializer=_init_engine) as pool:
        pending = [(row, pool.apply_async(_label_one, (row,)))
                  for row in sample]
        for i, (row, ar) in enumerate(pending):
            try:
                r = ar.get(timeout=LABEL_TIMEOUT_SEC)
            except mp.TimeoutError:
                r = {**row, "label": 0, "reason": "timeout_skipped"}
            rows.append(r)
            if (i + 1) % 40 == 0:
                print(f"  {i + 1}/{len(sample)}  "
                     f"(pos so far: {sum(x['label'] for x in rows)})",
                     flush=True)
    return rows


def main():
    sample = harvest_candidates()
    print(f"sample size {len(sample)}")
    rows = label_all(sample)

    excluded_reasons = {"timeout_skipped"}
    used = [r for r in rows if r["reason"] not in excluded_reasons]
    print(f"excluded {len(rows) - len(used)}; fit on {len(used)}")

    X = np.array([r["danger"] for r in used], dtype=float)
    y = np.array([r["label"] for r in used], dtype=float)
    print(f"positive rate {y.mean():.1%} (n_pos={int(y.sum())})")

    result = {"n": len(used), "positive_rate": round(float(y.mean()), 4),
             "rows": rows}

    if 0 < y.sum() < len(y):
        iso = IsotonicRegression(y_min=0.0, y_max=1.0,
                                 out_of_bounds="clip").fit(X, y)
        grid = np.arange(0, 773, 2)
        table = {int(g): round(float(iso.predict([g])[0]), 4) for g in grid}
        brier = float(np.mean((iso.predict(X) - y) ** 2))
        baseline = float(np.mean((y.mean() - y) ** 2))
        sp, sp_p = spearmanr(X, y)
        pb, pb_p = pointbiserialr(y, X)
        print(f"\n{'bin':<12}{'n':>5}{'mean_d':>10}{'obs':>8}{'iso':>8}")
        reliability = []
        for lo, hi in BINS:
            rs = [(dd, ll) for dd, ll in zip(X, y) if lo <= dd < hi]
            if not rs:
                continue
            ds = [dd for dd, _ in rs]
            obs = sum(ll for _, ll in rs) / len(rs)
            pred = float(iso.predict([sum(ds) / len(ds)])[0])
            reliability.append({"bin": [lo, hi], "n": len(rs),
                                "mean_danger": round(sum(ds) / len(ds), 1),
                                "obs_rate": round(obs, 3),
                                "iso_pred": round(pred, 3)})
            print(f"{f'{lo}-{hi}':<12}{len(rs):>5}"
                 f"{sum(ds) / len(ds):>10.1f}{obs:>8.3f}{pred:>8.3f}")
        print(f"\nBrier {brier:.4f} vs baseline {baseline:.4f}  "
              f"spearman {float(sp):.3f} (p={float(sp_p):.4f})  "
              f"point-biserial {float(pb):.3f} (p={float(pb_p):.4f})")
        result.update({"reliability": reliability, "brier": round(brier, 4),
                       "baseline_brier": round(baseline, 4),
                       "spearman": round(float(sp), 4),
                       "spearman_p": round(float(sp_p), 5),
                       "status": "fit"})
        json.dump(table, open(OUT_TABLE, "w"), indent=0)
    else:
        print("DEGENERATE — no variance in labels (confirms/refutes v1)")
        result["status"] = "degenerate"

    json.dump(result, open(OUT_REPORT, "w"), indent=1)
    print(f"\nwrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
