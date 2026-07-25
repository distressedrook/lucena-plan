"""dynamism — a deterministic, objective sharpness rating for a position.

THE PROBLEM (2026-07-22, user): the sheet called a position 'quiet' purely
because the engine said 0.00 — but 0.00 spans everything from a dead
symmetric endgame to a razor-sharp mutual attack where one inaccuracy
loses. Evaluation measures WHO stands better; dynamism measures HOW MUCH
the position punishes the next mistake.

THE CONTRACT: (fen, pvs, rolls) — no rolling here, only reading. Every
component is deterministic given the same lines:

  NARROWNESS   (engine)  how few moves hold the position: the cp gap from
                         PV1 to PV2, and the count of eval-equal lines.
                         Placid equality holds ~3.4 equal lines; a lone
                         playable move at 0.00 is a knife edge.
  FORCINGNESS  (engine)  the density of checks + captures in the first 8
                         plies of the equal lines — a sharp 0.00 trades
                         blows in its own best play, a quiet one shuffles.
  DIVERGENCE   (maia)    how much strong humans scatter: distinct first
                         moves across the K rollouts, plus whether the
                         human top choice is even inside the engine's
                         equal set (humans wandering where the engine is
                         narrow = practical danger).
  GEOMETRY     (board)   standing tension: pawn tensions, SEE-positive
                         captures available, opposite-side castling,
                         passers on the 5th rank or beyond.

Score = sum of component points (each capped, documented inline) ->
bucket: DEAD / QUIET / DYNAMIC / SHARP / RAZOR. The bucket and the firing
components are returned so callers can SAY WHY ('sharp: only one move
holds, and the best lines are 60% checks and captures'), never just a
number.
"""
from __future__ import annotations

import chess

from plan_diff import _see

EQUAL_BAND = 50
_FORCING_PLIES = 8


