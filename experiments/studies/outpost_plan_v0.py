"""The hole/outpost PLAN, v0 — choreography theorem for the census's
strongest rent-payer (occupied outposts, +8.3pp by presence).

Plan-unit:
  concession — the ply the square permanently became a hole in the defender's
               camp (self-advance by the defender vs an exchange that removed
               the guarding pawn), tracked backward from occupation
  journey    — the occupying knight's moves from concession to arrival
  anchoring  — attacker pawn support at arrival (required)
  rent       — occupation sustained >= HOLD plies (else transient)

v0 scope: knights only (the classical outpost piece), hole = square no
defender pawn can ever attack, defender-relative rank 2-4, arrival supported.
"""
from __future__ import annotations

import collections
import statistics

import chess
import chess.pgn

HOLD = 8


def side_rank(sq: int, side: bool) -> int:
    r = chess.square_rank(sq)
    return r if side == chess.WHITE else 7 - r


def hole_for(pawns: set[int], sq: int, side: bool) -> bool:
    """No pawn of `side` (given as a square-set) can ever attack sq."""
    f, r = chess.square_file(sq), side_rank(sq, side)
    return not any(chess.square_file(p) in (f - 1, f + 1)
                   and side_rank(p, side) < r for p in pawns)


def study(game):
    b = game.board()
    moves = list(game.mainline_moves())
    n = len(moves)
    # forward pass: record per-ply defender pawn sets and knight journeys
    pawn_sets = []                     # per ply: {side: frozenset}
    journeys = {}                      # current knight square -> [squares...]
    for side in (chess.WHITE, chess.BLACK):
        for s in b.pieces(chess.KNIGHT, side):
            journeys[s] = [s]
    arrivals = []                      # (ply, sq, attacker, journey list)
    sans = []
    for i, mv in enumerate(moves):
        mover = b.turn
        pc = b.piece_at(mv.from_square)
        sans.append(b.san(mv))
        if mv.to_square in journeys:   # any knight on target square is captured
            del journeys[mv.to_square]
        if pc and pc.piece_type == chess.KNIGHT and mv.from_square in journeys:
            journeys[mv.to_square] = journeys.pop(mv.from_square) + [mv.to_square]
        b.push(mv)
        pawn_sets.append({chess.WHITE: frozenset(b.pieces(chess.PAWN, chess.WHITE)),
                          chess.BLACK: frozenset(b.pieces(chess.PAWN, chess.BLACK))})
        if pc and pc.piece_type == chess.KNIGHT:
            defender = not mover
            sq = mv.to_square
            if 2 <= side_rank(sq, defender) <= 4 \
                    and hole_for(pawn_sets[i][defender], sq, defender) \
                    and any(p.piece_type == chess.PAWN and p.color == mover
                            for p in (b.piece_at(a) for a in b.attackers(mover, sq)) if p):
                arrivals.append((i, sq, mover, list(journeys.get(sq, [sq]))))
    out = []
    for (i, sq, attacker, journey) in arrivals:
        # rent: knight stays HOLD plies (no later move from/to sq within window)
        stays = True
        for j in range(i + 1, min(i + 1 + HOLD, n)):
            if moves[j].from_square == sq or moves[j].to_square == sq:
                stays = False
                break
        if not stays:
            continue
        defender = not attacker
        # concession: earliest ply from which the hole held continuously
        j = i
        while j > 0 and hole_for(pawn_sets[j - 1][defender], sq, defender):
            j -= 1
        concession_ply = j - 1 if j > 0 else None
        ctype = None
        if concession_ply is not None:
            cmv = moves[concession_ply]
            b2mover = chess.WHITE if concession_ply % 2 == 0 else chess.BLACK
            ctype = "self_advance" if b2mover == defender else "exchange"
        # journey measured from concession to arrival
        route = journey[-4:]
        rel = sq if attacker == chess.WHITE else \
            chess.square(chess.square_file(sq), 7 - chess.square_rank(sq))
        out.append({"ply": i, "sq": chess.square_name(sq),
                    "rel_sq": chess.square_name(rel),          # owner-relative
                    "depth": side_rank(sq, attacker),   # attacker-relative rank:
                    # 3 = 4th-rank outpost (shallow) .. 5 = 6th-rank (deep)
                    "attacker": "white" if attacker == chess.WHITE else "black",
                    "lag": (i - concession_ply) if concession_ply is not None else None,
                    "ctype": ctype, "route_len": len(journey) - 1,
                    "route": "-".join(chess.square_name(s) for s in route)})
        break                          # first sustained outpost per game (v0)
    return out


if __name__ == "__main__":
    n = hits = 0
    rows = []
    with open("/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn",
              encoding="latin-1") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            n += 1
            if n % 10000 == 0:
                print(f"scanned {n}, plans {len(rows)}", flush=True)
            res = game.headers.get("Result", "*")
            if res not in ("1-0", "0-1", "1/2-1/2"):
                continue
            try:
                found = study(game)
            except Exception:
                continue
            for r in found:
                sc = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[res]
                r["score"] = sc if r["attacker"] == "white" else 1.0 - sc
                rows.append(r)

    print(f"\nsustained supported knight outposts: {len(rows)}/{n} games "
          f"({100*len(rows)/n:.1f}%)")
    print(f"occupier score: {statistics.mean(r['score'] for r in rows):.3f}")
    lags = [r["lag"] for r in rows if r["lag"] is not None]
    print(f"median lag concession -> occupation: {statistics.median(lags):.0f} plies")
    print(f"median journey length: {statistics.median(r['route_len'] for r in rows):.0f} knight moves")
    print("\nconcession type:")
    for t, k in collections.Counter(r["ctype"] for r in rows).most_common():
        rs = [r for r in rows if r["ctype"] == t]
        print(f"  {t}: {k} (occupier score {statistics.mean(r['score'] for r in rs):.3f})")
    print("\nby depth (attacker-relative rank of the outpost):")
    for dpt in (3, 4, 5):
        rs = [r for r in rows if r["depth"] == dpt]
        if rs:
            print(f"  rank {dpt + 1}: n={len(rs)} (score "
                  f"{statistics.mean(r['score'] for r in rs):.3f})")
    print("\ntop outpost squares (owner-relative):")
    for s, k in collections.Counter(r["rel_sq"] for r in rows).most_common(12):
        rs = [r for r in rows if r["rel_sq"] == s]
        print(f"  {s}: {k} (score {statistics.mean(r['score'] for r in rs):.3f})")
    print("\nby file class:")
    for label, files in (("rim (a/h)", "ah"), ("b/g", "bg"), ("central (c-f)", "cdef")):
        rs = [r for r in rows if r["rel_sq"][0] in files]
        if rs:
            print(f"  {label}: n={len(rs)} (score "
                  f"{statistics.mean(r['score'] for r in rs):.3f})")
    print("\nmost common final routes:")
    for rt, k in collections.Counter(r["route"] for r in rows).most_common(10):
        print(f"  {rt}: {k}")
    import json
    with open("/Users/avismara/Development/lucena/lucena-plans/experiments/outpost_plans.jsonl",
              "w") as g:
        for r in rows:
            g.write(json.dumps(r) + "\n")
    print("\nwrote experiments/outpost_plans.jsonl")
