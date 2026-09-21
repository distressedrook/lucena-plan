"""Bad-bishop ESCAPE study: when a GM finds themselves with a bad bishop,
what do they do about it — and does it work?

Onset: side has exactly one bishop; >=3 own pawns on its color complex, >=2 of
them rammed; state persists >= PERSIST plies (transients excluded).

Resolutions, first to occur:
  traded    — the bishop leaves the board (recording what it was traded for)
  freed     — the ram structure on its complex dissolves (<2 rams for >=6
              plies) while the bishop lives; recorded who executed the break
  activated — structure still fixed, but the bishop sustains mobility >= 7
              or sits in the enemy half for >= 4 consecutive plies
  stuck     — none of the above before the game ends

Also records the bishop's own move route from onset to resolution (the
maneuver GMs actually play, e.g. the ...Bd7-e8-h5 regroup) and the bad-bishop
side's score per resolution type.
"""
from __future__ import annotations

import collections
import json

import chess
import chess.pgn

PERSIST = 8
FREED_HOLD = 6
ACT_MOB = 7
ACT_HOLD = 4


def sq_color(sq: int) -> bool:
    return bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[sq])


def side_rank(sq: int, side: bool) -> int:
    r = chess.square_rank(sq)
    return r if side == chess.WHITE else 7 - r


def facts(b: chess.Board, side: bool):
    """Per-ply snapshot for one side: (bishop_sq or None, complex, pawns_on_c,
    rams_on_c, mobility, outside) — only when the side has exactly one bishop.
    outside: bishop stands at/in front of its most advanced rammed same-color
    pawn (the 'bad bishop outside the chain' case); False = entombed behind."""
    bs = list(b.pieces(chess.BISHOP, side))
    if len(bs) != 1:
        return None
    sq = bs[0]
    c = sq_color(sq)
    ahead = 8 if side == chess.WHITE else -8
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
    mob = len(b.attacks(sq) & ~b.occupied_co[side])
    outside = fixed == 0 or side_rank(sq, side) >= ram_rank
    return sq, c, total, fixed, mob, outside


def study(game):
    """Returns one record per side that acquired a persistent bad bishop."""
    b = game.board()
    snaps = {chess.WHITE: [], chess.BLACK: []}
    movers, caps, froms, tos, sans = [], [], [], [], []
    for mv in game.mainline_moves():
        movers.append(b.turn)
        sans.append(b.san(mv))
        froms.append(mv.from_square)
        tos.append(mv.to_square)
        cap = b.piece_at(mv.to_square)
        if b.is_en_passant(mv):
            cap = chess.Piece(chess.PAWN, not b.turn)
        caps.append(cap)
        b.push(mv)
        for side in (chess.WHITE, chess.BLACK):
            snaps[side].append(facts(b, side))
    n = len(sans)
    out = []
    for side in (chess.WHITE, chess.BLACK):
        s = snaps[side]
        bad = [x is not None and x[2] >= 3 and x[3] >= 2 for x in s]
        onset = None
        for i in range(n - PERSIST + 1):
            if all(bad[i:i + PERSIST]):
                onset = i
                break
        if onset is None:
            continue
        c = s[onset][1]
        cur = s[onset][0]
        klass = "outside" if s[onset][5] else "entombed"
        route = []
        res, res_ply, detail = "stuck", n - 1, ""
        act_run = free_run = 0
        for t in range(onset + 1, n):
            if movers[t] == side and froms[t] == cur:
                route.append(sans[t])
                cur = tos[t]
            # traded: our bishop was captured
            if movers[t] != side and tos[t] == cur and caps[t] \
                    and caps[t].piece_type == chess.BISHOP:
                res, res_ply = "traded", t
                got = caps[t - 1] if t >= 1 and movers[t - 1] == side and caps[t - 1] \
                    and tos[t - 1] == cur else None
                detail = f"for_{chess.piece_name(got.piece_type)}" if got else "offered"
                break
            if s[t] is None and res == "stuck":
                # bishop gone some other way (e.g. we initiated trade, recapture pending)
                if t + 1 < n and movers[t] == side and caps[t] is not None:
                    res, res_ply = "traded", t
                    detail = f"for_{chess.piece_name(caps[t].piece_type)}"
                else:
                    res, res_ply, detail = "traded", t, "unclear"
                break
            if s[t] is not None:
                free_run = free_run + 1 if s[t][3] < 2 else 0
                if free_run >= FREED_HOLD:
                    res, res_ply = "freed", t - FREED_HOLD + 1
                    k = res_ply
                    detail = "self_break" if movers[k] == side else "opponent_break"
                    break
                act_run = act_run + 1 if (s[t][4] >= ACT_MOB or s[t][5]) else 0
                if act_run >= ACT_HOLD and s[t][3] >= 2:
                    res, res_ply = "activated", t - ACT_HOLD + 1
                    break
        score = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}.get(
            game.headers.get("Result", "*"), None)
        if score is not None and side == chess.BLACK:
            score = 1.0 - score
        out.append({"side": "white" if side == chess.WHITE else "black",
                    "complex": "light" if c else "dark", "class": klass,
                    "onset": onset, "resolution": res, "res_ply": res_ply,
                    "lag": res_ply - onset, "detail": detail,
                    "route": route[:8], "score": score,
                    "white": game.headers.get("White", "?"),
                    "black": game.headers.get("Black", "?"),
                    "event": game.headers.get("Event", "?")})
    return out


if __name__ == "__main__":
    import statistics
    rows, n = [], 0
    with open("/Users/avismara/Projects/active/lucena/lucena-plans/research/data/gm_classical.pgn",
              encoding="latin-1") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            n += 1
            if n % 10000 == 0:
                print(f"scanned {n}, bad-bishop cases {len(rows)}", flush=True)
            try:
                rows.extend(study(game))
            except Exception:
                continue
    with open("/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/bad_bishop_cases.jsonl",
              "w") as g:
        for r in rows:
            g.write(json.dumps(r) + "\n")
    scored = [r for r in rows if r["score"] is not None]
    print(f"\ncases: {len(rows)} (in {n} games)")
    for klass in ("entombed", "outside"):
        ks = [r for r in scored if r["class"] == klass]
        if not ks:
            continue
        print(f"\n== {klass} at onset: {len(ks)} cases, "
              f"bad-side score {statistics.mean(r['score'] for r in ks):.3f} ==")
        print(f"{'resolution':>12} | {'n':>5} | {'share':>6} | {'bad-side score':>14} | {'median lag':>10}")
        for res in ("traded", "freed", "activated", "stuck"):
            rs = [r for r in ks if r["resolution"] == res]
            if not rs:
                continue
            sc = statistics.mean(r["score"] for r in rs)
            lag = statistics.median(r["lag"] for r in rs)
            print(f"{res:>12} | {len(rs):>5} | {100*len(rs)/len(ks):>5.1f}% | {sc:>14.3f} | {lag:>10.0f}")
    ent = [r for r in scored if r["class"] == "entombed"]
    print("\ntrade details (entombed only):")
    for d, k in collections.Counter(r["detail"] for r in ent
                                    if r["resolution"] == "traded").most_common():
        print(f"  {d}: {k}")
    print("\nfreed details (entombed only):")
    for d, k in collections.Counter(r["detail"] for r in ent
                                    if r["resolution"] == "freed").most_common():
        print(f"  {d}: {k}")
    print("\nescape routes of entombed bishops (first 2 bishop moves, any resolution):")
    for rt, k in collections.Counter(tuple(r["route"][:2]) for r in ent
                                     if r["route"]).most_common(12):
        print(f"  {' '.join(rt)}: {k}")
