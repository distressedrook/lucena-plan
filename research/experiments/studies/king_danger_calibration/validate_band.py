#!/usr/bin/env python3
"""validate_real_games, generalized to an arbitrary rating band + the
parallelized/hardened infra from validate_gm_games_fast.py (isolated
per-game parsing, multiprocessing harvest, watchdog-bounded labeling).

Usage: validate_band.py LO HI  (e.g. `validate_band.py 1300 1400`)

Reuses the already-downloaded lichess_2013-01.pgn — no new download per
band, it has games across the whole rating spectrum. Same design as
validate_real_games.py for direct comparability: both sides in [LO,HI],
>=3min time control, real continuations, 16-ply horizon, checkmate-or-
crash label, isotonic fit.
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
PGN = os.path.join(HERE, "lichess_2013-01.pgn")
STOCKFISH = "/opt/homebrew/bin/stockfish"

MIN_TC_SEC = 180
HORIZON = 16
CRASH_CP = -700
START_FLOOR_CP = -250
NODES = 80_000
PER_BIN = 50
MAX_PER_GAME = 2
N_WORKERS = 8
MAX_GAMES_SCAN = 130_000
LABEL_TIMEOUT_SEC = 45
BINS = [(0, 40), (40, 100), (100, 200), (200, 773)]


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
    return ks.get(color, {}).get("danger")


def _split_games(path: str) -> list[str]:
    text = open(path, errors="replace").read()
    starts = [m.start() for m in re.finditer(r"^\[Event ", text, re.M)]
    starts.append(len(text))
    return [text[starts[i]:starts[i + 1]] for i in range(len(starts) - 1)]


def _make_qualifies(lo, hi):
    def qualifies(headers) -> bool:
        try:
            we = int(headers.get("WhiteElo", 0))
            be = int(headers.get("BlackElo", 0))
        except ValueError:
            return False
        tc = headers.get("TimeControl", "-")
        m = re.match(r"(\d+)", tc)
        if not m or int(m.group(1)) < MIN_TC_SEC:
            return False
        if headers.get("Termination", "") == "Time forfeit":
            return False
        return lo <= we <= hi and lo <= be <= hi
    return qualifies


def _harvest_chunk(args):
    import io
    blocks, lo, hi = args
    qualifies = _make_qualifies(lo, hi)
    by_bin = defaultdict(list)
    for block in blocks:
        try:
            game = chess.pgn.read_game(io.StringIO(block))
        except Exception:
            continue
        if game is None or not qualifies(game.headers):
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
            continue
        if not positions:
            continue
        positions.sort(key=lambda t: -t[2])
        for fen, color, d, ply_idx in positions[:MAX_PER_GAME]:
            for blo, bhi in BINS:
                if blo <= d < bhi and len(by_bin[(blo, bhi)]) < PER_BIN:
                    by_bin[(blo, bhi)].append({
                        "fen": fen, "color": color, "danger": d,
                        "ply_idx": ply_idx, "sans": sans,
                        "white": game.headers.get("White"),
                        "black": game.headers.get("Black")})
    return dict(by_bin)


def harvest_candidates(lo, hi):
    blocks = _split_games(PGN)
    chunk = max(1, len(blocks) // (N_WORKERS * 4))
    chunks = [(blocks[i:i + chunk], lo, hi)
             for i in range(0, len(blocks), chunk)]
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
    print(f"[{lo}-{hi}] "
          f"{ {f'{a}-{b}': len(merged.get((a, b), [])) for a, b in BINS} }",
          flush=True)
    out = []
    for v in merged.values():
        out += v
    return out


def _label_one(row):
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


def label_all(sample):
    rows = []
    with mp.Pool(N_WORKERS, initializer=_init_engine) as pool:
        pending = [(row, pool.apply_async(_label_one, (row,)))
                  for row in sample]
        for row, ar in pending:
            try:
                r = ar.get(timeout=LABEL_TIMEOUT_SEC)
            except mp.TimeoutError:
                r = {**row, "label": 0, "reason": "timeout_skipped"}
            r.pop("sans", None)
            rows.append(r)
    return rows


def run_band(lo, hi):
    sample = harvest_candidates(lo, hi)
    rows = label_all(sample)
    excluded_reasons = {"already_lost_excluded", "timeout_skipped"}
    used = [r for r in rows if r["reason"] not in excluded_reasons]
    X = np.array([r["danger"] for r in used], dtype=float)
    y = np.array([r["label"] for r in used], dtype=float)
    result = {"band": [lo, hi], "n": len(used),
             "positive_rate": round(float(y.mean()), 4) if len(y) else None}
    if 0 < y.sum() < len(y):
        iso = IsotonicRegression(y_min=0.0, y_max=1.0,
                                 out_of_bounds="clip").fit(X, y)
        grid = np.arange(0, 773, 2)
        table = {int(g): round(float(iso.predict([g])[0]), 4) for g in grid}
        sp, sp_p = spearmanr(X, y)
        pb, pb_p = pointbiserialr(y, X)
        result.update({"table": table, "spearman": round(float(sp), 4),
                       "spearman_p": round(float(sp_p), 5),
                       "point_biserial": round(float(pb), 4),
                       "point_biserial_p": round(float(pb_p), 5),
                       "status": "fit", "rows": rows})
        print(f"[{lo}-{hi}] n={len(used)} pos={y.mean():.1%} "
              f"spearman={sp:.3f} (p={sp_p:.4f})", flush=True)
    else:
        result["status"] = "degenerate"
        result["rows"] = rows
        print(f"[{lo}-{hi}] n={len(used)} DEGENERATE "
              f"(pos_rate={result['positive_rate']})", flush=True)
    return result


if __name__ == "__main__":
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    result = run_band(lo, hi)
    out = os.path.join(HERE, f"band_{lo}_{hi}_report.json")
    json.dump(result, open(out, "w"), indent=1)
    print(f"wrote {out}")
