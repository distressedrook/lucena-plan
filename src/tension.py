"""tension — central pawn tension detection + what each resolution DOES,
read from the banked engine/Maia lines (user ruling 2026-07-22: everything
is banked; without the bank it's nonsense, so we read the ACTUAL resolution
and its ACTUAL resulting structure, never a guessed recapture).

A central tension = a White and Black pawn on adjacent central files (c-f)
in mutual diagonal capture contact (d4 vs e5). Three ways to discharge it
(see research/experiments/center_tension_theory.md):
  KEEP    the tension persists — flexibility
  LOCK    a central pawn pushes past, closing the centre (d4-d5)
  RESOLVE a central capture (dxe5)

`analyze(fen, pvs, rolls)` walks every banked line, classifies which mode
it took, and for each mode that occurs describes the RESULTING position
with the ordinary geometry detectors (holes / strong squares / open files
/ bad bishop) — so "what locking does here" is computed from the real
post-lock board, not recited.
"""
from __future__ import annotations

import chess

from weaknesses import (side_rank, is_hole, bad_bishop_problem,
                        strong_squares)

CENTRAL_FILES = {2, 3, 4, 5}   # c d e f


def central_tension(b: chess.Board) -> list[tuple[int, int]]:
    """(white_pawn_sq, black_pawn_sq) pairs in mutual central capture
    contact — the cocked levers."""
    out = []
    for wp in b.pieces(chess.PAWN, chess.WHITE):
        for df in (-1, 1):
            bp = wp + 8 + df           # the square a white pawn attacks
            if 0 <= bp < 64 and abs(chess.square_file(bp)
                                    - chess.square_file(wp)) == 1:
                pc = b.piece_at(bp)
                if pc and pc.piece_type == chess.PAWN and pc.color == chess.BLACK:
                    # central iff EITHER pawn is on a central file (2026-07-24
                    # fix): gating on the White pawn's file alone missed the
                    # color-mirror (White b4 vs Black c5) while including a
                    # non-central Black pawn (White c4 vs Black b5).
                    if (chess.square_file(wp) in CENTRAL_FILES
                            or chess.square_file(bp) in CENTRAL_FILES):
                        out.append((wp, bp))
    return out


def _central_pawns(b):
    return {sq for c in (chess.WHITE, chess.BLACK)
            for sq in b.pieces(chess.PAWN, c)
            if chess.square_file(sq) in CENTRAL_FILES}


def classify_line(fen: str, ucis: list[str],
                  horizon: int = 12) -> dict | None:
    """Walk a banked line; return how it FIRST discharges the central
    tension present at the start: {mode, move (san), res_fen (position
    right after the discharge)} — or {mode:'keep'} if the tension survives
    the horizon. None if there was no central tension to begin with."""
    b = chess.Board(fen)
    pairs0 = central_tension(b)
    if not pairs0:
        return None
    # Track ALL the ORIGINAL pair(s) by SQUARE IDENTITY, not "any tension
    # exists on the board": pushing d5-d4 dissolves e4-vs-d5 correctly
    # even though it immediately creates a fresh c3-vs-d4 contact
    # elsewhere — checking "is there ANY tension left" missed the real
    # resolution and mislabeled a later, unrelated capture instead
    # (2026-07-22 finding). A pair is intact iff its white square still
    # holds a White pawn AND its black square still holds a Black pawn.
    # 2026-07-24 fix: track EVERY original pair, not just pairs0[0] — a line
    # discharging any OTHER central tension was mislabeled "keep".
    tracked = list(pairs0)
    tracked_sqs = {sq for pr in tracked for sq in pr}

    def intact(bd, w, bl):
        pw = bd.piece_at(w)
        pb = bd.piece_at(bl)
        return (pw is not None and pw.piece_type == chess.PAWN
                and pw.color == chess.WHITE
                and pb is not None and pb.piece_type == chess.PAWN
                and pb.color == chess.BLACK)

    for i, u in enumerate(ucis[:horizon]):
        mv = chess.Move.from_uci(u)
        san = b.san(mv)
        is_cap = b.is_capture(mv)
        mover = "White" if b.turn == chess.WHITE else "Black"
        touches = mv.from_square in tracked_sqs or mv.to_square in tracked_sqs
        b.push(mv)
        if touches:
            # the FIRST original pair this move breaks is the discharge
            for w, bl in tracked:
                if (mv.from_square in (w, bl) or mv.to_square in (w, bl)) \
                        and not intact(b, w, bl):
                    mode = "resolve" if is_cap else "lock"
                    return {"mode": mode, "move": san, "mover": mover,
                            "res_fen": b.fen()}
    return {"mode": "keep", "move": None, "mover": None, "res_fen": b.fen()}


