"""The structure->plan evidence table, row 1: Carlsbad / minority attack.

For every game that HOLDS the (reversed-)Carlsbad structure >= 10 plies,
record how far the minority side's choreography got:
  none      — structure held, b-pawn never advanced to the 4th
  launched  — b-pawn reached the 4th (side-relative) while structure held
  advanced  — b-pawn reached the 5th
  completed — lever resolved (the detector's full criterion)
plus the minority side's score. This is the DENOMINATOR the reliability
numbers need: P(launch | structure), P(complete | launch), score by stage.
"""
from __future__ import annotations

import json
import statistics
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans")
from detectors import is_carlsbad, is_carlsbad_reversed

STRUCT_MIN = 10


def stage(game, side):
    """(stage, score-for-side) or None if structure never held long enough."""
    struct_check = is_carlsbad if side == chess.WHITE else is_carlsbad_reversed
    adv1, adv2 = ("b4", "b5") if side == chess.WHITE else ("b5", "b4")
    lever_own = "bxc6" if side == chess.WHITE else "bxc3"
    lever_opp = ("cxb5", "axb5") if side == chess.WHITE else ("cxb4", "axb4")
    b = game.board()
    struct = 0
    p1 = p2 = lever = None
    for mv in game.mainline_moves():
        san = b.san(mv)
        mover_is_side = b.turn == side
        if struct_check(b):
            struct += 1
            if mover_is_side and b.piece_at(mv.from_square) and \
                    b.piece_at(mv.from_square).piece_type == chess.PAWN:
                to = chess.square_name(mv.to_square)
                if to == adv1 and p1 is None:
                    p1 = True
                if to == adv2 and p1 is not None:
                    p2 = True
            if mover_is_side and san == lever_own and p2:
                lever = True
        if not mover_is_side and p2 and lever is None and san in lever_opp:
            lever = True
        b.push(mv)
    if struct < STRUCT_MIN:
        return None
    st = ("completed" if lever else
          "advanced" if p2 else
          "launched" if p1 else "none")
    res = game.headers.get("Result", "*")
    if res not in ("1-0", "0-1", "1/2-1/2"):
        return None
    sc = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[res]
    return st, sc if side == chess.WHITE else 1.0 - sc


if __name__ == "__main__":
    CORPORA = [("lichess", "/Users/avismara/Development/lucena/lucena-plans/data/lichess_elite_2023-01.pgn"),
               ("gm", "/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn")]
    rows = []
    for name, path in CORPORA:
        n = 0
        with open(path, encoding="latin-1") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                n += 1
                if n % 25000 == 0:
                    print(f"[{name}] scanned {n}, structure games {len(rows)}", flush=True)
                for side, sname in ((chess.WHITE, "white"), (chess.BLACK, "black")):
                    try:
                        r = stage(game, side)
                    except Exception:
                        continue
                    if r:
                        rows.append({"corpus": name, "side": sname,
                                     "stage": r[0], "score": r[1]})
        print(f"[{name}] done: {n} games", flush=True)

    with open("/Users/avismara/Development/lucena/lucena-plans/experiments/carlsbad_row.jsonl", "w") as g:
        for r in rows:
            g.write(json.dumps(r) + "\n")

    STAGES = ["none", "launched", "advanced", "completed"]
    for corpus in ("lichess", "gm"):
        for side in ("white", "black"):
            rs = [r for r in rows if r["corpus"] == corpus and r["side"] == side]
            if not rs:
                continue
            print(f"\n== {corpus} / {side}-side minority ({len(rs)} structure games) ==")
            launched = sum(1 for r in rs if r["stage"] != "none")
            completed = sum(1 for r in rs if r["stage"] == "completed")
            print(f"launch rate {100*launched/len(rs):.1f}%  |  "
                  f"complete-given-launch "
                  f"{100*completed/max(1,launched):.1f}%")
            for st in STAGES:
                ss = [r["score"] for r in rs if r["stage"] == st]
                if len(ss) < 3:
                    continue
                dr = statistics.mean(1.0 if s == 0.5 else 0.0 for s in ss)
                print(f"  {st:>10}: n={len(ss):>5}  score {statistics.mean(ss):.3f}  "
                      f"draws {100*dr:.0f}%")
