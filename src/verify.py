#!/usr/bin/env python3
"""verify — close the loop: suggest -> ROLL -> DIFF, per position.

A candidate plan is not trusted because GMs typically play it in this
structure; it is trusted because, rolled forward FROM THIS POSITION, sound
play executes it. Two rolls, one diff:

  ROLL(engine)  MultiPV=4 @ 1M nodes, each line extended to the plan's
                horizon. A candidate is CONFIRMED-SOUND if it appears in an
                EVAL-EQUAL line (|cp - cp_best| <= 50): optimal play here
                executes it.
  ROLL(maia)    K=9 gated rollouts (K* from the k-study; 40-60 policy band).
                A candidate is HUMAN-TYPICAL if it appears in a fraction of
                rolls that beats its random floor (>= 2 hits AND frac >= 2x
                the plan's P(random-per-roll)).
  DIFF          plan_diff.labels() on every rolled line; membership test on
                the candidate's family (side-matched).

TIMING (2026-07-22 ruling): "appears somewhere in the horizon" is not the
same claim as "play it now" — a plan confirmed only at ply 11 of a 14-ply
line requires ten plies of unrelated play first (trades, tactics, a
DIFFERENT piece's journey) before it's even reachable. Presenting that as
undated CONFIRMED-SOUND invites a student to play the move immediately, on
a position that hasn't earned it yet (concrete case: an engine's own best
line plants a bishop on f5 — genuinely CONFIRMED — but only after 10 prior
plies of queen trades and a different bishop's tactical detour through d4;
playing Bf5 on move 1 is simply a different, unexamined position). So every
confirmation carries `lag` (the ply it first fires, in the earliest-firing
equal line), `timing` (immediate <=2 / developing <=6 / long-term >6 plies),
and `immediate_move` (the actual next move of that line — what to play NOW,
which is usually NOT the plan's own characteristic move).

Verdict per candidate: CONFIRMED-SOUND (engine, fires within 2 plies) >
CONFIRMED-SOUND-LATER (engine, fires at ply 3+ — sound but not yet due;
show `immediate_move` instead) > HUMAN-TYPICAL (human) > UNSUPPORTED
(neither) > REFUTED (engine-equal lines exist and NONE contain it AND the
forced-commit roll drops eval > 40cp — the counterfactual).

THE CONTRACT (2026-07-22 ruling): (fen, pvs, rolls). This module NEVER
rolls — it only checks lines. `pvs` are engine MultiPV lines
([{cp, ucis}]; eval-equal semantics per EQUAL_BAND), `rolls` are Maia
gated rollouts (list of UCI lists). Who produced them is the caller's
business: the backend hands in lines from its own engine/Maia access; the
research harness rolls live via research/experiments/tools/rolls.py or reuses the
banked 4,000-position benchmark shards. Either leg may be None (that
backend absent) — verify degrades to the other and says so. Deterministic
given the same lines.
"""
from __future__ import annotations

import json
import sys

import chess

from plan_diff import labels, parse_line

EQUAL_BAND = 50          # |cp - cp_best| <= this -> an equal (sound) line
REFUTE_DROP = 40         # forced-commit eval drop that REFUTES a candidate

