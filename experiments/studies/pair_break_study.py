"""pair_break_study — WHEN should the pair-less side exchange N-for-B?

USER RULING (2026-07-22): "if the opponent has the bishop pair AND the
position is open, exchange — otherwise you're dead lost." Finding 6 says the
pair PREMIUM is largest pawn-full (+4.8pp) and vanishes truly open (+0.9pp)
— the folklore inversion. Both can be true (where the pair is dangerous vs
where the DEFENSIVE exchange pays are different questions). This study cells
the exchange plan by openness and lets the corpus pick the gate.

Per game: first ply where one side faces the enemy bishop pair (2B vs their
own <2B) while holding >= 1 knight. Cell by openness AT THAT MOMENT (total
pawns: >= 14 full / 12-13 mid / <= 11 open). Then: did the pair-less side
RESOLVE the enemy pair within 30 plies (any capture of an enemy bishop that
ends the pair)? Score of the pair-less side by resolved/unresolved x cell.
"""
from __future__ import annotations

import sys

import chess
import chess.pgn

PGN = "/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn"
WINDOW = 30
SCORE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}


def has_pair(b, side):
    return len(b.pieces(chess.BISHOP, side)) >= 2


if __name__ == "__main__":
    cells = {}   # (cell, resolved) -> [scores]
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
            if len(moves) < 30:
                continue
            n_games += 1
            if n_games % 5000 == 0:
                print(f"  {n_games} games", file=sys.stderr, flush=True)
            b = game.board()
            onset = {}          # side -> (ply, cell) first pair-facing moment
            for i, mv in enumerate(moves):
                b.push(mv)
                if i < 12 or i > len(moves) - 10:
                    continue
                for side in (chess.WHITE, chess.BLACK):
                    if side in onset:
                        continue
                    if has_pair(b, not side) and not has_pair(b, side) \
                            and len(b.pieces(chess.KNIGHT, side)) >= 1:
                        pawns = (len(b.pieces(chess.PAWN, chess.WHITE))
                                 + len(b.pieces(chess.PAWN, chess.BLACK)))
                        cell = ("full" if pawns >= 14 else
                                "open" if pawns <= 11 else "mid")
                        onset[side] = (i, cell)
            if not onset:
                continue
            # second pass: did the pair get resolved within WINDOW plies?
            b = game.board()
            resolved_at = {}
            for i, mv in enumerate(moves):
                cap = b.piece_at(mv.to_square)
                for side in onset:
                    o_ply, _ = onset[side]
                    if side in resolved_at or i <= o_ply \
                            or i > o_ply + WINDOW:
                        continue
                    if cap and cap.piece_type == chess.BISHOP \
                            and cap.color != side:
                        b.push(mv)
                        if not has_pair(b, not side):
                            resolved_at[side] = i
                        b.pop()
                b.push(mv)
            for side, (o_ply, cell) in onset.items():
                s = SCORE[res] if side == chess.WHITE else 1.0 - SCORE[res]
                key = (cell, side in resolved_at)
                cells.setdefault(key, []).append(s)

    import statistics
    print(f"{n_games} games scanned")
    print(f"{'cell':>6} | {'pair RESOLVED <=30 plies':>26} | "
          f"{'NOT resolved':>20} | edge")
    for cell in ("open", "mid", "full"):
        r = cells.get((cell, True), [])
        u = cells.get((cell, False), [])
        if len(r) >= 30 and len(u) >= 30:
            mr, mu = statistics.mean(r), statistics.mean(u)
            print(f"{cell:>6} | {mr:.3f} (n={len(r):>5}) {'':>8} | "
                  f"{mu:.3f} (n={len(u):>5}) | {100*(mr-mu):+.1f}pp")
