#!/usr/bin/env python3
"""King-danger calibration v2 — Maia-defended counterfactual.

v1 (calibrate.py) walked the ENGINE's own best line for both sides and
found zero catastrophes even at danger=239: the engine defends itself
perfectly by construction, so "danger" under perfect defense is nearly
always survivable. That measures the wrong thing for a coaching product
— we want P(catastrophe | a player of this level defends), not P(...|
engine defends).

v2: ATTACKER plays the engine's best move each ply (also gives the free
eval reading); DEFENDER (the at-risk side) plays Maia's top policy
choice at rating L. Positions are sourced from the residual-attribution
study's already-harvested interior dataset (77k positions along real
engine lines) so the dangerous end of the range has coverage — root-only
benchmark positions starved v1's high bins (only 2 above danger=200).
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
from lucena_engine.maia import MaiaEngine

DATASET = (f"{ROOT}/lucena-plans/research/experiments/studies/"
          "residual_attribution/dataset.jsonl")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_REPORT = os.path.join(HERE, "calib_v2_report.json")
OUT_TABLE = os.path.join(HERE, "calib_v2_table.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"
DEFENDER_ELO = 1500

HORIZON = 16              # plies of simulated play
CRASH_CP = -700
START_FLOOR_CP = -250
NODES = 80_000
PER_BIN = 70
BINS = [(0, 40), (40, 100), (100, 200), (200, 350), (350, DANGER_MAX + 1)]


def king_dangers(fen: str):
    try:
        terms = analyze_positional(Board(fen))["terms"]
    except ValueError:
        return None
    ks = terms["king_safety"]["features"]
    return {c: ks[c]["danger"] for c in ("white", "black") if c in ks}


def sample_positions(rng):
    fens = []
    with open(DATASET) as f:
        for line in f:
            fens.append(json.loads(line)["fen"])
    rng.shuffle(fens)
    seen = set()
    by_bin = defaultdict(list)
    for fen in fens:
        key = " ".join(fen.split()[:4])
        if key in seen:
            continue
        dd = king_dangers(fen)
        if dd is None:
            continue
        seen.add(key)
        for color, d in dd.items():
            for lo, hi in BINS:
                if lo <= d < hi and len(by_bin[(lo, hi)]) < PER_BIN:
                    by_bin[(lo, hi)].append((fen, color, d))
        if all(len(by_bin.get(b, [])) >= PER_BIN for b in BINS):
            break
    out = []
    for v in by_bin.values():
        out += v
    print({f"{lo}-{hi}": len(by_bin.get((lo, hi), [])) for lo, hi in BINS})
    return out


def simulate(engine, maia, fen: str, at_risk: str):
    """(label, reason). Attacker = engine bestmove; defender (at_risk) =
    Maia argmax @ DEFENDER_ELO."""
    b = chess.Board(fen)
    risk_white = at_risk == "white"

    def to_risk_pov(cp):
        return cp if risk_white else -cp

    for i in range(HORIZON):
        if b.is_game_over():
            break
        defender_to_move = (b.turn == chess.WHITE) == risk_white
        if defender_to_move:
            picks = maia.top_human_moves(b.fen(), DEFENDER_ELO, n=1)
            if not picks:
                return 0, "maia_no_moves"
            mv = chess.Move.from_uci(picks[0]["uci"])
            if mv not in b.legal_moves:
                return 0, "maia_illegal_skip"
            b.push(mv)
        else:
            info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
            cp = info["score"].white().score(mate_score=10_000)
            if i == 0 and to_risk_pov(cp) < START_FLOOR_CP:
                return 0, "already_lost_excluded"
            mv = info.get("pv", [None])[0]
            if mv is None or mv not in b.legal_moves:
                return 0, "no_move"
            b.push(mv)
            if b.is_checkmate():
                mated_white = b.turn == chess.WHITE
                if mated_white == risk_white:
                    return 1, f"mate_ply{i+1}"
                break
            if to_risk_pov(cp) <= CRASH_CP:
                return 1, f"crash_ply{i+1}"
    return 0, "held"


def main():
    rng = random.Random(23)
    sample = sample_positions(rng)
    print(f"sample size {len(sample)}")

    os.environ.setdefault(
        "LUCENA_MAIA",
        f"{ROOT}/.venv-maia/bin/python {ROOT}/engine/scripts/"
        "maia_policy_uci.py")
    maia = MaiaEngine()
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": 4, "Hash": 512})
    rows = []
    try:
        for i, (fen, color, d) in enumerate(sample):
            lbl, reason = simulate(engine, maia, fen, color)
            rows.append({"fen": fen, "color": color, "danger": d,
                         "label": lbl, "reason": reason})
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(sample)}  "
                      f"(pos so far: {sum(r['label'] for r in rows)})")
    finally:
        maia.close()
        engine.quit()

    excluded = [r for r in rows if r["reason"] == "already_lost_excluded"]
    used = [r for r in rows if r["reason"] != "already_lost_excluded"]
    print(f"excluded (already lost) {len(excluded)}; fit on {len(used)}")

    X = np.array([r["danger"] for r in used], dtype=float)
    y = np.array([r["label"] for r in used], dtype=float)
    print(f"positive rate: {y.mean():.1%}  (n_pos={int(y.sum())})")

    if y.sum() == 0 or y.sum() == len(y):
        print("DEGENERATE: no variance in labels — calibration cannot "
              "be fit. Stopping without writing a table.")
        json.dump({"n": len(used), "n_excluded": len(excluded),
                  "positive_rate": round(float(y.mean()), 4),
                  "rows": rows, "status": "degenerate"},
                  open(OUT_REPORT, "w"), indent=1)
        return

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(X, y)

    grid = np.arange(0, DANGER_MAX + 1, 2)
    table = {int(g): round(float(iso.predict([g])[0]), 4) for g in grid}

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
          f"{baseline_brier:.4f}  (must beat baseline)")

    from scipy.stats import spearmanr

    def spearman(a, b_):
        # scipy tie-corrects ranks; a naive double-argsort mis-ranks a
        # binary target this tied and leaks the array's build order
        # (rows are appended bin-by-bin, i.e. sorted by danger) into the
        # tie-break — caught 2026-07-24, silently gave -0.098 for what is
        # actually a positive, significant relationship.
        return float(spearmanr(a, b_).statistic)

    print(f"spearman(danger, label) = {spearman(X, y):.3f}")

    json.dump({"n": len(used), "n_excluded": len(excluded),
              "positive_rate": round(float(y.mean()), 4),
              "reliability": reliability, "brier": round(brier, 4),
              "baseline_brier": round(baseline_brier, 4),
              "spearman": round(spearman(X, y), 3),
              "rows": rows, "status": "fit"},
              open(OUT_REPORT, "w"), indent=1)
    json.dump(table, open(OUT_TABLE, "w"), indent=0)
    print(f"\nwrote {OUT_REPORT}\nwrote {OUT_TABLE}")


if __name__ == "__main__":
    main()