def _describe_result(before_fen: str, after_fen: str, side: bool) -> list[str]:
    """Concrete structural consequences of a resolution: the delta in
    holes / strong squares / open files between the position now and the
    position after the resolution — computed, not recited."""
    a = chess.Board(before_fen)
    c = chess.Board(after_fen)
    out = []
    # open files created
    def open_files(bd):
        wf = {chess.square_file(p) for p in bd.pieces(chess.PAWN, chess.WHITE)}
        bf = {chess.square_file(p) for p in bd.pieces(chess.PAWN, chess.BLACK)}
        return {f for f in range(8) if f not in wf and f not in bf}
    new_open = open_files(c) - open_files(a)
    if new_open:
        out.append("opens the " + "/".join(chess.FILE_NAMES[f]
                   for f in sorted(new_open)) + "-file")
    # new holes conceded in each camp (squares each side can aim at)
    def holes(bd, camp):
        return {sq for sq in chess.SQUARES if not bd.piece_at(sq)
                and 3 <= side_rank(sq, not camp) <= 5
                and 1 <= chess.square_file(sq) <= 6
                and is_hole(bd, sq, camp)}
    for camp, nm in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
        new_h = holes(c, camp) - holes(a, camp)
        if new_h:
            out.append(f"concedes {nm} a hole on "
                       + ",".join(sorted(chess.square_name(s)
                                         for s in new_h)))
    # bad bishop created/relieved for the side to move. The PROBLEM set
    # (inside the chain), not the raw detector — this line is user-facing
    # prose, and "leaves White with a bad bishop" must not fire for a bishop
    # that merely ends up outside its chain (2026-07-25; finding 4: outside
    # 0.517 vs inside 0.470).
    bb_before = set(bad_bishop_problem(a, side))
    bb_after = set(bad_bishop_problem(c, side))
    who = "White" if side == chess.WHITE else "Black"
    if bb_after - bb_before:
        out.append(f"leaves {who} with a bad bishop")
    elif bb_before - bb_after:
        out.append(f"frees {who}'s bishop")
    return out


def analyze(fen: str, pvs: list | None, rolls: list | None) -> dict | None:
    """The teaching object for the central tension in `fen`, read from the
    banked lines. Returns None if there is no central tension."""
    b = chess.Board(fen)
    pairs = central_tension(b)
    if not pairs:
        return None
    side = b.turn
    desc = ", ".join(f"{chess.square_name(w)} vs {chess.square_name(bl)}"
                     for w, bl in pairs)
    modes = {"keep": 0, "lock": 0, "resolve": 0}
    examples = {}          # mode -> (move, [consequence strings])
    eng_modes = []
    for src, lines in (("eng", [p["ucis"] for p in (pvs or [])]),
                       ("maia", rolls or [])):
        for ucis in lines:
            r = classify_line(fen, ucis)
            if not r:
                continue
            modes[r["mode"]] += 1
            if src == "eng":
                eng_modes.append(r["mode"])
            if r["mode"] not in examples and r["mode"] != "keep":
                examples[r["mode"]] = {
                    "move": r["move"], "mover": r["mover"],
                    "consequences": _describe_result(fen, r["res_fen"], side)}
    return {"tension": desc, "side": "White" if side else "Black",
            "modes": modes, "eng_modes": eng_modes, "examples": examples}


def render(a: dict) -> list[str]:
    """The CENTER TENSION fact-sheet section: the static 3-way choice, then
    what the BANKED lines actually do here (recommendation + the computed
    consequence of each mode that occurs)."""
    if a is None:
        return []
    L = [f"CENTRAL TENSION ({a['tension']}) — {a['side']} to move must "
         "choose how to handle it:"]
    em = a["eng_modes"]
    if not em:
        # no engine lines supplied (Maia-only bank): do NOT fabricate an
        # engine recommendation from zero lines (2026-07-24 fix — the old
        # `n = len(em) or 1` printed "engine's best lines KEEP (0/1)").
        L.append("  (No engine lines supplied for this position — the "
                 "engine's tension preference is unavailable here.)")
        return L
    n = len(em)
    tally = {m: em.count(m) for m in ("keep", "lock", "resolve")}
    best = max(tally, key=tally.get)
    verb = {"keep": "KEEP the tension (maintain the flexibility)",
            "lock": "LOCK the centre (push a central pawn past)",
            "resolve": "RESOLVE it (capture in the centre)"}
    L.append(f"  Best play most often {verb[best]} "
             f"({tally[best]}/{n} of them).")
    if tally["keep"]:
        L.append("  - KEEP: keeps both capture options and the push open; "
                 "makes the opponent solve more problems. Strong when you "
                 "have more good resolutions available than they do.")
    for mode in ("lock", "resolve"):
        if mode in a["examples"]:
            ex = a["examples"][mode]
            cons = ("; ".join(ex["consequences"])
                    if ex["consequences"] else "no structural change of note")
            label = "LOCK" if mode == "lock" else "RESOLVE"
            L.append(f"  - {label} ({ex['mover']} plays {ex['move']}): {cons}.")
        elif tally[mode] == 0:
            label = "LOCK" if mode == "lock" else "RESOLVE"
            L.append(f"  - {label}: no strong line does this here — a sign "
                     "it eases the opponent's game in this structure.")
    return L
