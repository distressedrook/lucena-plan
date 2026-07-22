"""Generalized minority attack — adjudicating the 2026-07-22 ruling:

    "Minority attack is: 2 pawns vs 3. Semi-open c-file."

Precondition (owner-relative, mirrored for Black): owner has exactly 2 pawns
on files a-c with NO c-pawn; enemy has exactly 3 pawns on files a-c including
a c-pawn (semi-open c-file for the owner). Held >= 10 plies.

Staging (as evidence_table.py): none / launched (b4) / advanced (b5) /
completed (lever: bxc6 or enemy ...cxb5/axb5).

Adjudicated questions:
  1. Do NON-Carlsbad instances launch/complete/pay like Carlsbad ones?
  2. How often does the defender dissolve the target with ...c5 (the c-pawn
     advancing while the precondition holds), and what does it cost/save?
"""
from __future__ import annotations

import statistics
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans")
from detectors import is_carlsbad, is_carlsbad_reversed

QS = {0, 1, 2}          # files a, b, c


def rel_sq(sq: int, side: bool) -> str:
    if side == chess.BLACK:
        sq = chess.square(chess.square_file(sq), 7 - chess.square_rank(sq))
    return chess.square_name(sq)


def precondition(b: chess.Board, side: bool) -> bool:
    own = [s for s in b.pieces(chess.PAWN, side) if chess.square_file(s) in QS]
    opp = [s for s in b.pieces(chess.PAWN, not side) if chess.square_file(s) in QS]
    return (len(own) == 2 and not any(chess.square_file(s) == 2 for s in own)
            and len(opp) == 3 and any(chess.square_file(s) == 2 for s in opp))


def study(game, side):
    b = game.board()
    held = 0
    p1 = p2 = lever = False
    c5 = False
    carlsbad_overlap = False
    struct = is_carlsbad if side == chess.WHITE else is_carlsbad_reversed
    for mv in game.mainline_moves():
        pre = precondition(b, side)
        if pre:
            held += 1
            if struct(b):
                carlsbad_overlap = True
            mover = b.turn
            pc = b.piece_at(mv.from_square)
            if pc and pc.piece_type == chess.PAWN:
                to = rel_sq(mv.to_square, side)
                if mover == side:
                    if to == "b4":
                        p1 = True
                    elif to == "b5" and p1:
                        p2 = True
                    elif to == "c6" and p2 and b.is_capture(mv):
                        lever = True
                else:
                    to_e = rel_sq(mv.to_square, side)
                    if to_e == "b5" and p2 and b.is_capture(mv):
                        lever = True          # enemy resolves the lever on b5
                    if to_e == "c5" and chess.square_file(mv.from_square) == 2:
                        c5 = True             # defender's c-pawn advances: dissolution
        b.push(mv)
    if held < 10:
        return None
    res = game.headers.get("Result", "*")
    if res not in ("1-0", "0-1", "1/2-1/2"):
        return None
    sc = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[res]
    stage = ("completed" if lever else "advanced" if p2
             else "launched" if p1 else "none")
    return {"stage": stage, "carlsbad": carlsbad_overlap, "c5": c5,
            "score": sc if side == chess.WHITE else 1.0 - sc}


if __name__ == "__main__":
    CORPORA = [("gm", "/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn"),
               ("lichess", "/Users/avismara/Development/lucena/lucena-plans/data/lichess_elite_2023-01.pgn")]
    rows = []
    for cname, path in CORPORA:
        n = 0
        with open(path, encoding="latin-1") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                n += 1
                if n % 25000 == 0:
                    print(f"[{cname}] {n}, cases {len(rows)}", flush=True)
                for side, sname in ((chess.WHITE, "white"), (chess.BLACK, "black")):
                    try:
                        r = study(game, side)
                    except Exception:
                        continue
                    if r:
                        rows.append({**r, "corpus": cname, "side": sname})
        print(f"[{cname}] done ({n} games)", flush=True)

    STAGES = ["none", "launched", "advanced", "completed"]
    for cname in ("gm", "lichess"):
        for family, test in (("CARLSBAD", True), ("NON-carlsbad", False)):
            rs = [r for r in rows if r["corpus"] == cname and r["carlsbad"] == test]
            if len(rs) < 20:
                continue
            launched = sum(1 for r in rs if r["stage"] != "none")
            completed = sum(1 for r in rs if r["stage"] == "completed")
            print(f"\n== {cname} / {family} ({len(rs)} minority games) ==")
            print(f"launch {100*launched/len(rs):.0f}% | "
                  f"complete|launch {100*completed/max(1,launched):.0f}%")
            for st in STAGES:
                ss = [r["score"] for r in rs if r["stage"] == st]
                if len(ss) >= 5:
                    print(f"  {st:>10}: n={len(ss):>5}  score {statistics.mean(ss):.3f}")
            # dissolution
            for lab, cond in (("...c5 played", True), ("no ...c5", False)):
                ss = [r["score"] for r in rs if r["c5"] == cond]
                if len(ss) >= 5:
                    print(f"  {lab:>12}: n={len(ss):>5}  attacker score "
                          f"{statistics.mean(ss):.3f}")
