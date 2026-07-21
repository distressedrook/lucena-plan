"""Weakness detectors — the fixed-target vocabulary for plan conversion.

The two-weaknesses experiment (experiments/weakness_census.py) established
that CREATION of weaknesses is flat as a predictor and HARVEST is a strong
monotone gradient; a complete census needs the full classical taxonomy.

Implemented (each pure geometry, side = the side OWNING the weakness):
  weak_pawns        isolated/backward pawn on a file where the enemy has no
                    pawn (rook-attackable), unsupportable by own pawns, not
                    passed
  entombed_bishops  bishop behind its own most advanced rammed same-color
                    pawn (>= 3 own pawns on its color, >= 2 rammed)
  occupied_outposts hole in own camp (a square no own pawn can EVER attack,
                    own 3rd-5th rank) currently held by an enemy knight or
                    bishop that is supported by an enemy pawn
  exposed_king      >= 2 of the files (king's file and neighbors) have no own
                    pawn — open lanes to the king; counts as ONE weakness

Not yet implemented (needs design): passive rook, weak color complex (>= 3
same-color holes), back-rank weakness, overextended pawns.
"""
from __future__ import annotations

import chess


def side_rank(sq: int, side: bool) -> int:
    r = chess.square_rank(sq)
    return r if side == chess.WHITE else 7 - r


def sq_color(sq: int) -> bool:
    return bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[sq])


def weak_pawns(b: chess.Board, side: bool) -> list[int]:
    """Own pawns on enemy-pawn-free files, unsupportable, not passed."""
    own = b.pieces(chess.PAWN, side)
    enemy = b.pieces(chess.PAWN, not side)
    efiles = {chess.square_file(s) for s in enemy}
    out = []
    for sq in own:
        f = chess.square_file(sq)
        if f in efiles:
            continue
        r = side_rank(sq, side)
        if any(chess.square_file(s) in (f - 1, f + 1)
               and side_rank(s, side) <= r for s in own if s != sq):
            continue
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r for s in enemy):
            continue                       # passed pawn: strength, not weakness
        out.append(sq)
    return out


def entombed_bishops(b: chess.Board, side: bool) -> list[int]:
    out = []
    ahead = 8 if side == chess.WHITE else -8
    for sq in b.pieces(chess.BISHOP, side):
        c = sq_color(sq)
        total = fixed = 0
        ram_rank = -1
        for p in b.pieces(chess.PAWN, side):
            if sq_color(p) != c:
                continue
            total += 1
            front = p + ahead
            if 0 <= front < 64:
                pc = b.piece_at(front)
                if pc and pc.piece_type == chess.PAWN and pc.color != side:
                    fixed += 1
                    ram_rank = max(ram_rank, side_rank(p, side))
        if total >= 3 and fixed >= 2 and side_rank(sq, side) < ram_rank:
            out.append(sq)
    return out


def is_hole(b: chess.Board, sq: int, side: bool) -> bool:
    """No own pawn can EVER attack sq (own pawns attack toward higher
    side-relative ranks): no own pawn on an adjacent file strictly behind."""
    f, r = chess.square_file(sq), side_rank(sq, side)
    return not any(chess.square_file(p) in (f - 1, f + 1)
                   and side_rank(p, side) < r
                   for p in b.pieces(chess.PAWN, side))


def occupied_outposts(b: chess.Board, side: bool) -> list[int]:
    """Enemy minors sitting on pawn-supported holes in our 3rd-5th rank."""
    out = []
    for pt in (chess.KNIGHT, chess.BISHOP):
        for sq in b.pieces(pt, not side):
            if not (2 <= side_rank(sq, side) <= 4):
                continue
            if not is_hole(b, sq, side):
                continue
            support = any(p.piece_type == chess.PAWN and p.color != side
                          for p in (b.piece_at(a) for a in b.attackers(not side, sq))
                          if p)
            if support:
                out.append(sq)
    return out


def exposed_king(b: chess.Board, side: bool) -> bool:
    ksq = b.king(side)
    if ksq is None:
        return False
    kf = chess.square_file(ksq)
    own_files = {chess.square_file(s) for s in b.pieces(chess.PAWN, side)}
    lanes = sum(1 for f in (kf - 1, kf, kf + 1)
                if 0 <= f <= 7 and f not in own_files)
    return lanes >= 2


def census(b: chess.Board, side: bool) -> dict:
    """All fixed targets in `side`'s camp; 'total' is the census number."""
    wp = weak_pawns(b, side)
    eb = entombed_bishops(b, side)
    op = occupied_outposts(b, side)
    ek = exposed_king(b, side)
    return {"weak_pawns": wp, "entombed_bishops": eb,
            "occupied_outposts": op, "exposed_king": ek,
            "total": len(wp) + len(eb) + len(op) + (1 if ek else 0)}