# per-family natural horizon (finding 9: harvest/outpost fast, minority/
# passer slow). Default 25.
PLAN_HORIZON = {
    "weakness_harvest": 14, "outpost_occupation": 14, "rook_activation": 14,
    "heavy_battery": 16, "blockade": 16, "chain_base_attack": 16,
    "center_break_vs_king": 16, "remove_defender": 14,
    "minority_attack": 30, "minority_attack_general": 30,
    "passer_creation": 30, "passer_push": 30, "majority_roll": 30,
    "pawn_storm": 20, "king_march": 30, "trade_into_endgame": 20,
    "alternation": 40, "backward_push": 25,
    "free_bad_bishop": 20, "exchange_bad_bishop": 20, "strong_outpost": 18,
    "harvest_overextended": 14, "attack_passer": 16,
    "castle_kingside": 16, "castle_queenside": 16,
    "keep_king_uncastled": 12,   # the rule (2026-07-23, user-defined): the
                                 # king isn't castled in the next 6 MOVES
}
# P(random per single roll), slow regime, from the calibration report.
# The Maia-typical bar; refreshed by the 4,000-position benchmark.
FLOOR_ROLL = {
    "weakness_harvest": 0.05, "outpost_occupation": 0.069,
    "rook_activation": 0.092, "heavy_battery": 0.058, "blockade": 0.041,
    "chain_base_attack": 0.027, "center_break_vs_king": 0.011,
    "remove_defender": 0.005, "minority_attack": 0.007,
    "passer_creation": 0.045, "passer_push": 0.007, "pawn_storm": 0.003,
    "king_march": 0.014, "trade_into_endgame": 0.001, "alternation": 0.001,
    "keep_king_uncastled": 0.25,   # NEGATIVE-event plan (audited 2026-07-23,
                                   # keep_king_uncastled_audit.md); verdict
                                   # uses the pooled-70% rule, floor is data
}
DEFAULT_FLOOR = 0.03


# ---------------------------------------------------------------- diff

import functools


@functools.lru_cache(maxsize=4096)
def _parsed(fen: str, ucis: tuple, horizon: int, tail: int) -> tuple:
    """Cached parse_line(fen, ucis, horizon, tail) as a tuple of plan dicts.
    One banked line gets checked against MANY (family, square) candidates
    per position — without this, each check re-derives the full
    snapshot/delta_stream/parse_line pipeline from scratch (2026-07-22
    finding: this was the dominant cost building fact sheets at corpus
    scale, ~1.5s/position even reusing banked engine/Maia data — 105M
    function calls for 5 positions, almost all redundant re-parsing of
    the SAME lines). `ucis` and the return value are hashable/immutable
    so this is safe to cache process-wide."""
    b = chess.Board(fen)
    mvs = [chess.Move.from_uci(u) for u in ucis]
    return tuple(parse_line(b, mvs, horizon, tail))


def _fam_hit_in_line(fen: str, ucis, family: str, side: str, horizon: int,
                     tail: int, square: str | None = None
                     ) -> tuple[int, str] | None:
    """The (ply, detail) at which this line executes FAMILY for SIDE (and,
    if `square` is given, executes it AT THAT SPECIFIC SQUARE) — or None if
    it never does. The ply, not just a bool: WHEN a plan fires is as load-
    bearing as WHETHER it fires. A plan confirmed only at ply 11 of a
    14-ply line requires ten plies of other, unrelated play first (trades,
    a completely different bishop's journey) — presenting that as an
    undated 'CONFIRMED-SOUND' invites a student to play the move NOW, on
    the wrong position. See verify_plan's 'lag'/'immediate_move' fields.
    The DETAIL is the detector's own specifics (the exact freeing push
    'c6-c5', the battery's file, the outpost square) — 2026-07-22 ruling:
    name the specific pawns/squares the verified lines actually play,
    never the generic plan wording alone."""
    for pl in _parsed(fen, tuple(ucis), horizon, tail):
        if pl["side"] != side or pl["name"] != family:
            continue
        if square is not None:
            squares = {sq.strip() for sq in pl.get("detail", "").split(",")}
            if square not in squares:
                continue
        return pl["ply"], pl.get("detail", "")
    return None


def _fam_ply_in_line(fen: str, ucis, family: str, side: str, horizon: int,
                     tail: int, square: str | None = None) -> int | None:
    hit = _fam_hit_in_line(fen, ucis, family, side, horizon, tail, square)
    return None if hit is None else hit[0]


