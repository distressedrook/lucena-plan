"""plan_diff — the snapshot/diff/parse algorithm: name plans from state deltas.

v2 (post four-way audit): the random control showed event-anchored rules
detect chess while state-drift rules detect noise. Every rule is now anchored
to an irreversible event, and drift-born states must HOLD TO WINDOW END.

  snapshot(board)          the state vector S(p) — hashable channels
  delta_stream(A, moves)   per-ply snapshots, mover-attributed
  parse_line(A, moves)     the plan grammar -> named, staged, priced plans
  labels(A, moves)         flat '<side>:<name>[:<stage>]' set

Grammar (specificity status from research/experiments/engine_vs_human_plans.jsonl):
  PASSED the random audit unchanged: weakness_harvest, outpost_occupation,
    bad_bishop_escape/trade, minority_attack(+general)
  TIGHTENED in v2: pawn_storm (target the enemy king, >=3 advances, contact
    depth), seal_to_entomb/entomb (victim free at start, seal is a pawn move,
    holds to end), open_king (attacker's capture/pawn event + a heavy piece
    on the opened lanes)
  NEW in v2: rook_activation, seventh_invasion, king_march,
    passer_creation, passer_push
Prices: corpus-measured where available; NEW rules carry prior guesses
(marked) until their corpus pass runs.
"""
from __future__ import annotations

import sys

import chess

from weaknesses import (weak_pawns, entombed_bishops, exposed_king, is_hole,
                        side_rank, backward_pawns, bad_bishop, sq_color,
                        strong_squares, overextended_pawns)
from structures import classify

QS = {0, 1, 2}
PERSIST = 4   # 2026-07-22 test: was 6; lowered to check whether the
             # 6-ply persistence bar was too strict for outpost_occupation
             # (see research/experiments/persist4_comparison.txt for the audit)
MINORITY_HELD = 8
TAIL = 6      # v3: an event needs >= TAIL observation plies after it to be
              # verifiable; unverifiable-late events are NOT named (random
              # noise clusters late in long windows — the 78%-floor lesson)

PRICES = {
    "outpost_occupation": 8.3, "weakness_harvest": 8.4, "open_king": 6.7,
    "bad_bishop_escape": 6.0, "seal_to_entomb": 4.9, "entomb": 4.9,
    "minority_attack": 4.0, "minority_attack_general": 1.8,
    "bad_bishop_trade": 2.0, "pawn_storm": 2.0,
    # priors, not yet corpus-priced:
    "rook_activation": 3.0, "seventh_invasion": 5.0, "king_march": 3.0,
    "passer_creation": 6.0, "passer_push": 4.0,
    "blockade": 4.0, "pair_acquisition": 2.4,
    # 2026-07-22 ruling (castled vs uncastled): priors until calibrated
    "center_break_vs_king": 5.0, "deny_castling": 5.0,
    "prepared_break": 4.0, "wing_expansion": 2.5,   # priors, audit pending
    "simplification": 2.5,   # cramped trade-down; prior, audit pending
    "storm_launch": 1.0,     # staged storm: launch WITHOUT completion requirement
    # 2026-07-22 breadth pass — v5 corpus audit VERDICTS (94,289 anchors):
    # PRODUCTION (lift fast/slow, CI clear):
    "trade_into_endgame": 6.0,    # 339.5 / 33.5 — highest lift in the book
    "remove_defender": 5.0,       # 7.11 / 5.36
    "chain_base_attack": 5.0,     # 4.30 / 2.88 — Nimzowitsch validated
    "alternation": 6.0,           # 3.00 / 4.52 — finding 7's shuttle is real
    "heavy_battery": 3.5,         # 1.93 / 2.35
    # CANDIDATE-TIER (failed the random audit; kept for tracing only):
    "fix_then_attack": 1.0,       # 1.10 / 1.04 — no discrimination yet
    "rook_lift": 1.0,             # RETIRED as a family (v1 0.91/0.99; v2
                                  # intent-gated STILL 0.91/1.17 — random
                                  # kings get checked by accident at the GM
                                  # rate). The lift is a MECHANISM inside
                                  # attacking plans, not a plan. Trace-only.
    "majority_roll": 1.0,         # 0.91 / 0.63 — ANTI at slow: random lines
                                  # push majorities aimlessly; needs an
                                  # intent gate (the storm lesson)
    "bind_squeeze": 1.0,          # 0.33 / 0.19 — strongly ANTI: refusing
                                  # trades is what RANDOM play does; the GM
                                  # squeeze must be finer than no-trades
    # INCONCLUSIVE (preconditions too rare at these anchors; not refuted):
    "minority_block": 2.0,        # n~=10 at 94k anchors
    "piece_attack": 2.0,          # n~=5
    "castle_kingside": 4.0,       # PRIOR (2026-07-22, user-defined) — get
                                  # the king to safety; audit pending
    "castle_queenside": 4.0,      # same, queenside; audit pending
    "harvest_overextended": 5.0,  # PRIOR (2026-07-22, user-defined) — win
                                  # an enemy pawn advanced past its support
                                  # (Nimzowitsch); audit pending
    "strong_outpost": 5.0,        # PRIOR (2026-07-22, user-defined) —
                                  # knight to a strong square whose only
                                  # challenger is a king-shelter pawn (Ruy
                                  # Nf5); audit pending
    "attack_passer": 3.0,         # 2026-07-22, user-defined — the passer's
                                  # OPPONENT neutralizes it (taken/besieged,
                                  # attacker pieces named); corpus audit
                                  # pending, engine-gated per position
    "free_bad_bishop": 3.0,       # v2 (2026-07-22, user-defined) — push a
                                  # bishop-colored pawn off-color AND the
                                  # bishop actually stops being bad (v1
                                  # bare-push failed at lift 1.02); re-audit
    "exchange_bad_bishop": 3.0,   # PRIOR (2026-07-22, user-defined) — trade
                                  # the bad bishop off, ideally for the
                                  # enemy bishop (knight ok); audit pending
    "backward_push": 3.0,         # GRADUATED (2026-07-22, three-legged
                                  # audit) — the freeing break that
                                  # dissolves the backward pawn (user
                                  # request). Took a v3 SEE preparedness
                                  # gate: v1 bare push 0.99/0.82 (storm
                                  # disease — random shoves the pawn more
                                  # than GMs, who wait), v2 no-net-loss
                                  # gate broke the even liquidation, v3
                                  # (opponent SEE=0 on the stop-square)
                                  # -> corpus lift 1.55 fast [1.40,1.71] /
                                  # 1.36 slow [1.26,1.48], n=20,688
                                  # (full GM corpus). benchmark_v1 (4,000):
                                  # 39% engine-confirm vs 10% floor = 3.9x
                                  # discrimination — production tier
                                  # (between harvest 4.1x and rook 3.7x);
                                  # 39% absolute is the slow-plan signature
                                  # (payoff past the 25-ply horizon, like
                                  # blockade/entomb). Engine endorses the
                                  # break at ~2x the GM in-window rate
                                  # (16.7% vs 8.5%). Engine-CONTRACT gated:
                                  # never surfaced unverified (bare pushes
                                  # ARE random-typical).
    # 2026-07-22 user-ruling pair (priors, audit pending):
    "pair_break": 8.5,            # AUDITED (2026-07-22): widened to N-for-B
                                  # AND B-for-B (pair dies either way, user
                                  # correction) -> lift 15.66 fast / 11.71
                                  # slow, 2nd-strongest family in the book
                                  # (n=26,183; widening STRENGTHENED it,
                                  # did not dilute). Universal openness gate
                                  # (+2-5pp every cell, max at MID).
    "knight_reroute": 3.0,        # thematic multi-hop maneuver to a hole
}


def _minority_pre(b: chess.Board, side: bool) -> bool:
    own = [s for s in b.pieces(chess.PAWN, side) if chess.square_file(s) in QS]
    opp = [s for s in b.pieces(chess.PAWN, not side) if chess.square_file(s) in QS]
    return (len(own) == 2 and not any(chess.square_file(s) == 2 for s in own)
            and len(opp) == 3 and any(chess.square_file(s) == 2 for s in opp))


