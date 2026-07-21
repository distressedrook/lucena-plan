"""suggest.py — the position→plan suggester, v0. THE front door.

    ./suggest.py "FEN"
    ./suggest.py game.pgn 24        # position after move 24 (white's 24th)

Wires together every corpus-validated layer:
  structures.py   what structure is on the board (trigger layer)
  closed_v0       closedness skeleton (context)
  weaknesses.py   fixed-target census, both camps (conversion layer)
  hole scan       unoccupied deep holes = outpost plan targets
  evidence        hardcoded reliability numbers from the GM-corpus session
                  (CLAUDE.md findings; carlsbad_row, outpost laws, escape
                  hierarchy, harvest-gating)

Output: the position's states, then plans for each side ranked by the
corpus effect size, each with its reliability line and concrete guidance.
"""
from __future__ import annotations

import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/chess-plans")
sys.path.insert(0, "/Users/avismara/Development/chess-plans/experiments")
from structures import classify
from closed_v0 import skeleton
from weaknesses import census, is_hole, side_rank, weak_pawns, entombed_bishops


def holes_in(b: chess.Board, side: bool) -> list[tuple[str, bool]]:
    """Deep holes in `side`'s camp: (square, currently pawn-supportable by
    the enemy). Depth: enemy-relative rank 5-6, files b-g."""
    out = []
    enemy = not side
    for sq in chess.SQUARES:
        f = chess.square_file(sq)
        if not 1 <= f <= 6:
            continue
        if not 4 <= side_rank(sq, enemy) <= 5:
            continue
        if b.piece_at(sq):
            continue
        if not is_hole(b, sq, side):
            continue
        support = any(chess.square_file(p) in (f - 1, f + 1)
                      and side_rank(p, enemy) < side_rank(sq, enemy)
                      for p in b.pieces(chess.PAWN, enemy))
        out.append((chess.square_name(sq), support))
    return out


def name_side(s: bool) -> str:
    return "White" if s else "Black"


