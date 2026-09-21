#!/usr/bin/env python3
"""validate_gm_games, parallelized + hardened.

Fixes over validate_gm_games.py (which crashed 17min into harvest on a
corrupt game — an illegal SAN in the corpus — and was too slow anyway):
  - each game is parsed from its OWN isolated text block (regex-split on
    "[Event "), so one corrupt game can't desync or crash the run — it's
    just skipped
  - harvest calls the king-safety term directly instead of the full
    5-term analyze_positional (material/activity/pawns/center are
    computed and thrown away every position in the original — ~5x waste)
  - harvest is chunked across a multiprocessing Pool
  - engine labeling is parallelized across N single-threaded Stockfish
    workers instead of one 6-threaded engine processing serially — our
    workload is many small independent searches, which parallelizes
    ~linearly across processes, unlike within-search threading at 80k
    nodes
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import re
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
N_WORKERS = 8
BINS = [(0, 40), (40, 100), (100, 200), (200, 350), (350, 773)]


def _king_danger_only(fen: str, color: str):
    """King-safety-term-only computation — avoids analyze_positional's
    material/activity/pawns/center work, which harvest never uses."""
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
    return ks.get(color, {}).get("danger")


def _split_games(path: str) -> list[str]:
    """Isolate each game's text so a corrupt one can't crash a neighbor."""
    text = open(path, errors="replace").read()
    starts = [m.start() for m in re.finditer(r"^\[Event ", text, re.M)]
    starts.append(len(text))
    return [text[starts[i]:starts[i + 1]] for i in range(len(starts) - 1)]


def _qualifies(headers) -> bool:
    try:
        we, be = int(headers.get("WhiteElo", 0)), int(headers.get("BlackElo", 0))
    except ValueError:
        return False
    return we >= 2400 and be >= 2400


def _harvest_chunk(blocks: list[str]):
    """Worker: parse an isolated slice of game-text blocks, return
    candidate (fen, color, danger, san_line, headers) tuples per bin."""
    import io
    by_bin = defaultdict(list)
    for block in blocks:
        try:
            game = chess.pgn.read_game(io.StringIO(block))
        except Exception:
            continue
        if game is None or not _qualifies(game.headers):
            continue
        try:
            board = game.board()
            node = game
            positions = []
            sans = []
            while node.variations:
                nxt = node.variations[0]
                mv = nxt.move
                sans.append(board.san(mv))
                if board.fullmove_number >= 6:
                    color = "white" if board.turn == chess.WHITE else "black"
                    d = _king_danger_only(board.fen(), color)
                    if d is not None:
                        positions.append((board.fen(), color, d, len(sans) - 1))
                board = nxt.board()
                node = nxt
        except Exception:
            continue          # any mid-game corruption: skip this game
        if not positions:
            continue
        positions.sort(key=lambda t: -t[2])
        for fen, color, d, ply_idx in positions[:MAX_PER_GAME]:
            for lo, hi in BINS:
                if lo <= d < hi and len(by_bin[(lo, hi)]) < PER_BIN:
                    by_bin[(lo, hi)].append({
                        "fen": fen, "color": color, "danger": d,
                        "ply_idx": ply_idx, "sans": sans,
                        "white": game.headers.get("White"),
                        "black": game.headers.get("Black")})
    return dict(by_bin)


def harvest_candidates():
    blocks = _split_games(PGN)
    print(f"split into {len(blocks)} game blocks")
    chunk = max(1, len(blocks) // (N_WORKERS * 4))
    chunks = [blocks[i:i + chunk] for i in range(0, len(blocks), chunk)]
    merged = defaultdict(list)
    with mp.Pool(N_WORKERS) as pool:
        for partial in pool.imap_unordered(_harvest_chunk, chunks):
            for k, v in partial.items():
                room = PER_BIN - len(merged[k])
                if room > 0:
                    merged[k].extend(v[:room])
            if all(len(merged.get(b, [])) >= PER_BIN for b in BINS):
                pool.terminate()
                break
    print({f"{lo}-{hi}": len(merged.get((lo, hi), [])) for lo, hi in BINS})
    out = []
    for v in merged.values():
        out += v
    return out


def _label_one(row):
    """Worker: own single-threaded engine per call is wasteful (startup
    cost) — instead workers keep a persistent engine via initializer."""
    global _ENGINE
    engine = _ENGINE
    risk_white = row["color"] == "white"
    board = chess.Board(row["fen"])
    info = engine.analyse(board, chess.engine.Limit(nodes=NODES))
    start_cp = info["score"].white().score(mate_score=10_000)
    start_risk = start_cp if risk_white else -start_cp
    if start_risk < START_FLOOR_CP:
        return {**row, "label": 0, "reason": "already_lost_excluded"}

    sans = row["sans"]
    plies = 0
    # ply_idx = index of the move ABOUT TO BE PLAYED from the captured
    # FEN (captured pre-move, see _harvest_chunk) — the slice must
    # include it, not start one ply late.
    for san in sans[row["ply_idx"]: row["ply_idx"] + HORIZON]:
        try:
            mv = board.parse_san(san)
        except Exception:
            break
        board.push(mv)
        plies += 1
        if board.is_checkmate():
            mated_white = board.turn == chess.WHITE
            if mated_white == risk_white:
                return {**row, "label": 1, "reason": f"mate_ply{plies}"}
            return {**row, "label": 0, "reason": "opponent_mated"}
    if board.is_game_over() and not board.is_checkmate():
        return {**row, "label": 0, "reason": "game_ended_non_mate"}
    end_info = engine.analyse(board, chess.engine.Limit(nodes=NODES))
    end_cp = end_info["score"].white().score(mate_score=10_000)
    end_risk = end_cp if risk_white else -end_cp
    if end_risk <= CRASH_CP:
        return {**row, "label": 1, "reason": "eval_crash"}
    return {**row, "label": 0, "reason": "held"}


def _init_engine():
    global _ENGINE
    _ENGINE = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    _ENGINE.configure({"Threads": 1, "Hash": 128})


LABEL_TIMEOUT_SEC = 45   # a per-position watchdog: some corpus positions
                        # hung a bare engine.analyse() call indefinitely
                        # during this study (2026-07-24) — cause not
                        # isolated (works instantly in a 50-game replay),
                        # so bound it structurally instead of chasing it.
                        # A stuck worker just drops out of the pool; the
                        # rest keep going.


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
            r.pop("sans", None)
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

    excluded_reasons = {"already_lost_excluded", "timeout_skipped"}
    excluded = [r for r in rows if r["reason"] in excluded_reasons]
    used = [r for r in rows if r["reason"] not in excluded_reasons]
    n_timeout = sum(1 for r in rows if r["reason"] == "timeout_skipped")
    print(f"excluded {len(excluded)} ({n_timeout} timeouts); fit on {len(used)}")

    X = np.array([r["danger"] for r in used], dtype=float)
    y = np.array([r["label"] for r in used], dtype=float)
    print(f"positive rate {y.mean():.1%} (n_pos={int(y.sum())})")

    result = {"n": len(used), "n_excluded": len(excluded),
             "positive_rate": round(float(y.mean()), 4), "rows": rows}

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
        print("DEGENERATE")
        result["status"] = "degenerate"

    json.dump(result, open(OUT_REPORT, "w"), indent=1)
    print(f"\nwrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
