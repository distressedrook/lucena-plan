#!/usr/bin/env python3
"""suggest.py — the position→plan suggester. THE front door.

    ./suggest.py "FEN"
    ./suggest.py game.pgn 24

Three-stage architecture (2026-07-22 ruling):
  1. DESCRIBE — the complete state vector, neutrally. Everything the
     analyzers know, not a curated selection.
  2. SUGGEST  — candidate plans triggered by the description, each with its
     corpus reliability numbers. Candidates are NOT filtered by feasibility.
  3. VERIFY   — each candidate names what verifies it (engine soundness,
     Maia reachability, geometric notes). Verification is a downstream
     stage (engine/Maia); this tier only annotates.
"""
from __future__ import annotations

import sys

import chess
import chess.pgn

from structures import classify
from closed_v0 import skeleton
from weaknesses import census, is_hole, side_rank, bishop_escape_route
from plan_diff import snapshot


# Concrete verification contracts (2026-07-22 ruling: verification is a set
# of machine-checkable predicates with thresholds, not questions). All engine
# checks at fixed 1M nodes; k = Maia rollout count.
VERIFY = {
    "harvest": "engine: PV<=10 plies captures the pawn AND eval_after >= "
               "eval_now - 20cp; else REJECT",
    "outpost": "engine: eval(minor planted, best defense) >= eval_now - 25cp; "
               "maia k=10: occupation in >= 30% of futures",
    "keep_entombed": "engine: 10-ply PV eval drift >= -15cp AND no freeing "
                     "pawn trade in PV",
    "escape": "geometric route exists (shown); engine: eval after full "
              "extraction line >= eval_now - 20cp",
    "minority": "engine: forced sequence to the lever with eval >= -25cp at "
                "every own move; unreachable lever = REJECT (stall = 0.446)",
    "passer": "engine: PV advances the passer >= 2 ranks in 12 plies with "
              "eval loss <= 20cp",
    "center_break": "engine: break move within 30cp of engine-best AND a d/e "
                    "file opens within 6 PV plies",
    "deny_castling": "engine: after own 10-ply PV, enemy king still uncastled "
                     "AND eval >= +30cp if material was invested",
    "storm": "engine: storm advance within 30cp of best; maia k=10: >= 30% "
             "of futures push the same wing",
    "rook_activation": "engine: rook reaches the file within 10-ply PV, eval "
                       ">= eval_now - 20cp; corpus lift 2.26-2.58 (strongest "
                       "single family)",
    "attack_passer": "engine: the enemy passer is captured, or >= 2 pieces "
                     "besiege it for the tail, in an eval-equal line — the "
                     "attacker pieces are read off the line itself",
    "heavy_battery": "engine: a second heavy lands on the target file in an "
                     "eval-equal line and the doubling holds for the tail",
    "pair_break": "engine: after the N-for-B trade (direct or via the "
                  "outpost offer), eval >= eval_now - 20cp; maia: trade "
                  "resolves in >= 25% of rollouts",
    "backward_push": "engine: the freeing break appears in an eval-equal "
                     "line (band 50cp) — bare pushes are random-typical; "
                     "NEVER surface this unverified",
    "harvest_overextended": "engine: the overextended pawn falls or its "
                            "holes become outposts in an eval-equal line",
    "castle_kingside": "engine/maia: the king actually castles kingside in "
                      "an eval-equal line or the human rollouts",
    "castle_queenside": "engine/maia: the king actually castles queenside "
                        "in an eval-equal line or the human rollouts",
    "strong_outpost": "engine/maia: a knight reaches the strong square in "
                      "an eval-equal line or the human rollouts",
    "free_bad_bishop": "engine/maia: a same-color-pawn push that relieves "
                       "the bad bishop appears in an eval-equal line or the "
                       "human rollouts",
    "exchange_bad_bishop": "engine/maia: the bad bishop is traded off "
                           "(ideally for the enemy bishop) in an eval-equal "
                           "line or the human rollouts",
}


def name_side(s) -> str:
    return "White" if s in (chess.WHITE, "W") else "Black"


def sqn(sqs) -> str:
    return ",".join(chess.square_name(s) for s in sorted(sqs))


def holes_in(b: chess.Board, side: bool) -> list[tuple[str, str]]:
    """ALL holes in `side`'s camp (attacker-relative ranks 4-6), each with a
    value tag from the corpus laws: '' = deep+central (prime), 'rim' = a/h
    file (prices at 0.496 — near worthless), 'shallow' = attacker's 4th rank
    (0.509). Description shows everything; the plan stage applies the cuts."""
    out = []
    enemy = not side
    for sq in chess.SQUARES:
        if b.piece_at(sq):
            continue
        depth = side_rank(sq, enemy)
        if not 3 <= depth <= 5:
            continue
        if not is_hole(b, sq, side):
            continue
        f = chess.square_file(sq)
        tag = "rim" if f in (0, 7) else ("shallow" if depth == 3 else "")
        out.append((chess.square_name(sq), tag))
    return out


# ------------------------------------------------ pawn-structure decomposition
# Kmoch-complete: ANY pawn structure decomposes into rams, levers, majorities,
# files, chains, and defects. The named catalog is families on top of this.