def suggest(b: chess.Board) -> str:
    L = []
    structs = classify(b)
    rams, central, tension, open_files = skeleton(b)
    closed = central >= 2 and open_files == 0 and tension <= 1 and rams >= 4

    L.append("== position states ==")
    if structs:
        for n, owner in structs:
            L.append(f"  structure: {n} (owner {name_side(owner)})")
    else:
        L.append("  structure: none from the catalog")
    L.append(f"  skeleton: rams {rams} (central {central}), tension {tension}, "
             f"open files {open_files}"
             + ("  -> HERMETICALLY CLOSED (maneuvering chess; closed GM games "
                "are MORE decisive: 47% draws vs 56%)" if closed else ""))
    for side in (chess.WHITE, chess.BLACK):
        c = census(b, side)
        parts = []
        if c["weak_pawns"]:
            parts.append("weak pawns " + ",".join(chess.square_name(s)
                                                  for s in c["weak_pawns"]))
        if c["entombed_bishops"]:
            parts.append("ENTOMBED bishop " + ",".join(chess.square_name(s)
                                                       for s in c["entombed_bishops"]))
        if c["occupied_outposts"]:
            parts.append("enemy outpost on " + ",".join(chess.square_name(s)
                                                        for s in c["occupied_outposts"]))
        if c["exposed_king"]:
            parts.append("exposed king")
        L.append(f"  {name_side(side)} camp weaknesses [{c['total']}]: "
                 + ("; ".join(parts) if parts else "none"))

    for side in (chess.WHITE, chess.BLACK):
        enemy = not side
        plans = []

        # -- minority attack: 2v3 queenside + semi-open c-file (2026-07-22
        #    ruling), family-split numbers from minority_general.py
        own_qs = [s for s in b.pieces(chess.PAWN, side)
                  if chess.square_file(s) <= 2]
        opp_qs = [s for s in b.pieces(chess.PAWN, enemy)
                  if chess.square_file(s) <= 2]
        if (len(own_qs) == 2 and not any(chess.square_file(s) == 2 for s in own_qs)
                and len(opp_qs) == 3
                and any(chess.square_file(s) == 2 for s in opp_qs)):
            in_carlsbad = any(n == "carlsbad" and o == side for n, o in structs)
            if in_carlsbad:
                plans.append((
                    4.0, "MINORITY ATTACK (Carlsbad): march b-pawn b4-b5, "
                    "lever bxc6",
                    "GM evidence: completed 0.547 vs 0.507 unlaunched; launch "
                    "25%, lever reached 22% of launches. WARNING: stalling at "
                    "b5 scores 0.446 — commit to the lever or don't start. "
                    "Witnesses: minority-attack-gm/teaching-set/."))
            else:
                plans.append((
                    1.8, "MINORITY ATTACK (generalized 2v3 + semi-open c): "
                    "b4-b5 against c6 — playable but pays only if the lever "
                    "actually resolves",
                    "GM evidence: GMs launch this as often as in the Carlsbad "
                    "(25%) but the lever resolves only 13% of launches; "
                    "launched-overall runs 0.472 vs 0.495 baseline, completed "
                    "0.513. Pair it with c-file pressure and only commit when "
                    "the lever is forceable. (...c5 by the defender is NOT a "
                    "refutation — attacker scores are flat-to-better after it.)"))

        # -- outpost plan (deep holes in enemy camp)
        hs = holes_in(b, enemy)
        if hs:
            sup = [h for h, s in hs if s]
            plans.append((
                7.5, "OUTPOST PLAN: route a knight to "
                + ",".join(h for h, _ in hs[:4])
                + (f" (pawn-supportable: {','.join(sup[:4])})" if sup else ""),
                "GM evidence: sustained supported outposts in 21% of games; "
                "value is DEPTH (6th rank 0.584, 5th 0.561, 4th 0.509); rim "
                "outposts are worthless (0.496); f5-type king-adjacent squares "
                "best (0.630). Median journey: 3-4 knight moves — start now. "
                "Canonical route shape: b1-c3-d5."))

        # -- exploit entombed enemy bishop / seal threat
        ent = entombed_bishops(b, enemy)
        if ent:
            plans.append((
                4.9, "KEEP THE BISHOP ENTOMBED: avoid freeing pawn trades, "
                "trade the OTHER minors, invade on its color",
                "GM evidence: entombed bishop = the largest B-vs-N effect "
                "(owner scores 0.424 in open positions). But conversion needs "
                "a SECOND weakness: piece-access ones pay rent (outpost "
                "+8.3pp, exposed king +6.7pp); the pawn weakness pays only "
                "when captured (harvest 0.489->0.656)."))

        # -- own entombed bishop: escape hierarchy
        own_ent = entombed_bishops(b, side)
        if own_ent:
            plans.append((
                6.0, "ESCAPE THE BAD BISHOP (before trading it): reroute it "
                "outside the chain "
                "(Bd7-e8-h5 / Bg5-family gates); trade only if extraction fails",
                "GM evidence (4,581 cases): extraction restores near-equality "
                "(0.496); trading recovers only half (0.456); doing nothing is "
                "worst (0.436). Escaping BEATS trading — revised textbook."))

        # -- harvest weak enemy pawns
        wp = weak_pawns(b, enemy)
        if wp:
            plans.append((
                8.4, "HARVEST the weak pawn(s) "
                + ",".join(chess.square_name(s) for s in wp)
                + " — attack to WIN them, not to admire them",
                "GM evidence: weakness harvested 1x -> 0.577, 2x -> 0.656; "
                "created-but-never-harvested -> 0.453, WORSE than no weakness. "
                "If the pawn is defensible, switch: convert the defenders' "
                "passivity into a piece-access weakness (outpost / king "
                "lanes) — those pay rent by presence."))

        if plans:
            L.append(f"\n== plans for {name_side(side)} "
                     f"(ranked by corpus effect size) ==")
            for eff, head, ev in sorted(plans, key=lambda p: -p[0]):
                L.append(f"  [{eff:+.1f}pp] {head}")
                L.append(f"           {ev}")
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1].endswith(".pgn"):
        game = chess.pgn.read_game(open(sys.argv[1]))
        target = int(sys.argv[2]) * 2 - 1
        b = game.board()
        for i, mv in enumerate(game.mainline_moves()):
            b.push(mv)
            if i + 1 >= target:
                break
    elif len(sys.argv) >= 2:
        b = chess.Board(sys.argv[1])
    else:
        print(__doc__)
        sys.exit(1)
    print(suggest(b))