def _outposts_against(b: chess.Board, victim: bool) -> frozenset:
    out = set()
    for pt in (chess.KNIGHT, chess.BISHOP):
        for sq in b.pieces(pt, not victim):
            if not 2 <= side_rank(sq, victim) <= 4:
                continue
            if not is_hole(b, sq, victim):
                continue
            if any(p and p.piece_type == chess.PAWN and p.color != victim
                   for p in (b.piece_at(a) for a in b.attackers(not victim, sq))):
                out.add(sq)
    return frozenset(out)


def _passers(b: chess.Board, side: bool) -> list[int]:
    enemy = b.pieces(chess.PAWN, not side)
    out = []
    for sq in b.pieces(chess.PAWN, side):
        f, r = chess.square_file(sq), side_rank(sq, side)
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r for s in enemy):
            out.append(sq)
    return out


def _chain_bases(owner_pawns: frozenset, enemy_pawns: frozenset,
                 owner_white: bool) -> set[int]:
    """Bases of the OWNER's pawn chains (Nimzowitsch). A chain: a rammed,
    pawn-defended head plus the diagonal of defenders behind it; the base is
    the rearmost link, itself pawn-undefended — the lever target."""
    ahead = 8 if owner_white else -8
    bases = set()
    for head in owner_pawns:
        front = head + ahead
        if not 0 <= front < 64 or front not in enemy_pawns:
            continue                                   # head must be rammed
        # walk the defender diagonal back from the head
        cur, links = head, 0
        while True:
            defs = [cur - ahead + df for df in (-1, 1)
                    if 0 <= cur - ahead + df < 64
                    and abs(chess.square_file(cur - ahead + df)
                            - chess.square_file(cur)) == 1
                    and (cur - ahead + df) in owner_pawns]
            if not defs:
                break
            cur = defs[0]                              # follow one diagonal
            links += 1
        if links >= 1 and cur != head:
            bases.add(cur)
    return bases


def snapshot(b: chess.Board) -> dict:
    s = {"structures": frozenset(classify(b))}
    pawn_files = {}
    for side, t in ((chess.WHITE, "W"), (chess.BLACK, "B")):
        bp = b.pieces(chess.PAWN, side)
        pawn_files[t] = frozenset(chess.square_file(p) for p in bp)
        pas = _passers(b, side)
        ksq = b.king(side)
        s[f"{t}.weak"] = frozenset(weak_pawns(b, side))
        s[f"{t}.backward"] = frozenset(sq for sq, _ in backward_pawns(b, side))
        s[f"{t}.badbishop"] = frozenset(bad_bishop(b, side))
        s[f"{t}.overext"] = frozenset(overextended_pawns(b, side))
        s[f"{t}.entombed"] = frozenset(entombed_bishops(b, side))
        s[f"{t}.bishops"] = len(b.pieces(chess.BISHOP, side))
        s[f"{t}.exposed"] = exposed_king(b, side)
        s[f"{t}.outposted_by_enemy"] = _outposts_against(b, side)
        s[f"{t}.minority_pre"] = _minority_pre(b, side)
        s[f"{t}.b_rel_rank"] = max((side_rank(p, side) for p in bp
                                    if chess.square_file(p) == 1), default=-1)
        s[f"{t}.q_progress"] = sum(side_rank(p, side) for p in bp
                                   if chess.square_file(p) in QS)
        s[f"{t}.k_progress"] = sum(side_rank(p, side) for p in bp
                                   if chess.square_file(p) >= 5)
        s[f"{t}.q_max"] = max((side_rank(p, side) for p in bp
                               if chess.square_file(p) in QS), default=-1)
        s[f"{t}.q_n"] = sum(1 for p in bp if chess.square_file(p) in QS)
        s[f"{t}.k_n"] = sum(1 for p in bp if chess.square_file(p) >= 5)
        s[f"{t}.free_files"] = 8 - len({chess.square_file(p) for p in bp})
        s[f"{t}.k_max"] = max((side_rank(p, side) for p in bp
                               if chess.square_file(p) >= 5), default=-1)
        s[f"{t}.pawns"] = frozenset(bp)
        s[f"{t}.occ"] = frozenset(chess.SquareSet(b.occupied_co[side]))
        s[f"{t}.bishop_sqs"] = frozenset(b.pieces(chess.BISHOP, side))
        s[f"{t}.rooks"] = frozenset(b.pieces(chess.ROOK, side))
        s[f"{t}.heavies"] = frozenset(b.pieces(chess.ROOK, side)
                                      | b.pieces(chess.QUEEN, side))
        s[f"{t}.king_file"] = chess.square_file(ksq) if ksq is not None else -1
        s[f"{t}.king_rank"] = side_rank(ksq, side) if ksq is not None else -1
        s[f"{t}.castled"] = (ksq is not None and side_rank(ksq, side) == 0
                             and chess.square_file(ksq) not in (3, 4))
        s[f"{t}.can_castle"] = b.has_castling_rights(side)
        s[f"{t}.king_central"] = (ksq is not None
                                  and chess.square_file(ksq) in (3, 4)
                                  and side_rank(ksq, side) == 0)
        s[f"{t}.n_passers"] = len(pas)
        s[f"{t}.passer_max"] = max((side_rank(p, side) for p in pas), default=-1)
        # ---- canon-audit channels (2026-07-22)
        s[f"{t}.knights"] = len(b.pieces(chess.KNIGHT, side))
        s[f"{t}.has_pair"] = s[f"{t}.bishops"] >= 2
        fcount = {}
        for p in bp:
            fcount[chess.square_file(p)] = fcount.get(chess.square_file(p), 0) + 1
        s[f"{t}.doubled"] = sum(1 for v in fcount.values() if v >= 2)
        files = sorted(fcount)
        s[f"{t}.islands"] = sum(1 for i, f in enumerate(files)
                                if i == 0 or f - files[i - 1] > 1)
        s[f"{t}.space"] = sum(side_rank(p, side) - 1 for p in bp)
        s[f"{t}.protected_passer"] = any(
            any(pp and pp.piece_type == chess.PAWN and pp.color == side
                for pp in (b.piece_at(a) for a in b.attackers(side, sq)))
            for sq in pas)
        s[f"{t}.outside_passer"] = any(chess.square_file(sq) in (0, 1, 6, 7)
                                       for sq in pas)
        s[f"{t}.connected_passers"] = any(
            abs(chess.square_file(a) - chess.square_file(c)) == 1
            for a in pas for c in pas if a != c)
        s[f"{t}.central_isolani"] = frozenset(
            sq for sq in bp if chess.square_file(sq) in (3, 4)
            and not any(chess.square_file(q) in (chess.square_file(sq) - 1,
                                                 chess.square_file(sq) + 1)
                        for q in bp if q != sq))
        # ---- breadth-pass channels (2026-07-22)
        s[f"{t}.knight_sqs"] = frozenset(b.pieces(chess.KNIGHT, side))
        s[f"{t}.queens"] = frozenset(b.pieces(chess.QUEEN, side))
        s[f"{t}.npieces"] = len(s[f"{t}.occ"]) - len(bp) - 1   # non-pawn, non-king
        s[f"{t}.passer_files"] = frozenset(chess.square_file(p) for p in pas)
    # blockade squares: t piece standing directly in front of an enemy passer
    # or enemy central isolani (Nimzowitsch's blockader)
    for side, t in ((chess.WHITE, "W"), (chess.BLACK, "B")):
        enemy = not side
        ahead = 8 if enemy == chess.WHITE else -8
        targets = set(_passers(b, enemy)) | set(s[f"{'B' if t == 'W' else 'W'}.central_isolani"])
        blocked = set()
        for sq in targets:
            front = sq + ahead
            if 0 <= front < 64:
                pc = b.piece_at(front)
                if pc and pc.color == side and pc.piece_type != chess.PAWN:
                    blocked.add(front)
        s[f"{t}.blockading"] = frozenset(blocked)
    # king-zone attack mass: count of t's non-pawn pieces within Chebyshev
    # distance 2 of the ENEMY king (the piece-attack channel)
    for side, t in ((chess.WHITE, "W"), (chess.BLACK, "B")):
        ok = b.king(not side)
        n = 0
        if ok is not None:
            for sq in s[f"{t}.occ"] - s[f"{t}.pawns"]:
                if sq == b.king(side):
                    continue
                if chess.square_distance(sq, ok) <= 2:
                    n += 1
        s[f"{t}.attack_pieces"] = n
    s["wf"], s["bf"] = pawn_files["W"], pawn_files["B"]
    s["stm_check"] = b.is_check()          # side-to-move is in check
    return s