def dynamism(fen: str, pvs: list | None, rolls: list | None) -> dict:
    """{score, bucket, components: [(name, pts, why)], summary}."""
    b = chess.Board(fen)
    comps: list[tuple[str, int, str]] = []

    # ---- NARROWNESS (0-4): pv1-pv2 gap + equal-line count
    if pvs and len(pvs) >= 2:
        gap = abs(pvs[0]["cp"] - pvs[1]["cp"])
        n_equal = sum(1 for p in pvs if abs(p["cp"] - pvs[0]["cp"]) <= EQUAL_BAND)
        pts = 0
        if gap >= 120:
            pts = 4
        elif gap >= 70:
            pts = 3
        elif gap >= 40:
            pts = 2
        elif n_equal <= 2:
            pts = 1
        if pts:
            why = ("essentially only one move holds the position"
                   if gap >= 120 else
                   "the second-best move already concedes ground"
                   if gap >= 70 else
                   "the top choices are not interchangeable")
            if n_equal <= 2:
                why += f" ({n_equal} playable choice"\
                       f"{'s' if n_equal > 1 else ''})"
            comps.append(("narrowness", pts, why))

    # ---- FORCINGNESS (0-4): checks/captures density in equal lines
    if pvs:
        cp1 = pvs[0]["cp"]
        equal = [p for p in pvs if abs(p["cp"] - cp1) <= EQUAL_BAND]
        forcing = total = 0
        for p in equal:
            cur = b.copy()
            for u in p["ucis"][:_FORCING_PLIES]:
                mv = chess.Move.from_uci(u)
                if cur.is_capture(mv) or cur.gives_check(mv):
                    forcing += 1
                total += 1
                cur.push(mv)
        if total:
            frac = forcing / total
            pts = 4 if frac >= 0.6 else 3 if frac >= 0.45 else \
                2 if frac >= 0.3 else 0
            if pts:
                comps.append(("forcing lines", pts,
                              f"{round(100 * frac)}% of the best lines' "
                              "opening moves are checks or captures"))

    # ---- DIVERGENCE (0-3): human scatter + human-vs-engine split
    if rolls:
        firsts = {r[0] for r in rolls if r}
        pts, whys = 0, []
        if len(firsts) >= 5:
            pts += 2
            whys.append(f"strong humans scatter across {len(firsts)} "
                        "different first moves")
        elif len(firsts) >= 3:
            pts += 1
            whys.append(f"strong humans split between {len(firsts)} "
                        "first moves")
        if pvs and firsts:
            cp1 = pvs[0]["cp"]
            eq_firsts = {p["ucis"][0] for p in pvs
                         if p["ucis"] and abs(p["cp"] - cp1) <= EQUAL_BAND}
            if not (firsts & eq_firsts):
                pts += 1
                whys.append("the typical human choice is not among the "
                            "engine's equal moves")
        if pts:
            comps.append(("human divergence", pts, "; ".join(whys)))

    # ---- IMBALANCE + COMPENSATION (0-5): asymmetric material, and the
    # sharpest signal of all — static material disagreeing with the
    # engine's verdict (someone's material deficit is being paid for by
    # initiative; that compensation must be USED, urgently, or it decays).
    _VAL = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
            chess.ROOK: 500, chess.QUEEN: 900}
    mat = sum(v * (len(b.pieces(pt, chess.WHITE))
                   - len(b.pieces(pt, chess.BLACK)))
              for pt, v in _VAL.items())
    imb, why_i = 0, []
    wB, bB = len(b.pieces(chess.BISHOP, chess.WHITE)), \
        len(b.pieces(chess.BISHOP, chess.BLACK))
    wN, bN = len(b.pieces(chess.KNIGHT, chess.WHITE)), \
        len(b.pieces(chess.KNIGHT, chess.BLACK))
    if wB != bB and wN != bN and (wB + wN) == (bB + bN):
        imb += 1
        why_i.append("a bishop-versus-knight imbalance")
    wR, bR = len(b.pieces(chess.ROOK, chess.WHITE)), \
        len(b.pieces(chess.ROOK, chess.BLACK))
    if wR != bR and (wB + wN) != (bB + bN):
        imb += 1
        why_i.append("an exchange-type imbalance")
    if len(b.pieces(chess.QUEEN, chess.WHITE)) != \
            len(b.pieces(chess.QUEEN, chess.BLACK)):
        imb += 2
        why_i.append("a queen imbalance")
    if pvs:
        # compensation off ADJUSTED material (2026-07-24 sharpness audit):
        # raw material reads a pending recapture as "compensation" — 51 of
        # 117 raw-gap fires on the benchmark were exactly that mirage, and
        # the SEE-quiescent count closes them. Only a gap that SURVIVES
        # the captures is initiative paying for material.
        from lucena_core.metrics import material_stability
        adj = material_stability(fen)["adjusted_cp"]
        comp_gap = abs(adj - pvs[0]["cp"])
        if comp_gap >= 160:
            imb += 3
            down = "White" if adj < pvs[0]["cp"] else "Black"
            why_i.append(f"{down} is materially behind yet the engine "
                         "calls it level — the deficit is paid for by "
                         "initiative, which must be used before it decays")
        elif comp_gap >= 90:
            imb += 2
            why_i.append("material and the engine's verdict disagree — "
                         "real compensation is on the board")
    if imb:
        comps.append(("imbalance", min(imb, 5), "; ".join(why_i)))

    # ---- KING EXPOSURE (0-2): airy kings make every eval provisional —
    # but only while the OTHER side still has the artillery to exploit it
    # (a queen, or two heavies); bare-king endgames are not 'exposed'.
    from weaknesses import exposed_king

    def _artillery(side: bool) -> bool:
        return bool(b.pieces(chess.QUEEN, side)) or \
            len(b.pieces(chess.ROOK, side)) >= 2
    xw = bool(exposed_king(b, chess.WHITE)) and _artillery(chess.BLACK)
    xb = bool(exposed_king(b, chess.BLACK)) and _artillery(chess.WHITE)
    if xw and xb:
        comps.append(("king exposure", 2, "both kings are exposed"))
    elif xw or xb:
        comps.append(("king exposure", 1,
                      ("White's" if xw else "Black's")
                      + " king is exposed"))

    # ---- ACTIVITY ASYMMETRY (0-1): one side's pieces far more mobile
    my_mob = b.legal_moves.count()
    nb = b.copy(stack=False)
    nb.turn = not nb.turn
    their_mob = 0 if nb.is_check() else nb.legal_moves.count()
    hi, lo = max(my_mob, their_mob), min(my_mob, their_mob)
    if their_mob and lo and hi >= 1.6 * lo and hi - lo >= 12:
        who = "White" if (my_mob > their_mob) == (b.turn == chess.WHITE) \
            else "Black"
        comps.append(("activity", 1,
                      f"{who}'s pieces have far more scope"))

    # ---- GEOMETRY (0-4): standing tension on the board itself
    geo, why_bits = 0, []
    # pawn tensions: white-pawn/black-pawn pairs a capture apart
    wp = b.pieces(chess.PAWN, chess.WHITE)
    bp = b.pieces(chess.PAWN, chess.BLACK)
    n_tension = sum(1 for p in wp for df in (-1, 1)
                    if 0 <= chess.square_file(p) + df <= 7
                    and p + 8 + df in bp and p + 8 + df < 64)
    if n_tension >= 2:
        geo += 1
        why_bits.append(f"{n_tension} pawn tensions stand unresolved")
    hot = sum(1 for sq in chess.SQUARES
              if (pc := b.piece_at(sq)) is not None
              and pc.color != b.turn
              and _see(b, sq, b.turn) > 0)
    if hot:
        geo += 1
        why_bits.append(f"{hot} favorable capture(s) are on the board")
    wk, bk = b.king(chess.WHITE), b.king(chess.BLACK)
    if wk is not None and bk is not None:
        wf, bf = chess.square_file(wk), chess.square_file(bk)
        if (wf <= 2 and bf >= 5) or (wf >= 5 and bf <= 2):
            geo += 1
            why_bits.append("the kings are castled on opposite wings")
    deep_passers = sum(
        1 for side in (chess.WHITE, chess.BLACK)
        for q in b.pieces(chess.PAWN, side)
        if (chess.square_rank(q) if side == chess.WHITE
            else 7 - chess.square_rank(q)) >= 4
        and not any(abs(chess.square_file(s) - chess.square_file(q)) <= 1
                    and ((7 - chess.square_rank(s)) if side == chess.WHITE
                         else chess.square_rank(s))
                    < (7 - chess.square_rank(q) if side == chess.WHITE
                       else chess.square_rank(q))
                    for s in b.pieces(chess.PAWN, not side)))
    if deep_passers:
        geo += 1
        why_bits.append(f"{deep_passers} passer(s) already past midboard")
    if geo:
        comps.append(("board tension", min(geo, 4), "; ".join(why_bits)))

    score = sum(p for _, p, _ in comps)
    bucket = ("RAZOR" if score >= 9 else "SHARP" if score >= 6 else
              "DYNAMIC" if score >= 3 else "QUIET" if score >= 1 else "DEAD")
    summary = {"RAZOR": "razor-sharp — one inaccuracy changes the verdict",
               "SHARP": "sharp — concrete and punishing",
               "DYNAMIC": "dynamic — real tension under the surface",
               "QUIET": "quiet — maneuvering, little forcing play",
               "DEAD": "placid — nothing forcing anywhere"}[bucket]
    return {"score": score, "bucket": bucket, "components": comps,
            "summary": summary}