def pawn_decomposition(b: chess.Board) -> list[str]:
    wp = b.pieces(chess.PAWN, chess.WHITE)
    bp = b.pieces(chess.PAWN, chess.BLACK)
    L = []
    # rams
    rams = [chess.square_name(s) + "/" + chess.square_name(s + 8)
            for s in wp if s + 8 < 64 and (s + 8) in bp]
    # files
    wf = {chess.square_file(s) for s in wp}
    bf = {chess.square_file(s) for s in bp}
    open_f = [chess.FILE_NAMES[f] for f in range(8) if f not in wf | bf]
    semi_w = [chess.FILE_NAMES[f] for f in sorted(bf - wf)]
    semi_b = [chess.FILE_NAMES[f] for f in sorted(wf - bf)]
    L.append("  files: open " + (",".join(open_f) or "-")
             + " | semi-open for White: " + (",".join(semi_w) or "-")
             + " | for Black: " + (",".join(semi_b) or "-"))
    L.append("  rams: " + (", ".join(rams) or "none"))
    # majorities per wing
    def wing_counts(files):
        return (sum(1 for s in wp if chess.square_file(s) in files),
                sum(1 for s in bp if chess.square_file(s) in files))
    qw, qb = wing_counts({0, 1, 2})
    kw, kb = wing_counts({5, 6, 7})
    maj = []
    if qw != qb:
        maj.append(f"queenside {qw}v{qb} ({'White' if qw > qb else 'Black'})")
    if kw != kb:
        maj.append(f"kingside {kw}v{kb} ({'White' if kw > kb else 'Black'})")
    L.append("  majorities: " + ("; ".join(maj) or "none (symmetric wings)"))
    # levers: available now (tension) and one advance away
    def levers(own, enemy, side):
        ahead = 8 if side == chess.WHITE else -8
        now, potential = [], []
        for p in own:
            for df in (-1, 1):
                f = chess.square_file(p) + df
                t2 = p + ahead + df
                if 0 <= f <= 7 and 0 <= t2 < 64 and t2 in enemy:
                    now.append(f"{chess.square_name(p)}x{chess.square_name(t2)}")
            home = (chess.square_rank(p) == 1) if side == chess.WHITE \
                else (chess.square_rank(p) == 6)
            advances = [p + ahead]
            if home:
                advances.append(p + 2 * ahead)     # double-step levers (b2-b4!)
            blocked = False
            for adv in advances:
                if not (0 <= adv < 64) or b.piece_at(adv) or blocked:
                    blocked = True
                    continue
                hits = [chess.square_name(adv + ahead + df) for df in (-1, 1)
                        if 0 <= chess.square_file(adv) + df <= 7
                        and 0 <= adv + ahead + df < 64
                        and (adv + ahead + df) in enemy]
                if hits:
                    potential.append(f"{chess.square_name(p)}-"
                                     f"{chess.square_name(adv)} (hits "
                                     + ",".join(hits) + ")")
        return now, potential
    for side, own, enemy, nm in ((chess.WHITE, wp, bp, "White"),
                                 (chess.BLACK, bp, wp, "Black")):
        now, pot = levers(own, enemy, side)
        L.append(f"  {nm} levers: now " + (", ".join(now) or "-")
                 + " | one move away: " + (", ".join(pot) or "-"))
    if not any("x" in l or "hits" in l for l in L[-2:]):
        L.append("  NO LEVERS EXIST for either side"
                 + (" — with a sealed skeleton this is FORTRESS-like: no file "
                    "can ever be opened by pawns" if not open_f else ""))
    return L


# ---------------------------------------------------------------- describe

def game_phase(b: chess.Board) -> str:
    """Deterministic phase: endgame = queens off or minor material; the
    2026-07-22 authority rule: in the endgame the ENGINE is authoritative —
    geometry keeps naming (king_march, passer_push, harvest) but stops
    ranking; corpus priors and Maia frequencies do not outrank calculation."""
    queens = len(b.pieces(chess.QUEEN, chess.WHITE)) + len(b.pieces(chess.QUEEN, chess.BLACK))
    minors_rooks = sum(len(b.pieces(pt, c)) for c in (chess.WHITE, chess.BLACK)
                       for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK))
    if queens == 0 and minors_rooks <= 4:
        return "endgame"
    if queens == 0 or minors_rooks <= 3:
        return "late-middlegame"
    return "middlegame"


def standing_batteries(b: chess.Board) -> dict:
    """Files where a side ALREADY has 2+ heavy pieces (rooks/queen) doubled
    on a file free of its own pawns — a standing FEATURE of the position
    (reported in describe()/the fact sheet's POSITION READ), distinct from
    the DOUBLE ON THE FILE plan (proposed only while the doubling hasn't
    happened yet). {"W": [(file_name, "open"|"semi-open"), ...], "B": [...]}."""
    s = snapshot(b)
    out = {"W": [], "B": []}
    for t in ("W", "B"):
        own_f = s["wf"] if t == "W" else s["bf"]
        opp_f = s["bf"] if t == "W" else s["wf"]
        for f in range(8):
            if f in own_f:
                continue
            if sum(1 for h in s[f"{t}.heavies"]
                   if chess.square_file(h) == f) >= 2:
                out[t].append((chess.FILE_NAMES[f],
                               "open" if f not in opp_f else "semi-open"))
    return out


def describe(b: chess.Board) -> list[str]:
    L = ["== POSITION =="]
    ph = game_phase(b)
    if ph == "endgame":
        L.append("  phase: ENDGAME — engine-authoritative; geometric plans "
                 "are narration, not recommendation")
    elif ph == "late-middlegame":
        L.append("  phase: late middlegame — engine weight rising")
    structs = classify(b)
    if structs:
        L.append("  structure: " + "; ".join(f"{n} (owner {name_side(o)})"
                                             for n, o in structs))
    else:
        L.append("  structure: none from the catalog")
    rams, central, tension, open_files = skeleton(b)
    closed = central >= 2 and open_files == 0 and tension <= 1 and rams >= 4
    L.append(f"  skeleton: rams {rams} (central {central}), tension {tension}, "
             f"open files {open_files}"
             + ("  [HERMETICALLY CLOSED]" if closed else ""))
    L.extend(pawn_decomposition(b))
    s = snapshot(b)
    wB, bB = s["W.bishops"], s["B.bishops"]
    wN, bN = s["W.knights"], s["B.knights"]
    minors = f"  minors: White {wB}B+{wN}N vs Black {bB}B+{bN}N"
    if s["W.has_pair"] != s["B.has_pair"]:
        minors += f" — {'White' if s['W.has_pair'] else 'Black'} has the bishop pair"
    if wB == 1 and bB == 1:
        wsq = next(iter(s["W.bishop_sqs"]))
        bsq = next(iter(s["B.bishop_sqs"]))
        light = lambda q: bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[q])
        if light(wsq) != light(bsq):
            minors += " — OPPOSITE-colored bishops"
    L.append(minors)
    bats = standing_batteries(b)
    for t in ("W", "B"):
        for fn, kind in bats[t]:
            L.append(f"  battery: {name_side(t)} heavies doubled on the "
                     f"{kind} {fn}-file")
    def king_status(t):
        if s[f"{t}.castled"]:
            return "castled"
        if s[f"{t}.can_castle"]:
            return "uncastled, rights available"
        return "uncastled, rights lost"
    L.append(f"  space: White {s['W.space']} vs Black {s['B.space']}; "
             f"kings on files {chess.FILE_NAMES[s['W.king_file']]}/"
             f"{chess.FILE_NAMES[s['B.king_file']]} "
             f"(White {king_status('W')}; Black {king_status('B')})")
    for t, side in (("W", chess.WHITE), ("B", chess.BLACK)):
        c = census(b, side)
        parts = []
        if c["weak_pawns"]:
            parts.append("weak pawns " + sqn(c["weak_pawns"]))
        for bsq in c["entombed_bishops"]:
            route = bishop_escape_route(b, side, bsq)
            if route is None:
                parts.append(f"bishop {chess.square_name(bsq)} entombed "
                             f"(NO geometric exit)")
            else:
                parts.append(f"bishop {chess.square_name(bsq)} entombed "
                             f"(exit exists: "
                             + "-".join(chess.square_name(x) for x in route) + ")")
        if c["occupied_outposts"]:
            parts.append("enemy outpost on " + sqn(c["occupied_outposts"]))
        if c["exposed_king"]:
            parts.append("exposed king")
        if s[f"{t}.doubled"]:
            parts.append(f"doubled pawns x{s[f'{t}.doubled']}")
        L.append(f"  {name_side(t)} camp: [{c['total']}] "
                 + ("; ".join(parts) if parts else "no fixed weaknesses")
                 + f"; islands {s[f'{t}.islands']}")
        extras = []
        if s[f"{t}.n_passers"]:
            kinds = [k for k, f in (("protected", s[f"{t}.protected_passer"]),
                                    ("outside", s[f"{t}.outside_passer"]),
                                    ("connected", s[f"{t}.connected_passers"])) if f]
            extras.append(f"passers x{s[f'{t}.n_passers']}"
                          + (f" ({','.join(kinds)})" if kinds else ""))
        hz = holes_in(b, not side)
        if hz:
            shown = [h + (f"({tag})" if tag else "") for h, tag in hz[:8]]
            extras.append(f"holes in enemy camp: {','.join(shown)}")
        if extras:
            L.append(f"    {name_side(t)} assets: " + "; ".join(extras))
    return L


