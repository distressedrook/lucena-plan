"""plan_diff — the snapshot/diff/parse algorithm: name plans from state deltas.

v2 (post four-way audit): the random control showed event-anchored rules
detect chess while state-drift rules detect noise. Every rule is now anchored
to an irreversible event, and drift-born states must HOLD TO WINDOW END.

  snapshot(board)          the state vector S(p) — hashable channels
  delta_stream(A, moves)   per-ply snapshots, mover-attributed
  parse_line(A, moves)     the plan grammar -> named, staged, priced plans
  labels(A, moves)         flat '<side>:<name>[:<stage>]' set

Grammar (specificity status from experiments/engine_vs_human_plans.jsonl):
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

sys.path.insert(0, "/Users/avismara/Development/chess-plans")
from weaknesses import (weak_pawns, entombed_bishops, exposed_king, is_hole,
                        side_rank)
from structures import classify

QS = {0, 1, 2}
PERSIST = 6
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


def snapshot(b: chess.Board) -> dict:
    s = {"structures": frozenset(classify(b))}
    pawn_files = {}
    for side, t in ((chess.WHITE, "W"), (chess.BLACK, "B")):
        bp = b.pieces(chess.PAWN, side)
        pawn_files[t] = frozenset(chess.square_file(p) for p in bp)
        pas = _passers(b, side)
        ksq = b.king(side)
        s[f"{t}.weak"] = frozenset(weak_pawns(b, side))
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
    s["wf"], s["bf"] = pawn_files["W"], pawn_files["B"]
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
        pre_plies = [k for k in range(len(snaps)) if snaps[k][2][f"{t}.minority_pre"]]
        if len(pre_plies) >= MINORITY_HELD:
            ranks = [snaps[k][2][f"{t}.b_rel_rank"] for k in pre_plies]
            in_carlsbad = any(("carlsbad", t == "W") in snaps[k][2]["structures"]
                              or ("carlsbad", chess.WHITE if t == "W" else chess.BLACK)
                              in snaps[k][2]["structures"] for k in pre_plies)
            name = "minority_attack" if in_carlsbad else "minority_attack_general"
            reached5 = any(r >= 4 for r in ranks)
            full = [sn[f"{t}.b_rel_rank"] for _, _, sn in snaps]
            # v3 lever fix: the b-pawn must vanish IN a capture on rel b5/c6
            # (random lines get their b-pawn eaten anywhere -> false levers)
            side_c = chess.WHITE if t == "W" else chess.BLACK
            vanished_after5 = False
            for j in range(1, len(snaps)):
                if full[j] == -1 and full[j - 1] >= 4:
                    mj = moves[snaps[j][0]]
                    rel_to = mj.to_square if side_c == chess.WHITE else \
                        chess.square(chess.square_file(mj.to_square),
                                     7 - chess.square_rank(mj.to_square))
                    if chess.square_name(rel_to) in ("b5", "c6"):
                        vanished_after5 = True
                    break
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
        okf = s0[f"{o}.king_file"]
        skf = s0[f"{t}.king_file"]
        wing = "k" if okf >= 5 else ("q" if okf <= 2 else None)
        own_on_wing = (wing == "k" and skf >= 5) or (wing == "q" and skf <= 2)
        if wing and not own_on_wing:
            prog = send[f"{t}.{wing}_progress"] - s0[f"{t}.{wing}_progress"]
            if prog >= 4 and send[f"{t}.{wing}_max"] >= 4:
                emit("pawn_storm", t, snaps[-1][0], "completed", wing)

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
