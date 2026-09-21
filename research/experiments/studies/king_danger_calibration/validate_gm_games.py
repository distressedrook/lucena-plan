#!/usr/bin/env python3
"""King-danger calibration — validation against GM-vs-GM classical games
(the project's banked corpus: research/data/gm_classical.pgn, 33,769
TWIC games, both players titled GM by construction — no filter needed).

Same pipeline as validate_real_games.py, for a clean three-way
comparison: simulated 1500-vs-engine (ceiling/worst-case), real
matched 1500-vs-1500 (typical amateur experience), and now GM-vs-GM
(does the danger score still predict anything once BOTH attacker and
defender are near-perfect? Or does GM defensive skill flatten it out?).
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

ROOT = "/Users/avismara/Projects/active/lucena"
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
PGN = f"{ROOT}/lucena-plans/research/data/gm_classical.pgn"
OUT_REPORT = os.path.join(HERE, "gm_games_report.json")
OUT_TABLE = os.path.join(HERE, "gm_games_table.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"

HORIZON = 16
CRASH_CP = -700
START_FLOOR_CP = -250
NODES = 80_000
PER_BIN = 70
MAX_PER_GAME = 2
MAX_GAMES_SCAN = 34_000
BINS = [(0, 40), (40, 100), (100, 200), (200, 350), (350, DANGER_MAX + 1)]


def king_danger(board_fen: str, color: str):
    try:
        terms = analyze_positional(Board(board_fen))["terms"]
    except ValueError:
        return None
    ks = terms["king_safety"]["features"]
    return ks.get(color, {}).get("danger")


def qualifies(headers) -> bool:
    """gm_classical.pgn is pre-filtered (both players titled GM) — light
    sanity check only, no TC/Termination fields in OTB PGN."""
    try:
        we, be = int(headers.get("WhiteElo", 0)), int(headers.get("BlackElo", 0))
    except ValueError:
        return False
    return we >= 2400 and be >= 2400


def harvest_candidates():
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
                    color = "white" if board.turn == chess.WHITE else "black"
                    d = king_danger(board.fen(), color)
                    if d is not None:
                        positions.append((board.fen(), color, d, node))
                board = nxt.board()
                node = nxt
            if not positions:
                continue
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

        for label, path in (("simulated (1500 vs engine)", "calib_v2_table.json"),
                            ("real matched (1500 vs 1500)",
                             "real_games_matched_table.json")):
            p = os.path.join(HERE, path)
            if os.path.exists(p):
                other = {int(k): v for k, v in json.load(open(p)).items()}
                diffs = [abs(table[g] - other.get(g, table[g])) for g in table
                        if g in other]
                print(f"mean |GM_pred - {label}|: "
                     f"{round(float(np.mean(diffs)), 4)}")

        result.update({"reliability": reliability, "brier": round(brier, 4),
                       "baseline_brier": round(baseline, 4),
                       "spearman": round(float(sp), 4),
                       "spearman_p": round(float(sp_p), 5),
                       "point_biserial": round(float(pb), 4),
                       "point_biserial_p": round(float(pb_p), 5),
                       "status": "fit"})
        json.dump(table, open(OUT_TABLE, "w"), indent=0)
    else:
        print("DEGENERATE — no variance in labels")
        result["status"] = "degenerate"

    json.dump(result, open(OUT_REPORT, "w"), indent=1)
    print(f"\nwrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