# ----------------------------------------------------------------- suggest

def build_menus(b: chess.Board) -> dict:
    """PASS 1: state-triggered candidates per side. PASS 2: situational
    candidates gated on the COMPLETED menus (prophylaxis needs their menu,
    simplification needs the space differential, defense needs an actual
    attack). Returns the raw {t: [(eff, trigger, head, ev, verify,
    target_sq), ...]} menus — the data both suggest_plans() (numeric render)
    and fact_sheet.py (prose render) build on."""
    structs = classify(b)
    s = snapshot(b)
    from weaknesses import weak_pawns as _wp, entombed_bishops as _eb
    menus = {"W": [], "B": []}

    for t, side in (("W", chess.WHITE), ("B", chess.BLACK)):
        enemy = not side
        o = "B" if t == "W" else "W"
        plans = menus[t]

        def cand(eff, trigger, head, ev, verify, target_sq=None):
            plans.append((eff, trigger, head, ev, verify, target_sq))

        # CASTLE (2026-07-22, user-defined): fires even while blocked — a
        # longer-term "clear the path, then castle" idea, which the
        # verify-timing machinery (immediate/developing/long-term) already
        # renders correctly once the banked lines confirm it. Names exact
        # blocking squares, flagging enemy-occupied ones specifically.
        from weaknesses import castle_feasibility
        for kingside, fam, label in ((True, "castle_kingside", "KINGSIDE"),
                                     (False, "castle_queenside", "QUEENSIDE")):
            cf = castle_feasibility(b, side, kingside)
            if cf is None:
                continue
            bits = []
            if cf["blockers"]:
                own_b = [chess.square_name(sq) for sq, is_e in cf["blockers"]
                        if not is_e]
                enemy_b = [chess.square_name(sq) for sq, is_e in cf["blockers"]
                          if is_e]
                if own_b:
                    bits.append("own piece(s) still on "
                               + ",".join(own_b) + " need to move")
                if enemy_b:
                    bits.append(f"{name_side(enemy)}'s piece(s) sit on "
                               + ",".join(enemy_b) + " — blocking the path")
            if cf["attacked"]:
                bits.append("the king's path is currently covered by "
                           + name_side(enemy))
            cand(4.0, f"{name_side(side)}'s king uncastled, "
                 f"{label.lower()} rights available",
                 f"CASTLE {label}: get the king to safety",
                 "engine confirms it in 73% of eval-equal lines / 55% of "
                 "GM games (kingside) when the right is still held "
                 "(10.9x discrimination); queenside 28%/19% (5.2x) — "
                 "castling is a dominant, near-mandatory plan"
                 + (": " + "; ".join(bits) if bits else " — path is clear"),
                 VERIFY[fam])

        wp = _wp(b, enemy)
        if wp:
            cand(8.4, f"enemy weak pawns {sqn(wp)}",
                 "HARVEST the weak pawn(s) — attack to WIN them",
                 "harvested 1x -> 0.577, 2x -> 0.656; created-never-harvested "
                 "0.453 (worse than nothing)", VERIFY["harvest"])
        from weaknesses import overextended_pawns as _ox
        ox = _ox(b, enemy)
        if ox:
            cand(8.0, f"enemy overextended pawn(s) {sqn(ox)}",
                 "ATTACK THE OVEREXTENDED PAWN: it has outrun its support — "
                 "restrain it, blockade it, win it, and occupy the holes it "
                 "left behind (Nimzowitsch)",
                 "engine-gated: the pawn falls or the holes behind it become "
                 "outposts in the best lines", VERIFY["harvest_overextended"])

        # ============ the WEAKNESS-PLAN MATRIX (2026-07-22 ruling):
        # literature-tier attacker/owner plans for each detected pawn
        # weakness — advisory now, corpus calibration later (the SIMPLIFY
        # path). Every clause is PIECE-GATED (never name an executor that
        # isn't on the board — user ruling); a plan dies only when NO
        # clause survives.
        from weaknesses import isolated_pawns, backward_pawns
        heavies_t = bool(s[f"{t}.heavies"])
        knights_t = bool(b.pieces(chess.KNIGHT, side))
        minors_t = knights_t or bool(b.pieces(chess.BISHOP, side))
        ahead_o = 8 if enemy == chess.WHITE else -8
        ahead_t = 8 if side == chess.WHITE else -8
        fname = lambda q: chess.FILE_NAMES[chess.square_file(q)]

        for q, half in isolated_pawns(b, enemy)[:2]:
            stop = q + ahead_o
            cl = []
            if knights_t:
                cl.append(f"blockade {chess.square_name(stop)} — ideally "
                          "with a knight")
            elif minors_t:
                cl.append(f"blockade {chess.square_name(stop)} with a "
                          "minor piece")
            if heavies_t and half:
                cl.append(f"pile rooks/queen onto the {fname(q)}-file")
            if minors_t or heavies_t:
                cl.append("trade off its defenders and steer toward an "
                          "endgame, where it falls")
            if cl:
                cand(4.0, f"enemy isolated pawn on {chess.square_name(q)}",
                     f"BESIEGE THE ISOLATED PAWN on {chess.square_name(q)}: "
                     + "; ".join(cl),
                     "literature (Nimzowitsch/Silman): fix, blockade, "
                     "besiege — the blockader sits immune in front of it; "
                     "corpus calibration pending",
                     "advisory — literature tier; no engine contract")
        for q, half in isolated_pawns(b, side)[:2]:
            stop = q + ahead_t
            cl = [f"prepare the freeing {chess.square_name(q)}-"
                  f"{chess.square_name(stop)} advance to liquidate it at "
                  "the right moment"]
            if minors_t or heavies_t:
                cl.append("until then keep pieces on — the isolani's open "
                          "lines and outpost squares pay only in the "
                          "middlegame")
            cand(3.5, f"own isolated pawn on {chess.square_name(q)}",
                 f"USE OR LIQUIDATE THE ISOLANI on {chess.square_name(q)}: "
                 + "; ".join(cl),
                 "literature (the Tarrasch/Nimzowitsch two-sided verdict): "
                 "activity before the endgame, liquidation over passivity; "
                 "corpus calibration pending",
                 "advisory — literature tier; no engine contract")

        for q, half in backward_pawns(b, enemy)[:2]:
            stop = q + ahead_o
            cl = []
            if minors_t:
                cl.append(f"fix it: control or occupy "
                          f"{chess.square_name(stop)} (its stop-square is "
                          "a hole by construction)")
            if heavies_t and half:
                cl.append(f"pile on the half-open {fname(q)}-file")
            if minors_t or heavies_t:
                cl.append("the pawn is a permanent target — win it or "
                          "keep the defense chained to it")
            if cl:
                cand(4.0, f"enemy backward pawn on {chess.square_name(q)}",
                     f"FIX AND BESIEGE THE BACKWARD PAWN on "
                     f"{chess.square_name(q)}: " + "; ".join(cl),
                     "literature (Kmoch/Nimzowitsch): the backward pawn "
                     "and its stop-square are ONE weakness; corpus "
                     "calibration pending",
                     "advisory — literature tier; no engine contract")
        for q, half in backward_pawns(b, side)[:2]:
            stop = q + ahead_t
            cand(3.0, f"own backward pawn on {chess.square_name(q)}",
                 f"FREE THE BACKWARD PAWN: prepare the "
                 f"{chess.square_name(q)}-{chess.square_name(stop)} break",
                 "the textbook cure — dissolve or liquidate the weakness. "
                 "Corpus: bare pushes are random-typical; the PREPARED "
                 "break graduated (lift 1.55/1.36, n=20,688; benchmark 39% "
                 "engine-confirm vs 10% floor = 3.9x). Engine-gated per "
                 "position — engine endorses it at ~2x the GM rate",
                 VERIFY["backward_push"])

        dbl_files = [f for f in range(8)
                     if sum(1 for p_ in b.pieces(chess.PAWN, enemy)
                            if chess.square_file(p_) == f) >= 2]
        if dbl_files and (minors_t or heavies_t):
            cand(2.5, "enemy doubled pawns on the "
                 + "/".join(chess.FILE_NAMES[f] for f in dbl_files)
                 + "-file(s)",
                 "TARGET THE DOUBLED PAWNS: blockade the front one — the "
                 "rear one can never advance past it; attack the base",
                 "literature: doubled pawns cannot defend each other and "
                 "cannot make a passer unaided; corpus calibration pending",
                 "advisory — literature tier; no engine contract")

        for n_, ow in structs:
            if n_ != "hanging_pawns":
                continue
            if ow == enemy and (minors_t or heavies_t):
                cand(3.5, "enemy hanging pawns",
                     "PRESSURE THE HANGING PAWNS: attack them frontally, "
                     "force one to advance, then blockade and besiege the "
                     "one left behind",
                     "literature: hanging pawns are strong until forced to "
                     "move — the forced advance converts the duo into a "
                     "backward pawn + hole; corpus calibration pending",
                     "advisory — literature tier; no engine contract")
            elif ow == side:
                cand(3.5, "own hanging pawns",
                     "KEEP THE HANGING PAWNS ABREAST: don't let either be "
                     f"forced forward; their advance should be a break "
                     f"{name_side(side)} chooses, not a concession "
                     f"{name_side(side)} is forced into",
                     "literature: the duo's strength is the double break "
                     "threat; corpus calibration pending",
                     "advisory — literature tier; no engine contract")
        # ONE candidate PER HOLE (not bundled) — each square gets its own
        # claim and its own verify() call. A confirmed d5 must never lend
        # credibility to an unconfirmed f6 just because both are "holes".
        # Each hole carries the geometric KNIGHT ROUTE when one exists —
        # multi-hop maneuvers (Nc6-d4-e6-f4) are THE thematic content of
        # many positions and sampled-line verifiers systematically miss
        # them; the route annotation is how they surface.
        from weaknesses import knight_route, knight_route_conditional

        def route_text(target_sqs: set[int]) -> str:
            """Skeleton-conditional route annotation: the pawn-safe route
            NOW, plus the shorter shortcut with the pawns that block it —
            routes are computed against today's skeleton, and by execution
            time (plies later) the blocking pawn may be gone (user ruling
            2026-07-22)."""
            if not b.pieces(chess.KNIGHT, side):
                return ""
            safe, shortcut, blockers = knight_route_conditional(
                b, side, target_sqs)
            parts = []
            if safe:
                parts.append("knight route (current skeleton): "
                             + "-".join(chess.square_name(x) for x in safe))
            if shortcut:
                bl = ",".join(chess.square_name(x) for x in blockers)
                parts.append("knight shortcut "
                             + "-".join(chess.square_name(x) for x in shortcut)
                             + f" opens if the {bl} pawn(s) leave/advance")
            # ALWAYS 'knight ...'-prefixed: these clauses get attached to
            # bishop-themed plans too (BREAK THE BISHOP PAIR's offer route,
            # 'plant a minor' outposts) — an unlabeled square chain there
            # reads as the BISHOP's path, which it never is (2026-07-22:
            # 'd7-b8-a6-b4-d3 isn't a route for the bishop' — it was the
            # knight's offer route).
            return ("; " + "; ".join(parts)) if parts else ""

        # Reachability gate (2026-07-22 finding): a hole is only a real
        # OUTPOST candidate if some own piece can EVER physically stand
        # there. A bishop is color-bound for life — a wrong-colored
        # bishop with no knight on the board means NO piece can ever
        # reach the square, not just an ambiguous "a minor" (a caught
        # case: bishop on f3 (light), hole on b6 (dark) — impossible,
        # not merely unspecified).
        has_knight = bool(b.pieces(chess.KNIGHT, side))
        own_bishop_colors = {bool(chess.BB_LIGHT_SQUARES
                                  & chess.BB_SQUARES[bs])
                             for bs in b.pieces(chess.BISHOP, side)}
        hz = [h for h, tag in holes_in(b, enemy) if not tag]
        for hole in hz[:4]:
            hsq = chess.parse_square(hole)
            hole_light = bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[hsq])
            matching_bishop = hole_light in own_bishop_colors
            if not has_knight and not matching_bishop:
                continue   # no own piece can ever stand on this square
            piece_word = ("a minor" if has_knight and matching_bishop
                         else f"{name_side(side)}'s knight" if has_knight
                         else f"{name_side(side)}'s bishop")
            rtxt = route_text({hsq})
            cand(8.3, f"prime hole {hole} in enemy camp",
                 f"OUTPOST PLAN: plant {piece_word} on {hole}",
                 "presence pays +8.3pp rent; depth law 0.509/0.561/0.584"
                 + rtxt,
                 VERIFY["outpost"], target_sq=hole)
        # STRONG-SQUARE KNIGHT (2026-07-22, user-defined): a knight
        # maneuver to a square whose only pawn-challenger is an enemy
        # king-shelter pawn (Ruy Lopez Nf5) — broader than a permanent
        # hole. Candidate-tier: fires broadly, the engine gate prunes.
        from weaknesses import strong_squares as _ss
        ss = [s2 for s2 in _ss(b, side) if b.pieces(chess.KNIGHT, side)
              and knight_route(b, side, {s2})]
        for s2 in ss[:2]:
            sname = chess.square_name(s2)
            cand(5.0, f"strong square {sname} (only an enemy king-shelter "
                 "pawn can challenge it)",
                 f"KNIGHT TO {sname}: maneuver a knight to the strong "
                 f"square in front of {name_side(enemy)}'s king",
                 f"the Ruy-Lopez outpost: {name_side(enemy)} can only "
                 f"evict it by pushing a pawn that weakens "
                 f"{name_side(enemy)}'s own king"
                 + route_text({s2}),
                 VERIFY["strong_outpost"], target_sq=sname)
        # BREAK THE BISHOP PAIR (2026-07-22 ruling + corpus verdict): the
        # pair-less side strives to trade a knight for a bishop — lift
        # 11.3 fast / 9.1 slow, 3rd-strongest family in the book; the
        # exchange pays in EVERY openness cell (+2 to +5pp; largest at MID,
        # not open — folklore corrected). Route: direct NxB, or the
        # provoked outpost-offer (plant the knight on a hole the bishop
        # must take). The hole offer squares double as the route targets.
        if s[f"{o}.has_pair"] and not s[f"{t}.has_pair"] \
                and (b.pieces(chess.KNIGHT, side)
                     or b.pieces(chess.BISHOP, side)):
            offer_sqs = {chess.parse_square(h) for h in hz}
            rtxt = route_text(offer_sqs) if offer_sqs else ""
            cand(8.5, f"{name_side(o)} holds the bishop pair; own minor(s) "
                 "available",
                 "BREAK THE BISHOP PAIR: trade a minor for a bishop "
                 "(NxB or BxB — the pair dies either way)",
                 "lift 15.66 fast / 11.71 slow (2nd-strongest family in the "
                 "book, n=26,183; widening to include BxB STRENGTHENED the "
                 "signal, did not dilute it); resolving the pair pays "
                 "+2-5pp in every openness cell (max at MID openness); "
                 "GMs resolve it ~80% of the time"
                 + rtxt,
                 VERIFY["pair_break"])
        ent = _eb(b, enemy)
        if ent:
            cand(4.9, f"enemy entombed bishop {sqn(ent)}",
                 "KEEP IT ENTOMBED: avoid freeing trades, invade its color",
                 "largest B-vs-N effect (0.424 open); convert via a SECOND "
                 "piece-access weakness", VERIFY["keep_entombed"])
        for bsq in _eb(b, side):
            route = bishop_escape_route(b, side, bsq)
            cand(6.0, f"own entombed bishop {chess.square_name(bsq)}",
                 "ESCAPE the bad bishop (extraction beats trading)",
                 "escape 0.496 > trade 0.456 > stuck 0.436"
                 + (f"; geometric exit: "
                    + "-".join(chess.square_name(x) for x in route)
                    if route else "; NO geometric exit in this skeleton"),
                 VERIFY["escape"])
        # FREE THE BAD BISHOP (2026-07-22, user-defined): a lone bishop
        # choked by its own same-color pawns — push one of those pawns
        # OFF its color to relieve it (c6-c5, g6-g5, ...b6). A push flips
        # the pawn's color; only pushes free the bishop. Broader than the
        # entombment case above (fires on the mobility-choked bishop the
        # ram-based entombed_bishops misses).
        from weaknesses import bad_bishop as _bb, sq_color as _sqc
        for bsq in _bb(b, side):
            bcolor = _sqc(bsq)
            frees = [chess.square_name(pp) + "-"
                     + chess.square_name(pp + (8 if side == chess.WHITE else -8))
                     for pp in b.pieces(chess.PAWN, side)
                     if _sqc(pp) == bcolor
                     and not b.piece_at(pp + (8 if side == chess.WHITE else -8))]
            cand(4.5, f"own bad bishop {chess.square_name(bsq)} "
                 "(choked by same-color pawns)",
                 "FREE THE BAD BISHOP: push a same-color pawn off its color "
                 "to open lines for it",
                 "engine frees it in 76% of best lines / 49% of GM games "
                 "when a bad bishop is present (validated on the banked "
                 "benchmark; no random-floor gate — pushing pawns is a "
                 "common move type by nature)"
                 + (f"; available freeing pushes: {', '.join(frees)}"
                    if frees else ""),
                 VERIFY["free_bad_bishop"])
            # EXCHANGE THE BAD BISHOP (2026-07-22 v2, user refinement):
            # only surfaces when the ENEMY has a GOOD (non-bad) bishop to
            # target — trading a bad bishop for the enemy's OWN bad
            # bishop isn't the plan (that's just a trade, not a cure), and
            # a knight trade no longer qualifies either (narrower than
            # v1's "a knight will do"). MUST be the SAME COLOR as bsq
            # (2026-07-22 correction): a bishop is color-locked for its
            # entire life, so a direct bishop-for-bishop capture between
            # opposite-colored bishops is not just unlikely, it's
            # physically impossible. Verified against the banked/live
            # lines that the trade specifically lands on the enemy's good,
            # same-colored bishop, not just any capture.
            enemy_good = [q for q in b.pieces(chess.BISHOP, enemy)
                         if q not in _bb(b, enemy) and _sqc(q) == bcolor]
            if enemy_good:
                targets = ",".join(chess.square_name(q) for q in enemy_good)
                cand(4.5, f"own bad bishop {chess.square_name(bsq)}; "
                     f"{name_side(enemy)}'s bishop on {targets} is good",
                     f"EXCHANGE THE BAD BISHOP: trade it for "
                     f"{name_side(enemy)}'s good bishop on {targets}",
                     "the other cure: trade the bad piece specifically for "
                     "the enemy's good one, not just any piece — 55x "
                     "discrimination vs the random floor (5.5% "
                     "engine-confirm / 0.1% floor, n=2,217); the engine "
                     "gate confirms whether that exact trade happens here",
                     VERIFY["exchange_bad_bishop"])
        own_qs = [q for q in b.pieces(chess.PAWN, side) if chess.square_file(q) <= 2]
        opp_qs = [q for q in b.pieces(chess.PAWN, enemy) if chess.square_file(q) <= 2]
        opp_castled_q = s[f"{o}.king_file"] <= 2 and s[f"{t}.king_file"] >= 4
        if opp_castled_q and s[f"{o}.castled"]:
            cand(2.0, f"opposite castling: {name_side(o)}'s king on the queenside",
                 "STORM the queenside — an ATTACK, not a minority attack",
                 "storm lift 2.04 fast (intent-gated)", VERIFY["storm"])
        if s[f"{t}.king_file"] <= 2 and s[f"{o}.king_file"] >= 5 and s[f"{o}.castled"]:
            cand(2.0, f"opposite castling: {name_side(o)}'s king on the kingside",
                 "STORM the kingside with g/h pawns",
                 "storm lift 2.04 fast (intent-gated)", VERIFY["storm"])
        if (not opp_castled_q
                and len(own_qs) == 2 and not any(chess.square_file(q) == 2 for q in own_qs)
                and len(opp_qs) == 3 and any(chess.square_file(q) == 2 for q in opp_qs)):
            in_c = any(n == "carlsbad" and ow == side for n, ow in structs)
            # The lever pawn is whichever own queenside pawn borders the
            # open c-file (the b-file one) — named from ITS ACTUAL current
            # square, not a fixed "b4-b5" (2026-07-22 finding: that literal
            # string was printed regardless of the real position; on one
            # real position the pawn was still on b3, and b4 was occupied
            # by the opponent's OWN bishop — actively wrong, not just
            # imprecise). Black and White reach this independently (each
            # iteration of the t/side loop computes its own own_qs), so
            # the two sides' plans differ correctly when their structures
            # differ. No occupancy check needed here: an unreachable lever
            # simply won't confirm against the banked/live lines below —
            # verify handles that, this candidate only needs to be honest
            # about the geometry.
            lever_pawn = next((q for q in own_qs if chess.square_file(q) == 1),
                              max(own_qs, key=chess.square_file))
            lf = chess.square_file(lever_pawn)
            lever_rank = 4 if side == chess.WHITE else 3     # b5 / b4
            cap_rank = 5 if side == chess.WHITE else 2       # c6 / c3
            lever_sq = chess.square_name(chess.square(lf, lever_rank))
            cap_sq = chess.square_name(chess.square(2, cap_rank))
            lfile = chess.FILE_NAMES[lf]
            cand(4.0 if in_c else 1.8, "2v3 queenside minority + semi-open c-file",
                 f"MINORITY ATTACK: push the {lfile}-pawn (currently "
                 f"{chess.square_name(lever_pawn)}) to {lever_sq}, then "
                 f"lever {lfile}x{cap_sq}",
                 ("Carlsbad: completed 0.547 vs 0.507; lever lands 22%"
                  if in_c else "generalized: lever lands 13%; launched 0.472")
                 + "; stalling at b5 is WORSE than not starting (0.446)",
                 VERIFY["minority"])
        if s[f"{t}.castled"] and not s[f"{o}.castled"] \
                and (s[f"{o}.can_castle"] or s[f"{o}.king_central"]):
            cand(5.0, f"own king castled; {name_side(o)}'s king uncommitted",
                 "BREAK OPEN THE CENTER while their king is stuck there",
                 "corpus: lift 3.15 fast [2.74-3.62] — the strongest fast rule",
                 VERIFY["center_break"])
            cand(5.0, f"{name_side(o)} still has castling to complete",
                 "DENY CASTLING: hit e-file/f7 targets, keep the king stuck",
                 "rollout-invisible (0.70-0.86) — real only via engine contract",
                 VERIFY["deny_castling"])
        if s[f"{t}.n_passers"]:
            cand(1.7, f"passer(s) x{s[f'{t}.n_passers']}",
                 "PUSH THE PASSER toward the 6th",
                 "passer_push lift 1.77 fast; outcome 0.577", VERIFY["passer"])
        # ATTACK THE PASSER (2026-07-22, user-defined): the passer's
        # OPPONENT must neutralize it — passed pawns are dangerous. One
        # candidate PER enemy passer (never bundled); the verify detail
        # names the attacking pieces read off the line itself.
        if s[f"{o}.n_passers"]:
            from plan_diff import _passers
            for q in _passers(b, not side)[:2]:
                psq = chess.square_name(q)
                cand(3.5, f"enemy passed pawn on {psq}",
                     f"ATTACK THE PASSER on {psq}: restrain it, then attack "
                     "it — an enemy passer is a standing threat",
                     "AUDITED v7 (2026-07-22): benchmark 87% engine-confirm"
                     " / 44% floor, 91% maia-typical (n=253); corpus lift"
                     " 1.30 fast / 1.42 slow — a move-type plan (the"
                     " free_bad_bishop precedent: random lines capture"
                     " pawns too), so validation is per-position engine"
                     " presence, never the floor gate",
                     VERIFY["attack_passer"], target_sq=psq)
        own_f = s["wf"] if t == "W" else s["bf"]
        opp_f = s["bf"] if t == "W" else s["wf"]
        free_files = [f for f in range(8) if f not in own_f]
        if free_files:
            kind = [("open" if f not in opp_f else "semi-open",
                     chess.FILE_NAMES[f]) for f in free_files]
            cand(2.6, ", ".join(f"{k} {name}-file" for k, name in kind),
                 "ROOK ACTIVATION: put a rook on the open/semi-open file",
                 "corpus: lift 2.26-2.58 fast/slow — the strongest single "
                 "family in the vocabulary", VERIFY["rook_activation"])
        # DOUBLE ON THE FILE (heavy_battery, finding 12: lift 1.93/2.35) —
        # was an ORPHAN family (registered in CANDIDATE_FAMILIES, never
        # proposed; same shape as the piece_attack gap, KNOWN_ISSUES #8).
        # Propose when the side has 2+ heavies and a free file with a
        # TARGET (the plan_diff detector's own condition: an enemy pawn on
        # the file, or the enemy king's file) that isn't ALREADY doubled —
        # a standing battery is a feature (standing_batteries), not a plan.
        heavies = s[f"{t}.heavies"]
        if len(heavies) >= 2 and free_files:
            targets = [f for f in free_files
                       if f in opp_f or s[f"{o}.king_file"] == f]
            undoubled = [f for f in targets
                         if sum(1 for h in heavies
                                if chess.square_file(h) == f) < 2]
            if undoubled:
                names = ", ".join(f"{chess.FILE_NAMES[f]}-file"
                                  for f in undoubled)
                cand(2.4, f"battery target: {names} (2+ heavies available)",
                     f"DOUBLE ON THE FILE: double rooks (or rook and queen) "
                     f"on the {names}",
                     "heavy_battery lift 1.93 fast / 2.35 slow",
                     VERIFY["heavy_battery"])

    # ---- PASS 2: situation layer over completed menus
    for t, side in (("W", chess.WHITE), ("B", chess.BLACK)):
        o = "B" if t == "W" else "W"
        plans = menus[t]
        opp_hot = [pl for pl in menus[o] if pl[0] >= 4.0]
        if not opp_hot:
            tgt = max(menus[o], key=lambda pl: pl[0], default=None)
            plans.append((3.0, "QUIET: opponent's menu is "
                          + ("empty" if tgt is None else "low-priced"),
                          "PROPHYLAXIS: pre-empt their best idea"
                          + (f" — their top candidate: '{tgt[2][:44]}'"
                             if tgt else
                             f" — improve {name_side(side)}'s worst piece"),
                          "situational; target named from the opponent's menu",
                          "engine: preventing move within 15cp of best AND "
                          "their trigger OFF afterward", None))
        if s[f"{t}.space"] - s[f"{o}.space"] <= -6:
            plans.append((4.5, f"CRAMPED: space {s[f'{t}.space']} vs "
                          f"{s[f'{o}.space']}",
                          "SIMPLIFY: trade pieces, especially their active ones",
                          "corpus calibration (simplify_gate_study, mirrors "
                          "AVOID TRADES): heavy trading at space deficit 6-7 "
                          "scores 0.490 vs 0.400 when avoiding trades "
                          "(+9pp); negligible below 6 (+1-2pp) — the "
                          "inherited -4 literature gate was too loose, "
                          "tightened to match",
                          "engine: each initiated trade keeps eval within 20cp",
                          None))
        # AVOID TRADES — SIMPLIFY's mirror for the SPACE side (2026-07-22
        # user ruling + calibration). Corpus dose-response
        # (space_trades_study, 25,562 games): avoid-vs-heavy-trading edge
        # is +1.1pp at space diff 2-3, +2.4pp at 4-5, +9.0pp at 6-7 —
        # "considerable" is real; gate at >= 6, where the advice starts
        # paying seriously. Advisory tier: no engine contract (the corpus
        # gradient is the evidence; bind_squeeze's audit failure was about
        # DETECTABILITY vs random, not about the advice being wrong).
        if s[f"{t}.space"] - s[f"{o}.space"] >= 6:
            plans.append((4.5, f"BIG SPACE EDGE: {s[f'{t}.space']} vs "
                          f"{s[f'{o}.space']}",
                          f"AVOID TRADES: keep pieces on — "
                          f"{name_side(side)}'s space suffocates "
                          f"{name_side(o)} only while the board stays full",
                          "corpus calibration: avoiding trades at space "
                          "edge 6-7 scores 0.600 vs 0.510 when trading "
                          "heavily (+9pp); effect is monotone in the edge "
                          "and negligible below 6",
                          "advisory — no engine contract; decline trades "
                          "that don't win material or fix a concrete "
                          "problem", None))
        if any("STORM" in pl[2] or "BREAK OPEN" in pl[2] for pl in menus[o]) \
                or census(b, side)["exposed_king"]:
            plans.append((3.5, "UNDER ATTACK: opponent holds attacking "
                          "candidates",
                          "DEFEND: trade attackers / evacuate the king / "
                          "regroup defenders",
                          "situational; evacuation fires ONLY here",
                          "engine: defensive line holds; attacker count near "
                          "king falls in PV", None))
            # the classical maxim: meet the wing attack in the CENTER —
            # name the actual central lever from the Kmoch enumeration
            central = [l for l in pawn_decomposition(b)
                       if l.strip().startswith(name_side(t)) and "hits" in l]
            levers = []
            if central:
                import re as _re
                for m in _re.finditer(r"([a-h][1-8]-[a-h][1-8]) \(hits", central[0]):
                    if m.group(1)[0] in "cdef":
                        levers.append(m.group(1))
            if levers:
                plans.append((4.5, "UNDER WING ATTACK + central lever available",
                              "COUNTER IN THE CENTER: " + ", ".join(levers)
                              + " — the classical answer to a wing attack",
                              "maxim, corpus test pending; lever named from "
                              "THIS position's Kmoch enumeration",
                              "engine: the central break within 25cp of best; "
                              "opening the center must outscore defending",
                              None))

    return menus


