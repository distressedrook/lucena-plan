#!/usr/bin/env python3
"""King-danger calibration — EXTERNAL validation against real 1500-rated
human games (Lichess open database, 2013-01, 121,331 games; 29,168 have a
player rated 1450-1550 at >=3min time control).

This is the leg the whole study line has been missing: v2's calibration
(calibrate_v2.py) used a MAIA-SIMULATED defender, which is itself only a
model of a 1500 player. This script uses ACTUAL recorded human moves —
no policy model in the loop at all.

Method (identical design to calibrate_v2.py for direct comparability):
  - walk each qualifying game; at every ply where the ~1500-rated player
    is to move, compute their king's raw danger score (pure geometry)
  - stratified-sample across danger bins (oversample the dangerous end)
  - label CATASTROPHE if, within the next HORIZON plies of the GAME'S
    ACTUAL CONTINUATION (real moves both sides played), that king is
    checkmated, or the at-risk side's eval (engine, at the walked
    endpoint or game end) is <= CRASH_CP
  - exclude starts already worse than START_FLOOR_CP (isolate a
    danger-driven collapse from an already-lost position)
  - fit isotonic; compare its reliability curve to the v2 (simulated)
    table — agreement is the actual validation result.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

ROOT = "/Users/avismara/Development/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")

import chess
import chess.engine
import chess.pgn
import numpy as np
from sklearn.isotonic import IsotonicRegression
from scipy.stats import spearmanr, pointbiserialr

from lucena_core.board import Board
from lucena_core.positional import analyze_positional, DANGER_MAX

HERE = os.path.dirname(os.path.abspath(__file__))
PGN = os.path.join(HERE, "lichess_2013-01.pgn")
OUT_REPORT = os.path.join(HERE, "real_games_matched_report.json")
OUT_TABLE = os.path.join(HERE, "real_games_matched_table.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"

ELO_LO, ELO_HI = 1450, 1550
MIN_TC_SEC = 180
HORIZON = 16
CRASH_CP = -700
START_FLOOR_CP = -250
NODES = 80_000
PER_BIN = 70
MAX_PER_GAME = 2          # independence: don't over-draw one game
MAX_GAMES_SCAN = 130_000  # covers the whole 2013-01 file (121,331 games);
                          # the strict both-sides-in-band filter (4,864/
                          # 121,331 games) needs the full month to fill bins
BINS = [(0, 40), (40, 100), (100, 200), (200, 350), (350, DANGER_MAX + 1)]


def king_danger(board_fen: str, color: str):
    try:
        terms = analyze_positional(Board(board_fen))["terms"]
    except ValueError:
        return None
    ks = terms["king_safety"]["features"]
    return ks.get(color, {}).get("danger")


def qualifies(headers) -> bool:
    """BOTH sides must be 1450-1550 (2026-07-24, owner correction): the
    first pass let the opponent be any rating at all, so a 1500 crushed
    by a 2200 or coasting past a 1100 both counted as "1500 experience"
    and diluted the real signal — "of course it will be less [dangerous]
    if the actual opponent isn't even 1500". Requiring both sides in-band
    answers the real question, what typically happens between two ~1500s.
    Symmetric, so BOTH colors are valid at-risk subjects in these games —
    the harvester samples either side's king, doubling density per game."""
    try:
        we, be = int(headers.get("WhiteElo", 0)), int(headers.get("BlackElo", 0))
    except ValueError:
        return False
    tc = headers.get("TimeControl", "-")
    m = re.match(r"(\d+)", tc)
    if not m or int(m.group(1)) < MIN_TC_SEC:
        return False
    if headers.get("Termination", "") == "Time forfeit":
        return False
    return ELO_LO <= we <= ELO_HI and ELO_LO <= be <= ELO_HI


def harvest_candidates():
    """Yield (fen, color, danger) for the at-risk player's positions,
    stratified into bins as we go, capped per game."""
    by_bin = defaultdict(list)
    games_scanned = 0
    with open(PGN, errors="replace") as f:
        while games_scanned < MAX_GAMES_SCAN:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            games_scanned += 1
            if not qualifies(game.headers):
                continue
            board = game.board()
            node = game
            positions = []
            while node.variations:
                nxt = node.variations[0]
                if board.fullmove_number >= 6:
                    # both sides qualify symmetrically now: sample
                    # whichever side is about to move
                    color = "white" if board.turn == chess.WHITE else "black"
                    d = king_danger(board.fen(), color)
                    if d is not None:
                        positions.append((board.fen(), color, d, node))
                board = nxt.board()
                node = nxt
            if not positions:
                continue
            # prefer higher-danger positions from this game (oversampling
            # need), but cap how many we take from one game
            positions.sort(key=lambda t: -t[2])
            for fen, color, d, node in positions[:MAX_PER_GAME]:
                for lo, hi in BINS:
                    if lo <= d < hi and len(by_bin[(lo, hi)]) < PER_BIN:
                        by_bin[(lo, hi)].append((fen, color, d, node, game))
            if all(len(by_bin.get(b, [])) >= PER_BIN for b in BINS):
                break
    print(f"scanned {games_scanned} games; "
          f"{ {f'{lo}-{hi}': len(by_bin.get((lo, hi), [])) for lo, hi in BINS} }")
    out = []
    for v in by_bin.values():
        out += v
    return out