def delta_stream(start: chess.Board, moves: list[chess.Move], horizon: int = 40):
    b = start.copy()
    snaps = [(-1, None, snapshot(b))]
    for i, mv in enumerate(moves[:horizon]):
        if mv not in b.legal_moves:
            break
        tag = "W" if b.turn == chess.WHITE else "B"
        b.push(mv)
        snaps.append((i, tag, snapshot(b)))
    return snaps


def _holds_to_end(snaps, k, test) -> bool:
    return all(test(snaps[j][2]) for j in range(k, len(snaps)))


_SEE_VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
            chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 99}


def _see(b: chess.Board, sq: int, side: bool) -> int:
    """Static exchange value `side` can win by initiating captures on `sq`
    (0 if declining is best). Board copies expose x-ray attackers; pins
    and king-capture legality are ignored (the standard approximation)."""
    occ = b.piece_at(sq)
    atts = list(b.attackers(side, sq))
    if occ is None or not atts:
        return 0
    a = min(atts, key=lambda s: _SEE_VAL[b.piece_at(s).piece_type])
    apc = b.piece_at(a)
    b2 = b.copy(stack=False)
    b2.remove_piece_at(sq)
    b2.remove_piece_at(a)
    b2.set_piece_at(sq, apc)
    return max(0, _SEE_VAL[occ.piece_type] - _see(b2, sq, not side))