def suggest_plans(b: chess.Board) -> list[str]:
    menus = build_menus(b)
    L = []
    for t in ("W", "B"):
        if menus[t]:
            L.append(f"\n== CANDIDATE PLANS — {name_side(t)} "
                     f"(by corpus effect; unverified) ==")
            for eff, trig, head, ev, verify, tsq in sorted(menus[t], key=lambda x: -x[0]):
                L.append(f"  [{eff:+.1f}pp] {head}")
                L.append(f"           trigger: {trig}")
                L.append(f"           corpus:  {ev}")
                L.append(f"           verify:  {verify}"
                         + (f" [target square: {tsq}]" if tsq else ""))
    if not L:
        L.append("\n== CANDIDATE PLANS: none triggered ==")
    return L


def suggest(b: chess.Board) -> str:
    return "\n".join(describe(b) + suggest_plans(b))


def suggest_verified(b: chess.Board, pvs: list | None,
                     rolls: list | None) -> str:
    """The closed loop: describe -> suggest -> CHECK ROLLED LINES -> DIFF.
    Every surfaced candidate family is verified from THIS position (engine
    equal-line confirmation + Maia k-roll typicality) instead of asserted
    from corpus priors.

    THE CONTRACT: (fen, pvs, rolls) — the caller supplies the position's
    rolled lines (one engine MultiPV roll + K Maia rollouts covers every
    job; verify truncates each family to its own horizon). This function
    never rolls."""
    import os
    import sys
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "research"))
    from verify import verify_plan
    from experiments.tools.plan_trace import triggers
    out = describe(b) + suggest_plans(b)
    out.append("")
    out.append("== VERIFY (suggest -> roll -> diff, per position) ==")
    trig = triggers(b)
    fams = sorted({(t, f) for (t, lab) in trig
                   for f in CANDIDATE_FAMILIES.get(lab, ())})
    # SQUARE-BEARING families: verify each target square SEPARATELY. A
    # bundled label like "prime holes c5,d6,f6" must never let a confirmed
    # d5 lend credibility to an unconfirmed f6 — each square gets its own
    # roll-and-diff and its own verdict.
    SQUARE_FAMILIES = {"outpost_occupation"}
    from weaknesses import knight_route
    jobs = []   # (t, fam, square_or_None, display_label, route_hops)
    for t, fam in fams:
        if fam in SQUARE_FAMILIES and fam == "outpost_occupation":
            side_t = chess.WHITE if t == "W" else chess.BLACK
            enemy = not side_t
            holes = [h for h, tag in holes_in(b, enemy) if not tag]
            if holes:
                for h in holes[:4]:
                    # route length scales the verify horizon: convoluted
                    # real-game journeys must not time out the check
                    r = knight_route(b, side_t, {chess.parse_square(h)})
                    hops = len(r) - 1 if r else None
                    jobs.append((t, fam, h, f"{fam}@{h}", hops))
                continue
        jobs.append((t, fam, None, fam, None))
    if not jobs:
        out.append("  (no state-triggered candidates to verify)")
    for t, fam, sq, label, hops in jobs:
        v = verify_plan(b.fen(), t, fam, pvs, rolls,
                        square=sq, route_hops=hops)
        eng = v["engine"]
        mai = v["maia"]
        bits = []
        if eng is not None:
            bits.append(f"engine {eng['equal_lines']} equal lines, "
                        f"{'IN' if eng['in_equal_line'] else 'not in'}")
        else:
            bits.append("engine: no lines supplied")
        if mai is not None:
            bits.append(f"maia {mai['hits']}/{mai['k']} "
                        f"(floor {mai['floor']:.1%})")
        else:
            bits.append("maia: no rolls supplied")
        out.append(f"  {name_side(t)} {label} [h{v['horizon']}]: "
                   f"{v['verdict']}  ({'; '.join(bits)})")
        # TIMING — never let a later-firing confirmation read as "play it
        # now": a plan confirmed at ply 11 needed ten plies of unrelated
        # play first. Show the lag and what to ACTUALLY play immediately.
        if v["verdict"] == "CONFIRMED-SOUND-LATER":
            out.append(f"           NOT YET DUE — fires at ply {v['lag']} "
                       f"of this line, not now. Play the position's actual "
                       f"next move instead: {v['immediate_move']}")
        elif v["verdict"] == "CONFIRMED-SOUND":
            out.append(f"           due now (ply {v['lag']}): "
                       f"{v['immediate_move']}")
    return "\n".join(out)