def label_from_real_continuation(engine, fen, color, node):
    """Walk the GAME's actual future moves (real human/opponent play) up
    to HORIZON plies; label catastrophe by checkmate or eval crash."""
    risk_white = color == "white"
    board = chess.Board(fen)
    info = engine.analyse(board, chess.engine.Limit(nodes=NODES))
    start_cp = info["score"].white().score(mate_score=10_000)
    start_risk = start_cp if risk_white else -start_cp
    if start_risk < START_FLOOR_CP:
        return 0, "already_lost_excluded"

    cur = node
    plies = 0
    while cur.variations and plies < HORIZON:
        cur = cur.variations[0]
        plies += 1
        b = cur.board()
        if b.is_checkmate():
            mated_white = b.turn == chess.WHITE
            if mated_white == risk_white:
                return 1, f"mate_ply{plies}"
            return 0, "opponent_mated"
    end_board = cur.board()
    if end_board.is_game_over() and not end_board.is_checkmate():
        return 0, "game_ended_non_mate"
    end_info = engine.analyse(end_board, chess.engine.Limit(nodes=NODES))
    end_cp = end_info["score"].white().score(mate_score=10_000)
    end_risk = end_cp if risk_white else -end_cp
    if end_risk <= CRASH_CP:
        return 1, "eval_crash"
    return 0, "held"


def main():
    sample = harvest_candidates()
    print(f"sample size {len(sample)}")

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": 6, "Hash": 1024})
    rows = []
    try:
        for i, (fen, color, d, node, game) in enumerate(sample):
            lbl, reason = label_from_real_continuation(engine, fen, color, node)
            rows.append({"fen": fen, "color": color, "danger": d,
                        "label": lbl, "reason": reason,
                        "white": game.headers.get("White"),
                        "black": game.headers.get("Black")})
            if (i + 1) % 40 == 0:
                print(f"  {i + 1}/{len(sample)}  "
                     f"(pos so far: {sum(r['label'] for r in rows)})")
    finally:
        engine.quit()

    excluded = [r for r in rows if r["reason"] == "already_lost_excluded"]
    used = [r for r in rows if r["reason"] != "already_lost_excluded"]
    print(f"excluded {len(excluded)}; fit on {len(used)}")

    X = np.array([r["danger"] for r in used], dtype=float)
    y = np.array([r["label"] for r in used], dtype=float)
    print(f"positive rate {y.mean():.1%} (n_pos={int(y.sum())})")

    result = {"n": len(used), "n_excluded": len(excluded),
             "positive_rate": round(float(y.mean()), 4), "rows": rows}

    if 0 < y.sum() < len(y):
        iso = IsotonicRegression(y_min=0.0, y_max=1.0,
                                 out_of_bounds="clip").fit(X, y)
        grid = np.arange(0, DANGER_MAX + 1, 2)
        table = {int(g): round(float(iso.predict([g])[0]), 4) for g in grid}
        brier = float(np.mean((iso.predict(X) - y) ** 2))
        baseline = float(np.mean((y.mean() - y) ** 2))
        sp = float(spearmanr(X, y).statistic)
        pb = float(pointbiserialr(y, X).statistic)
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
              f"spearman {sp:.3f}  point-biserial {pb:.3f}")

        # compare vs the SIMULATED (v2) table
        v2_path = os.path.join(HERE, "calib_v2_table.json")
        agree = None
        if os.path.exists(v2_path):
            v2 = json.load(open(v2_path))
            v2f = {int(k): v for k, v in v2.items()}
            diffs = [abs(table[g] - v2f.get(g, table[g])) for g in table
                    if g in v2f]
            agree = round(float(np.mean(diffs)), 4)
            print(f"mean |real_pred - simulated_pred| across the grid: "
                 f"{agree}")

        result.update({"reliability": reliability, "brier": round(brier, 4),
                       "baseline_brier": round(baseline, 4),
                       "spearman": round(sp, 3), "point_biserial": round(pb, 3),
                       "vs_simulated_mean_abs_diff": agree, "status": "fit"})
        json.dump(table, open(OUT_TABLE, "w"), indent=0)
    else:
        print("DEGENERATE — no variance in labels")
        result["status"] = "degenerate"

    json.dump(result, open(OUT_REPORT, "w"), indent=1)
    print(f"\nwrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
