"""simplify_gate_study — calibrate the SIMPLIFY advisory gate (the mirror).

USER RULING (2026-07-22): "if I have a lot of space, avoid trades —
universally true, doesn't need engine checking; but the space difference
must be CONSIDERABLE before we surface it." Direction taken as canonical
(the mirror of SIMPLIFY, which we already offer the cramped side at
diff <= -4). This study calibrates the one free parameter: at WHAT space
differential does trade-avoidance start paying?

Per game: anchor at ply 30. If one side's space edge (pawn-advancement sum
diff) >= 2, record: the edge bucket, the number of piece trades (non-pawn
captures resolving into recaptures, approximated as non-pawn captures) in
the next 24 plies, and the space side's final score. Cells: edge bucket x
trades (0-1 = avoided, 2-3 = some, 4+ = heavy).
"""
from __future__ import annotations

import sys

import chess
import chess.pgn

PGN = "/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn"
ANCHOR = 30
WINDOW = 24
SCORE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}


def space(b, side):
    tot = 0
    for p in b.pieces(chess.PAWN, side):
        r = chess.square_rank(p)
        tot += (r - 1) if side == chess.WHITE else (6 - r)
    return tot


if __name__ == "__main__":
    cells = {}
    n_games = 0
    with open(PGN, encoding="latin-1") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            res = game.headers.get("Result", "*")
            if res not in SCORE:
                continue
            moves = list(game.mainline_moves())
            if len(moves) < ANCHOR + WINDOW + 4:
                continue
            n_games += 1
            if n_games % 5000 == 0:
                print(f"  {n_games}", file=sys.stderr, flush=True)
            b = game.board()
            for mv in moves[:ANCHOR]:
                b.push(mv)
            dw = space(b, chess.WHITE) - space(b, chess.BLACK)
            if abs(dw) < 2:
                continue
            side = chess.BLACK if dw > 0 else chess.WHITE   # the CRAMPED side
            edge = abs(dw)
            bucket = ("2-3" if edge <= 3 else "4-5" if edge <= 5 else
                      "6-7" if edge <= 7 else "8+")
            trades = 0
            for mv in moves[ANCHOR:ANCHOR + WINDOW]:
                cap = b.piece_at(mv.to_square)
                if cap and cap.piece_type != chess.PAWN:
                    trades += 1
                b.push(mv)
            tcell = "avoided(0-1)" if trades <= 1 else \
                    "some(2-3)" if trades <= 3 else "heavy(4+)"
            s = SCORE[res] if side == chess.WHITE else 1.0 - SCORE[res]
            cells.setdefault((bucket, tcell), []).append(s)

    import statistics
    print(f"{n_games} games")
    print(f"{'edge':>5} | {'avoided(0-1)':>18} | {'some(2-3)':>18} | "
          f"{'heavy(4+)':>18} | avoid-vs-heavy")
    for bucket in ("2-3", "4-5", "6-7", "8+"):
        row = []
        vals = {}
        for tc in ("avoided(0-1)", "some(2-3)", "heavy(4+)"):
            v = cells.get((bucket, tc), [])
            vals[tc] = statistics.mean(v) if len(v) >= 30 else None
            row.append(f"{vals[tc]:.3f} (n={len(v):>5})" if vals[tc] is not None
                       else f"    - (n={len(v):>5})")
        d = (f"{100*(vals['avoided(0-1)'] - vals['heavy(4+)']):+.1f}pp"
             if vals["avoided(0-1)"] is not None
             and vals["heavy(4+)"] is not None else "-")
        print(f"{bucket:>5} | " + " | ".join(row) + f" | {d}")