# --------------------------------------------------- execution verification
# Deterministic delta-check: given position A and the moves actually played,
# parse the delta stream and report, per candidate family, whether the plan
# was EXECUTED (with stage), or never attempted. Pure geometry; no engine.

CANDIDATE_FAMILIES = {
    "HARVEST": {"weakness_harvest"},
    "OUTPOST": {"outpost_occupation", "blockade"},
    "KEEP IT ENTOMBED": {"seal_to_entomb", "entomb"},
    "ESCAPE": {"bad_bishop_escape", "bad_bishop_trade"},
    "MINORITY ATTACK": {"minority_attack", "minority_attack_general"},
    "STORM": {"pawn_storm"},
    "BREAK OPEN THE CENTER": {"center_break_vs_king"},
    "DENY CASTLING": {"deny_castling"},
    "PUSH THE PASSER": {"passer_push", "passer_creation"},
    "ATTACK THE PASSER": {"attack_passer"},
    "ROOK ACTIVATION": {"rook_activation"},
    "BREAK THE BISHOP PAIR": {"pair_break"},
    "FREE THE BACKWARD PAWN": {"backward_push"},
    "FREE THE BAD BISHOP": {"free_bad_bishop"},
    "EXCHANGE THE BAD BISHOP": {"exchange_bad_bishop"},
    "KNIGHT TO": {"strong_outpost"},
    "CASTLE KINGSIDE": {"castle_kingside"},
    "CASTLE QUEENSIDE": {"castle_queenside"},
    "ATTACK THE OVEREXTENDED PAWN": {"harvest_overextended"},
    # 2026-07-22 breadth pass — reliability lines pending the v5 audit
    "ATTACK THE CHAIN BASE": {"chain_base_attack"},
    "FIX AND ATTACK": {"fix_then_attack"},
    "ROLL THE MAJORITY": {"majority_roll"},
    "ROOK LIFT": {"rook_lift"},
    "DOUBLE ON THE FILE": {"heavy_battery"},
    "TRADE INTO THE ENDGAME": {"trade_into_endgame"},
    "REMOVE THE DEFENDER": {"remove_defender"},
    "SQUEEZE": {"bind_squeeze"},
    "BLOCK THE MINORITY ATTACK": {"minority_block"},
    "ALTERNATE WEAKNESSES": {"alternation"},
    "PIECE ATTACK ON THE KING": {"piece_attack"},
}