def _fam_in_line(fen: str, ucis, family: str, side: str, horizon: int,
                 tail: int, square: str | None = None) -> bool:
    """Boolean convenience wrapper over `_fam_ply_in_line` — kept for the
    non-square (labels-based) fast path used by families with no meaningful
    'target square' (e.g. simplification)."""
    if square is None:
        for pl in _parsed(fen, tuple(ucis), horizon, tail):
            if pl["side"] == side and pl["name"] == family:
                return True
        return False
    return _fam_ply_in_line(fen, ucis, family, side, horizon, tail,
                            square) is not None


def _journey(fen: str, ucis: list, side_white: bool, target: int,
             upto: int) -> str | None:
    """The OBSERVED piece journey to `target` inside this line: the square
    path of the (non-pawn, non-king) piece that first lands there,
    reconstructed by chaining its own moves backward from the landing.
    Returns 'f3-e5' / 'd7-b6-d5' style, or None if nothing lands.

    2026-07-22 ruling: the SUGGEST phase proposes routes (geometry); the
    VERIFY phase filters them — what the sheet prints is the journey the
    eval-equal line actually plays, never the skeleton BFS route (which on
    a real position produced d7-b8-a6-b4-d3 while every rolled line played
    something else entirely)."""
    b = chess.Board(fen)
    side_moves: list[chess.Move] = []
    landing = None
    for u in ucis[:upto]:
        m = chess.Move.from_uci(u)
        if b.turn == side_white:
            if m.to_square == target and \
                    b.piece_type_at(m.from_square) not in (
                        None, chess.PAWN, chess.KING):
                landing = m
                break
            side_moves.append(m)
        b.push(m)
    if landing is None:
        return None
    path = [landing.to_square, landing.from_square]
    cur = landing.from_square
    for m in reversed(side_moves):
        if m.to_square == cur:
            cur = m.from_square
            path.append(cur)
    return "-".join(chess.square_name(q) for q in reversed(path))


def _journey_from(fen: str, ucis: list, side_white: bool, start: int,
                  upto: int) -> str | None:
    """FORWARD-tracked journey of the piece standing on `start`: its own
    square path through this line ('e3-d4-c5'), or None if it never moves
    (or is captured before moving). The extraction-plan case (2026-07-22):
    bad_bishop_escape's emitter carries no square, so the observed route
    must come from following the bishop itself through the firing line —
    the geometric BFS exit printed 'e3-g5' on a position whose lines all
    extract via a recapture on d4 (KNOWN_ISSUES #5)."""
    b = chess.Board(fen)
    cur = start
    path = [start]
    for u in ucis[:upto]:
        m = chess.Move.from_uci(u)
        moving_side_white = b.turn
        if m.from_square == cur and moving_side_white == side_white:
            cur = m.to_square
            path.append(cur)
        elif m.to_square == cur and moving_side_white != side_white:
            break                        # the tracked piece was captured
        b.push(m)
    if len(path) < 2:
        return None
    return "-".join(chess.square_name(q) for q in path)


# ---------------------------------------------------------------- verdict

