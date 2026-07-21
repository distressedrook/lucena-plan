"""Plan signatures — run the pattern library over ANY move sequence
(engine PV, Maia rollout, actual continuation) and return the plan events.

Events (tagged W:/B: by the side executing):
  minority_launch/advance/lever  generalized minority staging (2v3+semi-open c)
  outpost      knight lands on a pawn-supported hole in the enemy camp
  harvest      captures an enemy WEAK pawn (weak at the previous ply)
  seal         creates a new central ram (closing move)
  break        removes a central ram (pawn break)
  entomb       enemy bishop becomes entombed
  escape       own previously-entombed bishop gets out (still on board)
  open_king    enemy king becomes exposed (>= 2 pawn-free adjacent files)
  storm_q/k    >= 2 own pawn advances on that wing inside the window
"""
from __future__ import annotations

import sys

import chess

sys.path.insert(0, "/Users/avismara/Development/chess-plans")
from weaknesses import (weak_pawns, entombed_bishops, exposed_king, is_hole,
                        side_rank)

QS = {0, 1, 2}


def _minority_pre(b: chess.Board, side: bool) -> bool:
    own = [s for s in b.pieces(chess.PAWN, side) if chess.square_file(s) in QS]
    opp = [s for s in b.pieces(chess.PAWN, not side) if chess.square_file(s) in QS]
    return (len(own) == 2 and not any(chess.square_file(s) == 2 for s in own)
            and len(opp) == 3 and any(chess.square_file(s) == 2 for s in opp))


def _rel(sq: int, side: bool) -> str:
    if side == chess.BLACK:
        sq = chess.square(chess.square_file(sq), 7 - chess.square_rank(sq))
    return chess.square_name(sq)


def _central_rams(b: chess.Board) -> int:
    wp = b.pieces(chess.PAWN, chess.WHITE)
    bp = b.pieces(chess.PAWN, chess.BLACK)
    return sum(1 for s in wp if s + 8 < 64 and (s + 8) in bp
               and 2 <= chess.square_file(s) <= 5)


def signature(start: chess.Board, moves: list[chess.Move],
              horizon: int = 12) -> set[str]:
    b = start.copy()
    ev = set()
    prev_weak = {s: set(weak_pawns(b, s)) for s in (chess.WHITE, chess.BLACK)}
    prev_ent = {s: set(entombed_bishops(b, s)) for s in (chess.WHITE, chess.BLACK)}
    prev_exp = {s: exposed_king(b, s) for s in (chess.WHITE, chess.BLACK)}
    prev_rams = _central_rams(b)
    pawn_adv = {chess.WHITE: {"q": 0, "k": 0}, chess.BLACK: {"q": 0, "k": 0}}
    for mv in moves[:horizon]:
        if mv not in b.legal_moves:
            break
        mover = b.turn
        enemy = not mover
        tag = "W" if mover == chess.WHITE else "B"
        pc = b.piece_at(mv.from_square)
        cap = b.is_capture(mv)
        if cap and mv.to_square in prev_weak[enemy]:
            ev.add(f"{tag}:harvest")
        if pc and pc.piece_type == chess.PAWN and _minority_pre(b, mover):
            to = _rel(mv.to_square, mover)
            if to == "b4":
                ev.add(f"{tag}:minority_launch")
            elif to == "b5":
                ev.add(f"{tag}:minority_advance")
            elif to == "c6" and cap:
                ev.add(f"{tag}:minority_lever")
        # lever resolved by the DEFENDER capturing on the owner's b5 —
        # completion either way (corpus ruling, minority_general.py)
        if pc and pc.piece_type == chess.PAWN and cap \
                and _minority_pre(b, enemy) and _rel(mv.to_square, enemy) == "b5":
            owner_tag = "W" if enemy == chess.WHITE else "B"
            if f"{owner_tag}:minority_advance" in ev:
                ev.add(f"{owner_tag}:minority_lever")
        if pc and pc.piece_type == chess.PAWN:
            f = chess.square_file(mv.from_square)
            if f in QS:
                pawn_adv[mover]["q"] += 1
            elif f >= 5:
                pawn_adv[mover]["k"] += 1
        b.push(mv)
        if pc and pc.piece_type == chess.KNIGHT:
            sq = mv.to_square
            if 2 <= side_rank(sq, enemy) <= 4 and is_hole(b, sq, enemy) \
                    and any(p and p.piece_type == chess.PAWN and p.color == mover
                            for p in (b.piece_at(a)
                                      for a in b.attackers(mover, sq))):
                ev.add(f"{tag}:outpost")
        rams = _central_rams(b)
        if rams > prev_rams:
            ev.add(f"{tag}:seal")
        elif rams < prev_rams and cap:
            ev.add(f"{tag}:break")
        prev_rams = rams
        for s in (chess.WHITE, chess.BLACK):
            t = "W" if s == chess.WHITE else "B"
            ent = set(entombed_bishops(b, s))
            if ent - prev_ent[s] and s == enemy:
                ev.add(f"{tag}:entomb")
            if prev_ent[s] and not ent and s == mover \
                    and b.pieces(chess.BISHOP, s):
                ev.add(f"{tag}:escape")
            prev_ent[s] = ent
            exp = exposed_king(b, s)
            if exp and not prev_exp[s] and s == enemy:
                ev.add(f"{tag}:open_king")
            prev_exp[s] = exp
            prev_weak[s] = set(weak_pawns(b, s))
    for s, t in ((chess.WHITE, "W"), (chess.BLACK, "B")):
        for wing in ("q", "k"):
            if pawn_adv[s][wing] >= 2:
                ev.add(f"{t}:storm_{wing}")
    return ev