def candidate_family(head: str) -> set[str]:
    """The plan_diff family/families a candidate `head` maps to, or an
    empty set for ADVISORY-tier candidates (SIMPLIFY, AVOID TRADES, the
    literature weakness matrix, PROPHYLAXIS/DEFEND) that carry no engine
    contract. Longest-key-first so 'BREAK OPEN THE CENTER' isn't shadowed
    by a shorter prefix. Used by the verify gate: a candidate with a
    family must be CONFIRMED against rolled lines before it can be
    surfaced as a plan (user ruling 2026-07-22: SUGGEST alone is useless
    — never present an unverified engine-contract plan)."""
    for key in sorted(CANDIDATE_FAMILIES, key=len, reverse=True):
        if head.startswith(key):
            return CANDIDATE_FAMILIES[key]
    return set()


def execution_report(b: chess.Board, moves: list[chess.Move],
                     horizon: int = 60) -> list[str]:
    from plan_diff import parse_line
    executed = parse_line(b, moves, horizon=horizon, tail=6)
    by_side = {"W": {}, "B": {}}
    for pl in executed:
        by_side[pl["side"]].setdefault(pl["name"], pl["stage"])
    L = [f"== EXECUTION DELTA (over {min(len(moves), horizon)} plies) =="]
    for t in ("W", "B"):
        found = by_side[t]
        verdicts = []
        for label, fams in CANDIDATE_FAMILIES.items():
            hits = {f: found[f] for f in fams if f in found}
            if hits:
                verdicts.append(f"{label}: EXECUTED "
                                + ", ".join(f"{f}[{st}]" for f, st in hits.items()))
        extra = {f for f in found if not any(f in v for v in
                                             CANDIDATE_FAMILIES.values())}
        line = f"  {name_side(t)}: " + ("; ".join(verdicts) if verdicts
                                        else "no candidate plan executed")
        if extra:
            line += " | also: " + ", ".join(sorted(extra))
        L.append(line)
    return L


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
    if "--verify" in sys.argv:
        # Roll once, up front, through the research harness (the library
        # itself never rolls — the (fen, pvs, rolls) contract). Horizon 40
        # covers the slowest family (alternation).
        import os
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "research", "experiments", "tools"))
        from rolls import roll_both
        bank = roll_both(b.fen(), 40)
        print(suggest_verified(b, bank.get("pvs"), bank.get("rolls")))
    else:
        print(suggest(b))