def verify_plan(fen: str, side: str, family: str,
                pvs: list | None, rolls: list | None,
                square: str | None = None,
                route_hops: int | None = None,
                track: str | None = None) -> dict:
    """If `square` is given, the verdict is about THAT square specifically
    (e.g. outpost on d5) — a candidate bundling several holes must call this
    once per hole, never share one verdict across them. A per-square floor
    is tighter than the family floor: it's asking about one target among
    several possible ones, so chance agreement is lower.

    `route_hops`: length of the geometric route to the target (knight
    maneuvers). Real games take CONVOLUTED routes — retreats, back-and-
    forth (user ruling 2026-07-22; a 7-hop journey to b3 is in the corpus)
    — so the horizon scales with the route instead of timing out on plans
    that are being executed slowly: each own hop ~2 plies, x2 slack for
    the wandering, capped at 40.

    `pvs`/`rolls`: the caller's rolled lines — REQUIRED (the contract:
    this function never rolls; user ruling 2026-07-22: 'we don't have to
    use 57s engine roll, this is why I have 4000 positions with this
    data'). Pass None for a leg whose backend is absent; the verdict
    degrades to the other leg. The banked lines are labeled at the
    per-family horizon here (parse_line truncates), so a 25-ply bank
    still verifies a horizon-14 family correctly."""
    horizon = PLAN_HORIZON.get(family, 25)
    if route_hops:
        horizon = min(max(horizon, 4 * route_hops + 6), 40)
    tail = 6 if horizon >= 20 else 2
    floor = FLOOR_ROLL.get(family, DEFAULT_FLOOR)
    if square is not None:
        floor = floor / 3   # rough correction: ~3 plausible squares/family
                            # on average in the families that bundle (holes,
                            # weak pawns); tightens until corpus-calibrated
    r = {"family": family, "side": side, "horizon": horizon, "square": square,
         "verdict": "UNSUPPORTED", "engine": None, "maia": None,
         "lag": None, "timing": None, "immediate_move": None, "details": [],
         "routes": []}

    if family == "keep_king_uncastled":
        # NEGATIVE-event plan (2026-07-23, user-defined): confirmed by the
        # ABSENCE of castling — the side's king isn't castled within the
        # horizon (12 plies = 6 moves) in EVERY eval-equal engine line (one
        # equal line castling means the engine keeps castling on the table,
        # so 'keep it uncastled' is not the endorsed plan). plan_diff has no
        # emitter for a non-event; the lines are walked directly here.
        white = side == "W"

        def _castles_within(ucis) -> bool:
            b0 = chess.Board(fen)
            for u in ucis[:horizon]:
                mv = chess.Move.from_uci(u)
                if b0.turn == white and b0.is_castling(mv):
                    return True
                b0.push(mv)
            return False

        # RULING (2026-07-23, supersedes the audit's engine-only gate): the
        # verdict pools BOTH legs — if the king remains uncastled in more
        # than 70% of lines across the eval-equal engine PVs AND the Maia
        # rollouts together, CONFIRMED-SOUND; otherwise HUMAN-TYPICAL.
        # (Audit context on file: keep_king_uncastled_audit.md — blanket
        # holding is corpus-anti; the pooled bar is the owner's call.)
        held_e = held_m = 0
        equal: list = []
        if pvs is not None:
            cp1 = pvs[0]["cp"] if pvs else 0
            equal = [p for p in pvs if abs(p["cp"] - cp1) <= EQUAL_BAND]
            held_e = sum(1 for p in equal
                         if not _castles_within(p["ucis"]))
            r["engine"] = {"equal_lines": len(equal),
                           "in_equal_line": bool(equal)
                           and held_e == len(equal),
                           "held_lines": held_e}
        if rolls is not None:
            held_m = sum(1 for line in rolls
                         if not _castles_within(line))
            frac_m = held_m / len(rolls) if rolls else 0.0
            r["maia"] = {"hits": held_m, "k": len(rolls),
                         "frac": round(frac_m, 3), "floor": floor,
                         "typical": held_m >= 2 and frac_m >= 2 * floor}
        total = len(equal) + (len(rolls) if rolls is not None else 0)
        if total:
            pooled = (held_e + held_m) / total
            r["pooled_held_frac"] = round(pooled, 3)
            if pooled > 0.70:
                r["verdict"] = "CONFIRMED-SOUND"
                # a standing restraint, in force from move one of the line
                r["lag"], r["timing"] = 0, "immediate"
            else:
                r["verdict"] = "HUMAN-TYPICAL"
        return r

    if pvs is not None:
        cp1 = pvs[0]["cp"] if pvs else 0
        equal = [p for p in pvs if abs(p["cp"] - cp1) <= EQUAL_BAND]
        hits = [_fam_hit_in_line(fen, p["ucis"], family, side, horizon,
                                 tail, square) for p in equal]
        firing = [(h[0], h[1], p) for h, p in zip(hits, equal)
                  if h is not None]
        in_equal = bool(firing)
        r["engine"] = {"equal_lines": len(equal), "in_equal_line": in_equal}
        # Every firing equal line's detector detail (the exact freeing
        # push, file, square...), deduped — the specifics the sheet may
        # name (2026-07-22: 'name the pawns, and only if they appear in
        # the engine lines').
        r["details"] = sorted({d for _, d, _ in firing if d})
        # Observed journeys to the target square, one per firing equal
        # line, deduped but NOT merged — each is a route a distinct
        # engine line actually plays (earliest-firing line first).
        if square is not None and firing:
            tgt = chess.parse_square(square)
            for _ply, _d, line in sorted(firing, key=lambda fp: fp[0]):
                j = _journey(fen, line["ucis"], side == "W", tgt, horizon)
                if j and j not in r["routes"]:
                    r["routes"].append(j)
            r["routes"] = r["routes"][:3]
        elif track is not None and firing:
            # forward-track a named piece (the extraction case: no landing
            # square is known, but the piece's START square is)
            src = chess.parse_square(track)
            for _ply, _d, line in sorted(firing, key=lambda fp: fp[0]):
                j = _journey_from(fen, line["ucis"], side == "W", src,
                                  horizon)
                if j and j not in r["routes"]:
                    r["routes"].append(j)
            r["routes"] = r["routes"][:3]
        if firing:
            # the EARLIEST-firing equal line: the most direct route, and the
            # one whose immediate move is most representative of "play this
            # now" vs "this becomes available after other stuff happens"
            lag, _detail, best_line = min(firing, key=lambda fp: fp[0])
            r["lag"] = lag
            r["timing"] = ("immediate" if lag <= 2 else
                          "developing" if lag <= 6 else "long-term")
            if best_line["ucis"]:
                b0 = chess.Board(fen)
                r["immediate_move"] = b0.san(
                    chess.Move.from_uci(best_line["ucis"][0]))

    if rolls is not None:
        hits = sum(_fam_in_line(fen, line, family, side, horizon, tail, square)
                   for line in rolls)
        frac = hits / len(rolls) if rolls else 0.0
        typical = hits >= 2 and frac >= 2 * floor
        r["maia"] = {"hits": hits, "k": len(rolls), "frac": round(frac, 3),
                     "floor": floor, "typical": typical}

    if r["engine"] and r["engine"]["in_equal_line"]:
        r["verdict"] = ("CONFIRMED-SOUND" if r["timing"] == "immediate"
                        else "CONFIRMED-SOUND-LATER")
    elif r["maia"] and r["maia"]["typical"]:
        r["verdict"] = "HUMAN-TYPICAL"
    elif r["engine"] and r["engine"]["equal_lines"] and \
            not r["engine"]["in_equal_line"] and \
            (not r["maia"] or r["maia"]["hits"] == 0):
        r["verdict"] = "NOT-IN-BEST-LINES"   # weak-negative (confirmation
                                             # is one-sided; true REFUTED
                                             # needs the forced-commit roll)
    return r


if __name__ == "__main__":
    # ./verify.py "FEN" [side] [family] [bank.json]
    # bank.json = {"pvs": [...], "rolls": [...]} (research/experiments/tools/rolls.py
    # produces it). Without a bank, rolls live through the research harness.
    fen = sys.argv[1]
    side = sys.argv[2] if len(sys.argv) > 2 else "W"
    family = sys.argv[3] if len(sys.argv) > 3 else "weakness_harvest"
    if len(sys.argv) > 4:
        bank = json.load(open(sys.argv[4]))
    else:
        import os
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "research", "experiments", "tools"))
        from rolls import roll_both
        bank = roll_both(fen, PLAN_HORIZON.get(family, 25))
    print(json.dumps(verify_plan(fen, side, family,
                                 bank.get("pvs"), bank.get("rolls")),
                     indent=2))
