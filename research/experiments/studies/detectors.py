"""Plan detectors — choreography theorems for named plans.

Finding (three-tagged-games experiment, 2026-07-20): plans that RESTRUCTURE
are observable in the moves (pawn choreography + levers), not in static
eval-term drift — the terms only drift later, at the harvest. So plan
detection is mechanism-style geometry over move sequences, validated at
corpus scale, exactly like the tactical vocabulary.

Plans follow STRUCTURES, not openings: the reversed Carlsbad (Black's
minority attack) arises from the Exchange Caro-Kann, the London System,
and assorted Queen's Pawn games alike. The detectors read pawn skeletons.

Corpus validation (Lichess elite 2023-01):
  white minority attack:  53 / 28,461 games
  black minority attack: 102 / 60,000 games (mostly vs London/QP structures)
"""
from __future__ import annotations

import chess
import chess.pgn


def is_carlsbad(b: chess.Board) -> bool:
    """QGD-Exchange skeleton: White d4, no c-pawn; Black c6+d5, no e-pawn."""
    wp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.WHITE)}
    bp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.BLACK)}
    return ("d4" in wp and not any(sq[0] == "c" for sq in wp)
            and "c6" in bp and "d5" in bp and not any(sq[0] == "e" for sq in bp))


def is_carlsbad_reversed(b: chess.Board) -> bool:
    """Mirror (Exchange Caro / London-family): White d4 + c-pawn, no e-pawn;
    Black d5 + e-pawn, no c-pawn. Here BLACK owns the queenside minority."""
    wp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.WHITE)}
    bp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.BLACK)}
    return ("d4" in wp and any(sq[0] == "c" for sq in wp)
            and not any(sq[0] == "e" for sq in wp)
            and "d5" in bp and any(sq[0] == "e" for sq in bp)
            and not any(sq[0] == "c" for sq in bp))


def _detect(game, side: bool):
    """Shared choreography: minority pawn to 4th, then 5th (side-relative),
    then the lever resolves; post-condition: majority side's b-pawn gone."""
    struct_check = is_carlsbad if side == chess.WHITE else is_carlsbad_reversed
    adv1, adv2 = ("b4", "b5") if side == chess.WHITE else ("b5", "b4")
    lever_own = "bxc6" if side == chess.WHITE else "bxc3"
    lever_opp = ("cxb5", "axb5") if side == chess.WHITE else ("cxb4", "axb4")

    b = game.board()
    struct = 0
    p1 = p2 = lever = None
    sans = []
    for i, mv in enumerate(game.mainline_moves()):
        san = b.san(mv)
        mover_is_side = b.turn == side
        if struct_check(b):
            struct += 1
            if mover_is_side and b.piece_at(mv.from_square) and \
                    b.piece_at(mv.from_square).piece_type == chess.PAWN:
                to = chess.square_name(mv.to_square)
                if to == adv1 and p1 is None:
                    p1 = i
                if to == adv2 and p1 is not None:
                    p2 = i
            if mover_is_side and san == lever_own and p2 is not None:
                lever = i
        if not mover_is_side and p2 is not None and lever is None \
                and san in lever_opp:
            lever = i
        b.push(mv)
        sans.append(san)
    if struct < 10 or p1 is None or p2 is None or lever is None:
        return None
    majority = not side
    mp = {chess.square_name(s) for s in b.pieces(chess.PAWN, majority)}
    return {"plan": "minority_attack",
            "side": "white" if side == chess.WHITE else "black",
            "span": (p1, lever),
            "moves": " ".join(sans[p1:lever + 1]),
            "majority_b_pawn_gone": not any(sq[0] == "b" for sq in mp)}


def detect_minority_attack(game):
    """Either side; returns the first detected (White checked first)."""
    return _detect(game, chess.WHITE) or _detect(game, chess.BLACK)
