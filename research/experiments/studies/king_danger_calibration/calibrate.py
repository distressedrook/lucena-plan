#!/usr/bin/env python3
"""King-danger calibration: raw danger score -> P(catastrophe).

"0 = safe, 1 = checkmated" is a claim about a PROBABILITY, which the raw
composite score (SAFETY_TABLE + shield/file/center penalties) does not
carry on its own — it's a hand-authored formula with no outcome behind
it. This fits one.

Label (per at-risk king, engine-verified, no human game data needed):
CATASTROPHE if the engine's own best line (single PV, deep search) either
  (a) checkmates that king within HORIZON plies, or
  (b) leaves that side's eval below CRASH_CP by the horizon's end,
      starting from no worse than START_FLOOR_CP (isolates a COLLAPSE
      driven by the position, not an already-lost position restating
      the obvious).

Sampling is STRATIFIED across the raw danger range (5 bins) and
OVERSAMPLED at the high end, because forced mates within a bounded
horizon are rare — a uniform sample would starve the calibration curve
of positive examples exactly where they matter most.

Fits isotonic regression (monotone, exactly the right shape for "more
danger -> more probability, never less") and reports the reliability
curve + Brier score. Output: calib_report.json + calib_table.json (the
raw_danger -> P(catastrophe) lookup the product will actually use).
"""
from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict

ROOT = "/Users/avismara/Development/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")

import chess
import chess.engine
import numpy as np
from sklearn.isotonic import IsotonicRegression

from lucena_core.board import Board
from lucena_core.positional import analyze_positional, DANGER_MAX

BENCH = f"{ROOT}/lucena-plans/research/gpu_benchmark/benchmark_v1.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_REPORT = os.path.join(HERE, "calib_report.json")
OUT_TABLE = os.path.join(HERE, "calib_table.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"

HORIZON = 24            # plies of the engine's own best line to walk
CRASH_CP = -700          # at-risk side's POV, "practically lost"
START_FLOOR_CP = -200    # exclude positions already lost for other reasons
NODES = 400_000
PER_BIN = 90
BINS = [(0, 40), (40, 100), (100, 200), (200, 350), (350, DANGER_MAX + 1)]


def king_dangers(fen: str):
    try:
        terms = analyze_positional(Board(fen))["terms"]
    except ValueError:
        return None
    ks = terms["king_safety"]["features"]
    return {c: ks[c]["danger"] for c in ("white", "black") if c in ks}


def sample_positions(rng):
    fens = [json.loads(l)["fen"] for l in open(BENCH)]
    rng.shuffle(fens)
    by_bin = defaultdict(list)
    for fen in fens:
        dd = king_dangers(fen)
        if dd is None:
            continue
        for color, d in dd.items():
            for lo, hi in BINS:
                if lo <= d < hi and len(by_bin[(lo, hi)]) < PER_BIN:
                    by_bin[(lo, hi)].append((fen, color, d))
        if all(len(v) >= PER_BIN for v in by_bin.values()) and \
                len(by_bin) == len(BINS):
            break
    out = []
    for v in by_bin.values():
        out += v
    print({f"{lo}-{hi}": len(by_bin.get((lo, hi), []))
          for lo, hi in BINS})
    return out


def catastrophe(engine, fen: str, at_risk: str) -> tuple[int, str]:
    """(label, reason) for the at_risk color from THIS position."""
    b = chess.Board(fen)
    risk_is_white = at_risk == "white"
    info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
    start_cp = info["score"].white().score(mate_score=10_000)
    start_cp_risk = start_cp if risk_is_white else -start_cp
    if start_cp_risk < START_FLOOR_CP:
        return 0, "already_lost_excluded"
    pv = info.get("pv") or []
    bb = b.copy(stack=False)
    for i, mv in enumerate(pv[:HORIZON]):
        if mv not in bb.legal_moves:
            break
        bb.push(mv)
        if bb.is_checkmate():
            mated_white = bb.turn == chess.WHITE   # side to move IS mated
            if mated_white == risk_is_white:
                return 1, f"mate_in_pv_ply{i+1}"
            break                                   # the OTHER king got mated
    if len(pv) >= 2:
        end_info = engine.analyse(bb, chess.engine.Limit(nodes=NODES))
        end_cp = end_info["score"].white().score(mate_score=10_000)
        end_cp_risk = end_cp if risk_is_white else -end_cp
        if end_cp_risk <= CRASH_CP:
            return 1, "eval_crash"
    return 0, "held"


def main():
    rng = random.Random(17)
    sample = sample_positions(rng)
    print(f"sample size {len(sample)}")

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": 6, "Hash": 1024})
    rows = []
    try:
        for i, (fen, color, d) in enumerate(sample):
            lbl, reason = catastrophe(engine, fen, color)
            rows.append({"fen": fen, "color": color, "danger": d,
                         "label": lbl, "reason": reason})
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(sample)}")
    finally:
        engine.quit()

    excluded = [r for r in rows if r["reason"] == "already_lost_excluded"]
    used = [r for r in rows if r["reason"] != "already_lost_excluded"]
    print(f"excluded (already lost) {len(excluded)}; fit on {len(used)}")

    X = np.array([r["danger"] for r in used], dtype=float)
    y = np.array([r["label"] for r in used], dtype=float)
    print(f"positive rate: {y.mean():.1%}  (n_pos={int(y.sum())})")

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(X, y)

    grid = np.arange(0, DANGER_MAX + 1, 2)
    table = {int(g): round(float(iso.predict([g])[0]), 4) for g in grid}

    # 5-fold-ish reliability check by bin
    print(f"\n{'bin':<12}{'n':>5}{'mean_danger':>13}{'obs_rate':>10}"
          f"{'iso_pred':>10}")
    reliability = []
    for lo, hi in BINS:
        rs = [(d, l) for d, l in zip(X, y) if lo <= d < hi]
        if not rs:
            continue
        ds = [d for d, _ in rs]
        obs = sum(l for _, l in rs) / len(rs)
        pred = float(iso.predict([sum(ds) / len(ds)])[0])
        reliability.append({"bin": [lo, hi], "n": len(rs),
                            "mean_danger": round(sum(ds) / len(ds), 1),
                            "obs_rate": round(obs, 3),
                            "iso_pred": round(pred, 3)})
        print(f"{f'{lo}-{hi}':<12}{len(rs):>5}"
              f"{sum(ds) / len(ds):>13.1f}{obs:>10.3f}{pred:>10.3f}")

    brier = float(np.mean((iso.predict(X) - y) ** 2))
    baseline_brier = float(np.mean((y.mean() - y) ** 2))
    print(f"\nBrier: isotonic {brier:.4f}  vs base-rate baseline "
          f"{baseline_brier:.4f}  (lower is better; must beat baseline)")

    json.dump({"n": len(used), "n_excluded": len(excluded),
              "positive_rate": round(float(y.mean()), 4),
              "reliability": reliability, "brier": round(brier, 4),
              "baseline_brier": round(baseline_brier, 4),
              "rows": rows}, open(OUT_REPORT, "w"), indent=1)
    json.dump(table, open(OUT_TABLE, "w"), indent=0)
    print(f"\nwrote {OUT_REPORT}\nwrote {OUT_TABLE}")


if __name__ == "__main__":
    main()