def parse_line(start: chess.Board, moves: list[chess.Move],
               horizon: int = 40, tail: int = TAIL) -> list[dict]:
    snaps = delta_stream(start, moves, horizon)
    if len(snaps) < 2:
        return []
    s0 = snaps[0][2]
    send = snaps[-1][2]
    plans = []

    def emit(name, side, ply, stage="completed", extra=""):
        plans.append({"name": name, "side": side, "ply": ply, "stage": stage,
                      "price": PRICES.get(name, 0.0), "detail": extra})

    for t, o in (("W", "B"), ("B", "W")):
        # ---- minority attack (unchanged: passed the audit)
        # 2026-07-22 ruling: queenside pawn advances under OPPOSITE castling
        # (their king lives on the queenside, ours does not) are a STORM, not
        # a minority attack — the storm rule owns that case
        opp_castled_q = (snaps[0][2][f"{o}.king_file"] <= 2
                         and snaps[0][2][f"{t}.king_file"] >= 4)
        pre_plies = [] if opp_castled_q else \
            [k for k in range(len(snaps)) if snaps[k][2][f"{t}.minority_pre"]]
        # a COMPLETED lever retroactively validates the precondition: fast
        # executions (b4..bxc6 in under MINORITY_HELD plies) dissolve the 2v3
        # configuration by succeeding — completion waives the persistence bar
        full0 = [sn[f"{t}.b_rel_rank"] for _, _, sn in snaps]
        side_c0 = chess.WHITE if t == "W" else chess.BLACK
        lever_done = False
        for j in range(1, len(snaps)):
            if full0[j] == -1 and full0[j - 1] >= 4:
                mj = moves[snaps[j][0]]
                rel_to = mj.to_square if side_c0 == chess.WHITE else \
                    chess.square(chess.square_file(mj.to_square),
                                 7 - chess.square_rank(mj.to_square))
                if chess.square_name(rel_to) in ("b5", "c6"):
                    lever_done = True
                break
        if pre_plies and (len(pre_plies) >= MINORITY_HELD
                          or (lever_done and pre_plies[0] <= 2)):
            ranks = [snaps[k][2][f"{t}.b_rel_rank"] for k in pre_plies]
            in_carlsbad = any(("carlsbad", t == "W") in snaps[k][2]["structures"]
                              or ("carlsbad", chess.WHITE if t == "W" else chess.BLACK)
                              in snaps[k][2]["structures"] for k in pre_plies)
            name = "minority_attack" if in_carlsbad else "minority_attack_general"
            reached5 = any(r >= 4 for r in ranks)
            full = [sn[f"{t}.b_rel_rank"] for _, _, sn in snaps]
            # v3 lever fix: the b-pawn must vanish IN a capture on rel b5/c6
            # (random lines get their b-pawn eaten anywhere -> false levers)
            side_c = side_c0
            vanished_after5 = lever_done
            enemy_c_weak = any(any(chess.square_file(sq) == 2
                                   for sq in snaps[k][2][f"{o}.weak"])
                               for k in pre_plies)
            if vanished_after5 or (reached5 and enemy_c_weak):
                emit(name, t, pre_plies[-1], "completed")
            elif reached5:
                emit(name, t, pre_plies[-1], "advanced", "lever unresolved")
            elif any(r >= 3 for r in ranks) and ranks[0] < 3:
                emit(name, t, pre_plies[-1], "launched")

        for k in range(1, len(snaps)):
            ply, mover, s = snaps[k]
            p = snaps[k - 1][2]
            mv = moves[ply]
            mover_pawn = mv.to_square in (s[f"{mover}.pawns"] - p[f"{mover}.pawns"]) \
                if mover else False
            was_capture = mv.to_square in p[f"{'B' if mover == 'W' else 'W'}.occ"] \
                if mover else False
            verifiable = k + tail < len(snaps)   # v3: room to observe consequences

            # ---- castle_kingside / castle_queenside (2026-07-22,
            #      user-defined): the king actually castles. Detected by
            #      the king's start/landing squares — the only way a king
            #      moves two files in one move in standard (non-960) chess
            #      — so no live board object is needed here. One-shot,
            #      irreversible, no persistence check required.
            home = chess.E1 if t == "W" else chess.E8
            if mover == t and mv.from_square == home:
                if mv.to_square == (chess.G1 if t == "W" else chess.G8):
                    emit("castle_kingside", t, ply, "completed")
                elif mv.to_square == (chess.C1 if t == "W" else chess.C8):
                    emit("castle_queenside", t, ply, "completed")

            # ---- outpost occupation (unchanged: passed)
            gained = s[f"{o}.outposted_by_enemy"] - p[f"{o}.outposted_by_enemy"]
            if mover == t and gained and verifiable and all(
                    gained <= snaps[j][2][f"{o}.outposted_by_enemy"]
                    for j in range(k, min(k + PERSIST + 1, len(snaps)))):
                emit("outpost_occupation", t, ply, "completed",
                     ",".join(chess.square_name(x) for x in gained))

            # ---- harvest (unchanged: passed)
            lost = p[f"{o}.weak"] - s[f"{o}.weak"]
            if mover == t and lost and mv.to_square in lost:
                emit("weakness_harvest", t, ply, "completed",
                     chess.square_name(mv.to_square))

            # ---- harvest_overextended (2026-07-22, user-defined): win an
            #      enemy OVEREXTENDED pawn (advanced past any support — the
            #      Nimzowitsch target). Same capture event as weakness_
            #      harvest, on the overextended set. The holes such a pawn
            #      left behind it are already surfaced as outpost targets.
            lost_ox = p[f"{o}.overext"] - s[f"{o}.overext"]
            if mover == t and lost_ox and mv.to_square in lost_ox:
                emit("harvest_overextended", t, ply, "completed",
                     chess.square_name(mv.to_square))

            # ---- entomb / seal_to_entomb (TIGHTENED: victim free at start,
            #      seal is a pawn move, entombment holds to window end)
            ent_gain = s[f"{o}.entombed"] - p[f"{o}.entombed"]
            if ent_gain and verifiable and not s0[f"{o}.entombed"] \
                    and _holds_to_end(snaps, k, lambda sn: bool(sn[f"{o}.entombed"])):
                if mover == t and mover_pawn:
                    emit("seal_to_entomb", t, ply, "completed")
                elif mover == o and mover_pawn:
                    emit("entomb", t, ply, "self-inflicted-by-opponent")

            # ---- own bishop escape / trade (unchanged: passed)
            ent_lost = p[f"{t}.entombed"] - s[f"{t}.entombed"]
            if ent_lost and mover == t:
                if s[f"{t}.bishops"] == p[f"{t}.bishops"]:
                    # v3 consequence: the freed bishop must then DO something —
                    # move again within the tail (random frees leave it sitting)
                    if verifiable \
                            and _holds_to_end(snaps, k, lambda sn: not sn[f"{t}.entombed"]) \
                            and any(snaps[j][2][f"{t}.bishop_sqs"]
                                    != snaps[j - 1][2][f"{t}.bishop_sqs"]
                                    and snaps[j][1] == t
                                    for j in range(k + 1, min(k + tail + 3, len(snaps)))):
                        emit("bad_bishop_escape", t, ply)
                else:
                    emit("bad_bishop_trade", t, ply)

            # ---- free_bad_bishop (2026-07-22, user-defined): with a bad
            #      bishop on the board, PUSH one of the bishop's-color pawns
            #      off its color (c6-c5, g6-g5, ...b6 — the moves a player
            #      makes to relieve a bad bishop). Geometry: a pawn PUSH
            #      flips the pawn to the opposite color; a diagonal CAPTURE
            #      keeps it on-color — so the event is a non-capture push of
            #      a bishop-colored pawn. The bishop stays on the board
            #      (freeing, not trading). NOTE (user ruling 2026-07-22): NO
            #      random-floor gate here — random play pushes pawns at the
            #      same rate by nature (v1 lift ~1.0 is EXPECTED for a
            #      move-type plan, not a failure). Validation is engine/Maia
            #      presence when a bad bishop is on the board (16/16 Maia
            #      rollouts, engine PV1/PV3 on the founding position).
            if mover == t and mover_pawn and not was_capture \
                    and p[f"{t}.badbishop"] \
                    and s[f"{t}.bishops"] == p[f"{t}.bishops"]:
                # 2 bad bishops are now possible (pair-exemption dropped,
                # 2026-07-22) — check the pushed pawn's color against
                # EVERY flagged bad bishop, not an arbitrary one via
                # next(iter()) (that silently missed the case where a
                # push frees bishop #2 but iteration order picked #1).
                from_color = sq_color(mv.from_square)
                if any(sq_color(bbsq) == from_color
                      for bbsq in p[f"{t}.badbishop"]):
                    emit("free_bad_bishop", t, ply, "completed",
                         f"{chess.square_name(mv.from_square)}-"
                         f"{chess.square_name(mv.to_square)}")

            # ---- exchange_bad_bishop (2026-07-22 v2, user refinement):
            #      NOT just "t's bad bishop leaves the board" — the plan is
            #      specifically to exchange the bad bishop FOR THE
            #      OPPONENT'S GOOD BISHOP. v1 counted any trade (knight ok,
            #      any bishop ok); user ruling narrowed it: only counts
            #      when o loses a bishop that was GOOD (not itself bad) at
            #      the window's start, AND o's total bishop count actually
            #      drops (excludes the false-positive of the bishop merely
            #      relocating — moving changes which square is in
            #      bishop_sqs without changing the count, so requiring both
            #      together is what distinguishes captured from moved).
            #      SAME COLOR required (2026-07-22 correction): a bishop
            #      is color-locked for life, so it can only ever directly
            #      trade with a same-colored enemy bishop — an opposite-
            #      colored "good bishop" can never be the one t's bad
            #      bishop actually captures or gets captured by.
            #      No random-floor gate (user ruling, unchanged from v1):
            #      trading a piece is a common move type; validation is
            #      engine/Maia presence with a bad bishop on the board.
            bb_gone = p[f"{t}.badbishop"] \
                and s[f"{t}.bishops"] < p[f"{t}.bishops"] \
                and not (p[f"{t}.badbishop"] & s[f"{t}.bishop_sqs"])
            if bb_gone and verifiable \
                    and _holds_to_end(snaps, k,
                                      lambda sn: sn[f"{t}.bishops"]
                                      < p[f"{t}.bishops"]):
                lo = max(0, k - 2)
                hi = min(k + 3, len(snaps))
                p_lo = snaps[lo][2]
                departed_colors = {sq_color(bbsq) for bbsq in
                                   p[f"{t}.badbishop"] - s[f"{t}.bishop_sqs"]}
                good_o_before = {gsq for gsq in
                                 p_lo[f"{o}.bishop_sqs"] - p_lo[f"{o}.badbishop"]
                                 if sq_color(gsq) in departed_colors}
                ob0 = p_lo[f"{o}.bishops"]
                obw = min(snaps[j][2][f"{o}.bishops"] for j in range(lo, hi))
                lost_good = any(
                    gsq not in snaps[j][2][f"{o}.bishop_sqs"]
                    for gsq in good_o_before for j in range(lo, hi))
                if good_o_before and lost_good and obw < ob0:
                    emit("exchange_bad_bishop", t, ply, "completed")

            # ---- open_king (TIGHTENED: attacker's capture/pawn event flips
            #      it, holds to end, and a heavy piece stands on a lane file)
            if mover == t and verifiable \
                    and s[f"{o}.exposed"] and not p[f"{o}.exposed"] \
                    and (was_capture or mover_pawn) \
                    and _holds_to_end(snaps, k, lambda sn: sn[f"{o}.exposed"]):
                kf = s[f"{o}.king_file"]
                lanes = {kf - 1, kf, kf + 1}
                if any(chess.square_file(h) in lanes
                       for h in send[f"{t}.heavies"]):
                    emit("open_king", t, ply, "completed")

            # ---- NEW: rook to open/semi-open file (event: rook lands there;
            #      persistence: a rook of t still on that file at window end)
            rgain = s[f"{t}.rooks"] - p[f"{t}.rooks"]
            if mover == t and rgain and verifiable:
                side_c = chess.WHITE if t == "W" else chess.BLACK
                for rsq in rgain:
                    f = chess.square_file(rsq)
                    own_f, opp_f = (s["wf"], s["bf"]) if t == "W" else (s["bf"], s["wf"])
                    if f in own_f:
                        continue
                    if f == chess.square_file(mv.from_square):
                        continue          # slid along the same file
                    # v3.1 USE, not presence: random rooks stay by inertia, so
                    # occupation alone is noise. The rook must WORK the file:
                    # penetrate to rel rank >= 5 on it, capture on it, or a
                    # second heavy piece joins it (doubling) within the tail.
                    stays = all(
                        any(chess.square_file(r2) == f
                            for r2 in snaps[j][2][f"{t}.rooks"])
                        and f not in (snaps[j][2]["wf"] if t == "W"
                                      else snaps[j][2]["bf"])
                        for j in range(k, min(k + tail + 1, len(snaps))))
                    used = False
                    if stays:
                        for j in range(k, min(k + tail + 4, len(snaps))):
                            sj = snaps[j][2]
                            if any(chess.square_file(h) == f
                                   and side_rank(h, side_c) >= 4
                                   for h in sj[f"{t}.heavies"]):
                                used = True
                                break
                            if sum(1 for h in sj[f"{t}.heavies"]
                                   if chess.square_file(h) == f) >= 2:
                                used = True
                                break
                            if snaps[j][1] == t and j > k \
                                    and chess.square_file(moves[snaps[j][0]].to_square) == f \
                                    and moves[snaps[j][0]].to_square in \
                                    snaps[j - 1][2][f"{o}.occ"]:
                                used = True
                                break
                    if stays and used:
                        kind = "open" if f not in opp_f else "semi"
                        emit("rook_activation", t, ply, "completed",
                             f"{chess.FILE_NAMES[f]}-file:{kind}")
                # ---- 7th-rank invasion (v3: must HOLD the rank for the tail)
                for rsq in rgain:
                    if side_rank(rsq, side_c) >= 6 and all(
                            any(side_rank(r2, side_c) >= 6
                                for r2 in snaps[j][2][f"{t}.rooks"])
                            for j in range(k, min(k + tail + 1, len(snaps)))):
                        emit("seventh_invasion", t, ply, "completed",
                             chess.square_name(rsq))

            # ---- RULING: punish the uncastled king (own king castled, theirs
            #      central). Two plans, both event-anchored.
            if s[f"{t}.castled"] and (p[f"{o}.king_central"]
                                      or p[f"{o}.can_castle"]):
                # (a) center break: t's c-f pawn strikes at rel rank >= 4
                #     (capture, or advance creating contact) while the enemy
                #     king is still central; consequence: a d/e file is
                #     pawn-openable for t within the tail
                if mover == t and mover_pawn and verifiable \
                        and 2 <= chess.square_file(mv.to_square) <= 5 \
                        and side_rank(mv.to_square,
                                      chess.WHITE if t == "W" else chess.BLACK) >= 4 \
                        and was_capture and p[f"{o}.king_central"]:
                    own_f = "wf" if t == "W" else "bf"
                    if any(f not in snaps[min(k + tail, len(snaps) - 1)][2][own_f]
                           for f in (3, 4)):
                        emit("center_break_vs_king", t, ply, "completed")
                # (b) deny castling — FORCED only (v2 after 0.39 anti-lift:
                #     random kings shed rights freely; the plan is rights
                #     lost UNDER COMPULSION): the rights-losing move was made
                #     while in check, or we captured the castling rook
                lost_rights = p[f"{o}.can_castle"] and not s[f"{o}.can_castle"] \
                    and not s[f"{o}.castled"]
                forced = (mover == o and p["stm_check"]) or \
                         (mover == t and was_capture
                          and len(s[f"{o}.rooks"]) < len(p[f"{o}.rooks"]))
                if lost_rights and forced and verifiable \
                        and _holds_to_end(snaps, k,
                                          lambda sn: not sn[f"{o}.castled"]):
                    emit("deny_castling", t, ply, "completed")

            # ---- prepared_break: a Kmoch lever EXECUTES (contact-creating
            #      pawn advance, or capture of a rammed pawn) and the board
            #      opens for the breaker: own-free file count rises and holds
            if mover == t and mover_pawn and verifiable:
                side_b = chess.WHITE if t == "W" else chess.BLACK
                ahead_b = 8 if side_b == chess.WHITE else -8
                to = mv.to_square
                contact = (not was_capture and any(
                    0 <= to + ahead_b + df < 64
                    and abs(chess.square_file(to + ahead_b + df)
                            - chess.square_file(to)) == 1
                    and (to + ahead_b + df) in s[f"{o}.pawns"]
                    for df in (-1, 1)))
                ram_capture = (was_capture and to in p[f"{o}.pawns"]
                               and 0 <= to - ahead_b < 64
                               and (to - ahead_b) in p[f"{t}.pawns"])
                if contact or ram_capture:
                    end_j = min(k + tail, len(snaps) - 1)
                    if snaps[end_j][2][f"{t}.free_files"] > p[f"{t}.free_files"] \
                            and _holds_to_end(
                                snaps, end_j,
                                lambda sn, base=p[f"{t}.free_files"]:
                                sn[f"{t}.free_files"] > base):
                        emit("prepared_break", t, ply, "completed",
                             chess.square_name(to))

            # ---- NEW: blockade (Nimzowitsch) — a piece lands on the square
            #      in front of an enemy passer/central isolani and SITS
            bgain = s[f"{t}.blockading"] - p[f"{t}.blockading"]
            if mover == t and bgain and verifiable and all(
                    bgain & snaps[j][2][f"{t}.blockading"]
                    for j in range(k, min(k + tail + 1, len(snaps)))):
                emit("blockade", t, ply, "completed",
                     ",".join(chess.square_name(x) for x in bgain))

            # ---- NEW: pair acquisition — t captures a minor, ends with the
            #      bishop pair vs no pair (winning the two bishops)
            if mover == t and was_capture and verifiable \
                    and s[f"{t}.has_pair"] and not s[f"{o}.has_pair"] \
                    and not (p[f"{t}.has_pair"] and not p[f"{o}.has_pair"]) \
                    and _holds_to_end(snaps, k, lambda sn: sn[f"{t}.has_pair"]
                                      and not sn[f"{o}.has_pair"]):
                emit("pair_acquisition", t, ply, "completed")

            # ---- passer creation (v3: survives the tail AND shows intent —
            #      it advances, or was born already deep)
            if mover == t and verifiable \
                    and s[f"{t}.n_passers"] > p[f"{t}.n_passers"] \
                    and all(snaps[j][2][f"{t}.n_passers"] > 0
                            for j in range(k, min(k + tail + 1, len(snaps)))):
                advanced = any(snaps[j][2][f"{t}.passer_max"]
                               > snaps[j - 1][2][f"{t}.passer_max"]
                               and snaps[j][1] == t
                               for j in range(k + 1, len(snaps)))
                if advanced or s[f"{t}.passer_max"] >= 4:
                    emit("passer_creation", t, ply, "completed")
            # ---- passer push (an existing passer reaches 6th+; holds tail)
            if mover == t and verifiable \
                    and s[f"{t}.passer_max"] >= 5 > p[f"{t}.passer_max"] >= 0 \
                    and all(snaps[j][2][f"{t}.passer_max"] >= 5
                            for j in range(k, min(k + tail + 1, len(snaps)))):
                emit("passer_push", t, ply, "completed")

            # ================= 2026-07-22 breadth pass =================
            side_t = chess.WHITE if t == "W" else chess.BLACK
            ahead_t = 8 if side_t == chess.WHITE else -8

            # ---- chain_base_attack (Nimzowitsch): t's pawn move creates
            #      lever contact on the BASE of o's chain; consequence: the
            #      base pawn is gone or weak by window end
            if mover == t and mover_pawn and verifiable:
                bases = _chain_bases(p[f"{o}.pawns"], p[f"{t}.pawns"],
                                     side_t == chess.BLACK)
                to = mv.to_square
                hits = {to + ahead_t + df for df in (-1, 1)
                        if 0 <= to + ahead_t + df < 64
                        and abs(chess.square_file(to + ahead_t + df)
                                - chess.square_file(to)) == 1}
                struck = bases & hits
                if struck:
                    base = next(iter(struck))
                    if base not in send[f"{o}.pawns"] \
                            or base in send[f"{o}.weak"]:
                        emit("chain_base_attack", t, ply, "completed",
                             chess.square_name(base))

            # ---- fix_then_attack (a4-a5 vs b6): t's pawn advance takes
            #      CONTROL of the advance square of an o weak pawn, freezing
            #      it; completed if t later captures it, "fixed" if it stays
            #      weak (and frozen) to window end
            if mover == t and mover_pawn and not was_capture and verifiable:
                to = mv.to_square
                ctrl = {to + ahead_t + df for df in (-1, 1)
                        if 0 <= to + ahead_t + df < 64
                        and abs(chess.square_file(to + ahead_t + df)
                                - chess.square_file(to)) == 1}
                for wsq in s[f"{o}.weak"]:
                    adv = wsq - ahead_t          # o advances opposite to t
                    if adv not in ctrl:
                        continue
                    took = any(
                        snaps[j][1] == t
                        and moves[snaps[j][0]].to_square == wsq
                        and wsq in snaps[j - 1][2][f"{o}.pawns"]
                        for j in range(k + 1, len(snaps)))
                    if took:
                        emit("fix_then_attack", t, ply, "completed",
                             chess.square_name(wsq))
                    elif _holds_to_end(snaps, k,
                                       lambda sn, q=wsq: q in sn[f"{o}.weak"]):
                        emit("fix_then_attack", t, ply, "fixed",
                             chess.square_name(wsq))
                    break

            # ---- rook_lift v2 — LIFT WITH INTENT (2026-07-22 ruling; v1 at
            #      0.91/0.99 was chance: random rooks wander to rank 3 too).
            #      Anchor: vertical rise from the back ranks to rel rank 3/4.
            #      Swing: a t rook reaches the enemy-king zone files.
            #      INTENT: the swing must be followed by an attack event —
            #      a check by t, a t capture within distance 2 of the o king,
            #      or t's king-zone attack mass reaching 2+ having risen.
            if mover == t and verifiable and p[f"{o}.castled"]:
                rg = s[f"{t}.rooks"] - p[f"{t}.rooks"]
                for rsq in rg:
                    if not (2 <= side_rank(rsq, side_t) <= 3):
                        continue
                    if side_rank(mv.from_square, side_t) > 1:
                        continue
                    if chess.square_file(mv.from_square) != chess.square_file(rsq):
                        continue                       # vertical lift only
                    okf_ = s[f"{o}.king_file"]
                    zone = {okf_ - 1, okf_, okf_ + 1}
                    end_scan = min(k + tail + 7, len(snaps))
                    swung_at = None
                    for j in range(k + 1, min(k + tail + 5, len(snaps))):
                        if any(chess.square_file(r2) in zone
                               and 2 <= side_rank(r2, side_t) <= 4
                               for r2 in snaps[j][2][f"{t}.rooks"]):
                            swung_at = j
                            break
                    if swung_at is None or not any(
                            chess.square_file(h) in zone
                            for h in send[f"{t}.heavies"]):
                        continue
                    intent = False
                    base_mass = snaps[k - 1][2][f"{t}.attack_pieces"]
                    for j in range(swung_at, end_scan):
                        sj = snaps[j][2]
                        if snaps[j][1] != t:
                            continue
                        if sj["stm_check"]:            # t just gave check
                            intent = True
                            break
                        mj = moves[snaps[j][0]]
                        okf_j = sj[f"{o}.king_file"]
                        okr_j = sj[f"{o}.king_rank"]
                        if okf_j >= 0 and okr_j >= 0:
                            oksq = chess.square(
                                okf_j, okr_j if o == "W" else 7 - okr_j)
                            if mj.to_square in snaps[j - 1][2][f"{o}.occ"] \
                                    and chess.square_distance(
                                        mj.to_square, oksq) <= 2:
                                intent = True          # capture in the zone
                                break
                        if sj[f"{t}.attack_pieces"] >= 2 > base_mass:
                            intent = True              # attack mass built up
                            break
                    if intent:
                        emit("rook_lift", t, ply, "completed",
                             chess.square_name(rsq))

            # ---- heavy_battery: a second t heavy lands on an open/semi-open
            #      file (doubling); the battery holds for the tail and has a
            #      target (o pawn on the file, or the o king's file)
            if mover == t and verifiable:
                hg = s[f"{t}.heavies"] - p[f"{t}.heavies"]
                for hsq in hg:
                    f = chess.square_file(hsq)
                    own_f = s["wf"] if t == "W" else s["bf"]
                    if f in own_f:
                        continue
                    if sum(1 for h in s[f"{t}.heavies"]
                           if chess.square_file(h) == f) < 2:
                        continue
                    if sum(1 for h in p[f"{t}.heavies"]
                           if chess.square_file(h) == f) >= 2:
                        continue                       # was already doubled
                    holds = all(
                        sum(1 for h in snaps[j][2][f"{t}.heavies"]
                            if chess.square_file(h) == f) >= 2
                        for j in range(k, min(k + tail + 1, len(snaps))))
                    opp_f = s["bf"] if t == "W" else s["wf"]
                    target = f in opp_f or s[f"{o}.king_file"] == f
                    if holds and target:
                        emit("heavy_battery", t, ply, "completed",
                             f"{chess.FILE_NAMES[f]}-file")
                        break

            # ---- trade_into_endgame: t captures the queen while holding a
            #      standing endgame asset; queens stay off and trading
            #      continues (piece count falls further by window end)
            if mover == t and was_capture and verifiable \
                    and mv.to_square in p[f"{o}.queens"]:
                asset = (p[f"{t}.n_passers"] > p[f"{o}.n_passers"]
                         or len(p[f"{o}.weak"]) - len(p[f"{t}.weak"]) >= 2
                         or (p[f"{t}.has_pair"] and not p[f"{o}.has_pair"]))
                q_off = _holds_to_end(
                    snaps, k, lambda sn: not sn[f"{t}.queens"]
                    and not sn[f"{o}.queens"])
                further = (send[f"{t}.npieces"] + send[f"{o}.npieces"]
                           <= s[f"{t}.npieces"] + s[f"{o}.npieces"] - 2)
                if asset and q_off and further:
                    emit("trade_into_endgame", t, ply, "completed")

            # ---- remove_defender: t wins o's FIANCHETTO bishop beside its
            #      castled king; o never re-covers that color complex
            if mover == t and was_capture and verifiable \
                    and mv.to_square in p[f"{o}.bishop_sqs"]:
                side_o = not side_t
                fian_k = chess.square(6, 1 if side_o == chess.WHITE else 6)
                fian_q = chess.square(1, 1 if side_o == chess.WHITE else 6)
                okf_ = p[f"{o}.king_file"]
                hit = (mv.to_square == fian_k and okf_ >= 5) \
                    or (mv.to_square == fian_q and okf_ <= 2)
                if hit:
                    par = (chess.square_file(mv.to_square)
                           + chess.square_rank(mv.to_square)) % 2
                    if _holds_to_end(
                            snaps, k,
                            lambda sn, pr=par: not any(
                                (chess.square_file(x) + chess.square_rank(x))
                                % 2 == pr
                                for x in sn[f"{o}.bishop_sqs"])):
                        emit("remove_defender", t, ply, "completed",
                             chess.square_name(mv.to_square))

            # ---- minority_block (the DEFENSE): o is the minority attacker;
            #      t rams o's advancing a/b-pawn; the attack is frozen —
            #      o's b-pawn never advances further through window end
            if mover == t and mover_pawn and verifiable \
                    and p[f"{o}.minority_pre"]:
                bfl = chess.square_file(mv.to_square)
                ahead_o = -ahead_t
                behind = mv.to_square + ahead_o
                if bfl in (0, 1) and 0 <= behind < 64 \
                        and behind in s[f"{o}.pawns"]:
                    lvl = s[f"{o}.b_rel_rank"]
                    if _holds_to_end(
                            snaps, k,
                            lambda sn, L=lvl: -1 < sn[f"{o}.b_rel_rank"] <= L):
                        emit("minority_block", t, ply, "completed",
                             chess.square_name(mv.to_square))

            # ---- pair_break (2026-07-22, user ruling): the side FACING the
            #      enemy bishop pair strives to exchange knights for bishops
            #      — otherwise, in the wrong structure, they are strategically
            #      lost. Two shapes:
            #      (a) direct: t's MINOR (knight or own bishop — the pair
            #          dies however the trade happens; user correction
            #          2026-07-22) captures an o bishop, destroying the pair;
            #      (b) provoked (the classic outpost-offer, e.g. ...Nf4):
            #          o's bishop captures t's minor and t's recapture
            #          removes that bishop — t offered the piece to force
            #          the trade.
            #      Gate: t must be the pair-less side. Openness NOT gated
            #      here — the corpus study cells it (finding 6 says the pair
            #      premium is largest PAWN-FULL, the folklore says exchange
            #      when OPEN; let the data pick the gate).
            if verifiable and not p[f"{t}.has_pair"]:
                pair_lost = p[f"{o}.has_pair"] and not s[f"{o}.has_pair"]
                from_n = mv.from_square in p[f"{t}.knight_sqs"]
                from_b = mv.from_square in p[f"{t}.bishop_sqs"]
                if pair_lost and mover == t and was_capture \
                        and mv.to_square in p[f"{o}.bishop_sqs"] \
                        and (from_n or from_b) \
                        and _holds_to_end(snaps, k,
                                          lambda sn: not sn[f"{o}.has_pair"]):
                    emit("pair_break", t, ply, "completed",
                         f"{'NxB' if from_n else 'BxB'}@"
                         f"{chess.square_name(mv.to_square)}")
                elif pair_lost and mover == t and was_capture and k >= 2 \
                        and mv.to_square in p[f"{o}.bishop_sqs"] \
                        and _holds_to_end(snaps, k,
                                          lambda sn: not sn[f"{o}.has_pair"]):
                    # was the bishop t just captured itself capturing a t
                    # minor on this square one ply earlier? -> the offer
                    prev2 = snaps[k - 2][2]
                    off_n = mv.to_square in prev2[f"{t}.knight_sqs"]
                    off_b = mv.to_square in prev2[f"{t}.bishop_sqs"]
                    if (off_n or off_b) and snaps[k - 1][1] == o:
                        emit("pair_break", t, ply, "provoked",
                             f"{'N' if off_n else 'B'}-offer@"
                             f"{chess.square_name(mv.to_square)}")

            # ---- backward_push (2026-07-22 user request): the classic CURE
            #      for the backward pawn — advance it to dissolve the
            #      weakness (the freeing break: ...d5 in the Sicilian, ...e5
            #      in the KID exchange, c4 in the Carlsbad). Event: t pushes
            #      a pawn that stood in t's backward_half_open set. Result:
            #      t's backward count DROPS and stays dropped to window end
            #      — dissolved, not relocated (a push that leaves the pawn
            #      backward one square on doesn't count) and not merely
            #      swapped for a new backward neighbor. The pawn trading
            #      itself off after the push also qualifies (dissolution by
            #      liquidation — the textbook line).
            #      (rule lives in the post-loop board-replay block — the
            #      v3 preparedness gate needs attack counts, which aren't
            #      snapshot channels; see backward_push below)

            # ---- piece_attack: t's non-pawn pieces mass on the o king zone
            #      (3+ within distance 2), hold the mass for the tail, with
            #      NO pawn storm on that wing (pieces, not pawns, attack)
            if mover == t and not mover_pawn and verifiable \
                    and p[f"{o}.castled"] \
                    and s[f"{t}.attack_pieces"] >= 3 > p[f"{t}.attack_pieces"] \
                    and all(snaps[j][2][f"{t}.attack_pieces"] >= 3
                            for j in range(k, min(k + tail + 1, len(snaps)))):
                okf_ = p[f"{o}.king_file"]
                wing_ = "k" if okf_ >= 5 else ("q" if okf_ <= 2 else None)
                storm_prog = (send[f"{t}.{wing_}_progress"]
                              - s0[f"{t}.{wing_}_progress"]) if wing_ else 0
                if storm_prog < 2:
                    emit("piece_attack", t, ply, "completed")

        # ---- alternation (two weaknesses, finding 7's conversion layer):
        #      t harvests weak targets on fronts >= 4 files apart — the
        #      shuttle that beats accurate defense
        h_files = []
        for k in range(1, len(snaps)):
            ply_k, mover_k, s_k = snaps[k]
            if mover_k != t:
                continue
            mvk = moves[ply_k]
            pk = snaps[k - 1][2]
            if mvk.to_square in pk[f"{o}.weak"]:
                h_files.append((chess.square_file(mvk.to_square), ply_k))
        for i in range(len(h_files)):
            for j2 in range(i + 1, len(h_files)):
                if abs(h_files[i][0] - h_files[j2][0]) >= 4:
                    emit("alternation", t, h_files[j2][1], "completed",
                         f"files {chess.FILE_NAMES[h_files[i][0]]}"
                         f"+{chess.FILE_NAMES[h_files[j2][0]]}")
                    break
            else:
                continue
            break

        # ---- majority_roll: t holds a wing pawn majority at window start
        #      and mobilizes it (>= 3 ranks of progress); completed when a
        #      passer materializes on that wing
        for wing_m, files_m in (("q", (0, 1, 2)), ("k", (5, 6, 7))):
            if not (s0[f"{t}.{wing_m}_n"] > s0[f"{o}.{wing_m}_n"] >= 1):
                continue
            prog_m = (send[f"{t}.{wing_m}_progress"]
                      - s0[f"{t}.{wing_m}_progress"])
            if prog_m < 3:
                continue
            born = (set(send[f"{t}.passer_files"]) & set(files_m)) \
                - set(s0[f"{t}.passer_files"])
            if born:
                emit("majority_roll", t, snaps[-1][0], "completed",
                     wing_m + "-side")
            else:
                emit("majority_roll", t, snaps[-1][0], "launched",
                     wing_m + "-side")

        # ---- bind_squeeze: the space side's plan (the dual of
        #      simplification): starts >= +4 space, grows the bind by >= 3,
        #      initiates NO piece trades all window, never lets it slip
        d0 = s0[f"{t}.space"] - s0[f"{o}.space"]
        if d0 >= 4 and (send[f"{t}.space"] - send[f"{o}.space"]) >= d0 + 3:
            traded = any(
                snaps[k][1] == t
                and moves[snaps[k][0]].to_square
                in (snaps[k - 1][2][f"{o}.occ"] - snaps[k - 1][2][f"{o}.pawns"])
                for k in range(1, len(snaps)))
            slipped = any(
                snaps[k][2][f"{t}.space"] - snaps[k][2][f"{o}.space"] < d0
                for k in range(1, len(snaps)))
            if not traded and not slipped:
                emit("bind_squeeze", t, snaps[-1][0], "completed",
                     f"+{d0}->+{send[f'{t}.space'] - send[f'{o}.space']}")

        # ---- NEW: king march (endgame activation: king reaches its 4th+
        #      rank, net gain >= 2, and stays advanced at window end)
        kr0 = s0[f"{t}.king_rank"]
        kre = send[f"{t}.king_rank"]
        if kre >= 3 and kre - kr0 >= 2:
            emit("king_march", t, snaps[-1][0], "completed", f"rank{kre + 1}")

        # ---- pawn_storm (TIGHTENED: aimed at the enemy king's wing, >= 3
        #      ranks of progress, reaching contact depth rank 5+)
        # v4 intent gate: a storm is a plan only when the enemy king lives on
        # the stormed wing AND our own king does NOT (opposite-castling logic
        # from the canon audit) — random walks fail this gate
        # v5 PER-FAMILY ANCHOR (2026-07-22, the KING ATTACK fix): the storm
        # window opens at the ply the VICTIM'S king settles into its castled
        # address, not at window start — full-game parses previously computed
        # wing from the move-1 uncastled king (wing=None, rule dead).
        # Backward-compatible: victim already castled at window start -> the
        # anchor is ply 0 and semantics are unchanged.
        k_c = next((k for k in range(len(snaps))
                    if snaps[k][2][f"{o}.castled"]), None)
        if k_c is not None and len(snaps) - k_c >= 12:
            base = snaps[k_c][2]
            okf = base[f"{o}.king_file"]
            skf = base[f"{t}.king_file"]
            wing = "k" if okf >= 5 else ("q" if okf <= 2 else None)
            own_on_wing = (wing == "k" and skf >= 5) or (wing == "q" and skf <= 2)
            if wing and not own_on_wing:
                prog = send[f"{t}.{wing}_progress"] - base[f"{t}.{wing}_progress"]
                if prog >= 4 and send[f"{t}.{wing}_max"] >= 4:
                    emit("pawn_storm", t, snaps[-1][0], "completed", wing)
                # staged: LAUNCH — >= 2 ranks of progress toward the enemy
                # king, deliberately WITHOUT completion/consequence
                # requirements, so refuted and deterred storms enter every
                # sample (2026-07-22: completion-conditioning made the maxim
                # untestable)
                if prog >= 2:
                    emit("storm_launch", t, snaps[-1][0], "launched", wing)
        # ---- wing_expansion: space-gaining crab on a wing NOT hosting the
        #      enemy king (storm owns that case): >=3 progress, no pawn
        #      losses there, ends with a clear space lead on that wing
        okf_we = s0[f"{o}.king_file"]
        for wing in ("q", "k"):
            host = (okf_we >= 5 and wing == "k") or (okf_we <= 2 and wing == "q")
            if host:
                continue
            prog = send[f"{t}.{wing}_progress"] - s0[f"{t}.{wing}_progress"]
            if prog >= 3 and send[f"{t}.{wing}_n"] >= s0[f"{t}.{wing}_n"] \
                    and send[f"{t}.{wing}_max"] >= 4 \
                    and send[f"{t}.{wing}_progress"] \
                        - send[f"{o}.{wing}_progress"] >= 3:
                emit("wing_expansion", t, snaps[-1][0], "completed", wing)

    # ---- simplification: the CRAMPED side initiates >= 2 piece trades
    #      (a trade-down campaign). Gate: space differential <= -4 at window
    #      start (the situational precondition, per the 2026-07-22 ruling).
    for t, o in (("W", "B"), ("B", "W")):
        if s0[f"{t}.space"] - s0[f"{o}.space"] > -4:
            continue
        initiated = []
        for k in range(1, len(snaps)):
            ply, mover, s_k = snaps[k]
            if mover != t:
                continue
            mvk = moves[ply]
            pk = snaps[k - 1][2]
            if mvk.to_square in pk[f"{o}.occ"] \
                    and mvk.to_square not in pk[f"{o}.pawns"]:
                initiated.append(ply)
        if len(initiated) >= 2 and initiated[0] + tail < len(snaps):
            plans.append({"name": "simplification", "side": t,
                          "ply": initiated[1], "stage": "completed",
                          "price": PRICES.get("simplification", 0.0),
                          "detail": f"{len(initiated)} trades initiated"})

    # ---- knight_reroute (2026-07-22, user ruling): the thematic multi-hop
    #      knight maneuver (Nc6-d4-e6-f4). Piece-identity tracking via board
    #      replay (snapshots are identity-blind): a knight that makes >= 3
    #      hops within the window and LANDS on a hole in the enemy camp
    #      (rel rank 4+), holding it for the tail, executed a reroute. The
    #      sampled-line verifiers systematically miss narrow multi-hop plans
    #      (2 engine lines + 16 rollouts rarely stumble onto one specific
    #      3-hop sequence) — naming the maneuver retrospectively is how the
    #      grammar sees what the samplers cannot.
    b2 = start.copy()
    hop_count: dict[int, int] = {}          # knight square -> hops so far
    for k in range(1, len(snaps)):
        ply, mover, s_k = snaps[k]
        mvk = moves[ply]
        pc = b2.piece_at(mvk.from_square)
        cap = b2.piece_at(mvk.to_square)
        # ---- backward_push (2026-07-22 user request; v3 after two audit
        #      rounds): the freeing break of the backward pawn. v1 bare
        #      event: 0.99/0.82 (the storm disease — random shoves the
        #      pawn more than GMs, who wait). v2 no-net-pawn-loss gate:
        #      broken (the even liquidation transiently dips a pawn
        #      mid-exchange). v3 PREPAREDNESS intent gate via SEE: after
        #      the push, the opponent must gain NOTHING by capturing on
        #      the stop-square (static exchange value 0 — raw attacker
        #      counts fail on x-rays and even liquidations), plus v1's
        #      dissolution persistence (the side's backward count drops
        #      and stays dropped).
        if pc and pc.piece_type == chess.PAWN and cap is None \
                and k + tail < len(snaps):
            t_p = "W" if pc.color == chess.WHITE else "B"
            pback = snaps[k - 1][2][f"{t_p}.backward"]
            if mvk.from_square in pback:
                b3 = b2.copy(stack=False)
                b3.remove_piece_at(mvk.from_square)
                b3.set_piece_at(mvk.to_square, pc)
                prepared = _see(b3, mvk.to_square, not pc.color) == 0
            else:
                prepared = False
            if prepared:
                nb = len(pback)
                if _holds_to_end(snaps, k,
                                 lambda sn: len(sn[f"{t_p}.backward"]) < nb):
                    plans.append({"name": "backward_push", "side": t_p,
                                  "ply": ply, "stage": "completed",
                                  "price": PRICES.get("backward_push", 0.0),
                                  "detail":
                                  f"{chess.square_name(mvk.from_square)}-"
                                  f"{chess.square_name(mvk.to_square)}"})
        if cap and mvk.to_square in hop_count:
            del hop_count[mvk.to_square]     # tracked knight was captured
        if pc and pc.piece_type == chess.KNIGHT:
            n_hops = hop_count.pop(mvk.from_square, 0) + 1
            hop_count[mvk.to_square] = n_hops
            side_m = pc.color
            t_m = "W" if side_m == chess.WHITE else "B"
            enemy_m = not side_m
            # ---- strong_outpost (2026-07-22, user-defined): a knight lands
            #      on a STRONG SQUARE — not a permanent hole, but a square
            #      whose only pawn-challenger is an enemy king-shelter pawn
            #      (the Ruy Lopez Nf5). Checked on the PRE-move board, held
            #      for the tail. Distinct from outpost_occupation (permanent
            #      holes) and knight_reroute (>= 3 hops).
            pre_strong = mvk.to_square in strong_squares(b2, side_m)
            b2.push(mvk)
            if pre_strong and k + tail < len(snaps) \
                    and all(mvk.to_square in snaps[j][2][f"{t_m}.knight_sqs"]
                            for j in range(k, min(k + tail + 1, len(snaps)))):
                plans.append({"name": "strong_outpost", "side": t_m,
                              "ply": ply, "stage": "completed",
                              "price": PRICES.get("strong_outpost", 0.0),
                              "detail": chess.square_name(mvk.to_square)})
            if n_hops >= 3 and k + tail < len(snaps) \
                    and side_rank(mvk.to_square, side_m) >= 3 \
                    and is_hole(b2, mvk.to_square, enemy_m) \
                    and all(mvk.to_square in snaps[j][2][f"{t_m}.knight_sqs"]
                            for j in range(k, min(k + tail + 1, len(snaps)))):
                plans.append({"name": "knight_reroute", "side": t_m,
                              "ply": ply, "stage": "completed",
                              "price": PRICES.get("knight_reroute", 0.0),
                              "detail": f"{n_hops} hops -> "
                                        f"{chess.square_name(mvk.to_square)}"})
                hop_count[mvk.to_square] = 0   # journey complete; reset
        else:
            b2.push(mvk)

    # ---- attack_passer (2026-07-22, user-defined): the OPPONENT of a
    #      passed pawn goes after it — passers are dangerous and must be
    #      neutralized (Nimzowitsch: restrain, blockade, destroy). Two
    #      events, each with the attacking PIECES extracted
    #      deterministically from the line itself:
    #        taken    — the passer is captured (detail names the capturer).
    #        besieged — >= 2 attacker-side pieces bear on the passer's
    #                   CURRENT square and the pressure holds for the tail.
    #      The passer is TRACKED as it advances; the detail's first
    #      comma-token is its ORIGINAL square so per-square verify scoping
    #      matches the suggest candidate ('d6, attacked by rook+knight').
    for psq0, pcolor in [(q, chess.WHITE) for q in _passers(start, chess.WHITE)] \
            + [(q, chess.BLACK) for q in _passers(start, chess.BLACK)]:
        t_a = "B" if pcolor == chess.WHITE else "W"     # the attacker side
        att = not pcolor
        bb = start.copy(stack=False)
        cur = psq0
        pressure = []                    # (k, ply, n_attackers, names)
        for k in range(1, len(snaps)):
            ply, _mover, _sk = snaps[k]
            mvk = moves[ply]
            pc = bb.piece_at(mvk.from_square)
            if mvk.to_square == cur and pc is not None and pc.color == att:
                emit("attack_passer", t_a, ply, "completed",
                     f"{chess.square_name(psq0)}, taken by the "
                     f"{chess.piece_name(pc.piece_type)}")
                cur = None
                break
            bb.push(mvk)
            if pc is not None and mvk.from_square == cur:
                cur = mvk.to_square      # the passer advanced/captured
            if bb.piece_type_at(cur) != chess.PAWN \
                    or bb.color_at(cur) != pcolor:
                cur = None               # promoted or otherwise gone
                break
            names = sorted(chess.piece_name(bb.piece_type_at(a))
                           for a in bb.attackers(att, cur))
            pressure.append((k, ply, len(names), names))
        if cur is not None:              # never taken: check sustained siege
            for i, (k, ply, n, names) in enumerate(pressure):
                if n < 2 or k + tail >= len(snaps):
                    continue
                if all(m >= 2 for _, _, m, _ in pressure[i:i + tail + 1]):
                    emit("attack_passer", t_a, ply, "besieged",
                         f"{chess.square_name(psq0)}, attacked by "
                         + "+".join(names))
                    break

    plans.sort(key=lambda x: (-x["price"], x["ply"]))
    return plans


def labels(start: chess.Board, moves: list[chess.Move],
           horizon: int = 40, tail: int = TAIL) -> set[str]:
    out = set()
    for pl in parse_line(start, moves, horizon, tail):
        base = f"{pl['side']}:{pl['name']}"
        if pl["name"].startswith("minority"):
            out.add(f"{base}:{pl['stage']}")
        else:
            out.add(base)
    return out
