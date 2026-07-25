"""preroll — the PRE phase's feature scan, for the interactive loading
(owner 2026-07-25: "two phases to analysis: 1. Pre — detect all the
structures. 2. Roll — detect all the plans. I want the loading to be
interactive... as we analyze pawn structure, all the pawns must get
highlighted; as we analyze outposts, all the outposts..." ).

`features(fen)` returns the ordered list of detected features, each with the
SQUARES the app highlights while that stage is on screen:

    [{"stage": "pawns", "label": "Pawn structure", "squares": ["e4", ...]},
     ...]

Pure geometry — milliseconds, no engine, no rolls. Empty stages are skipped
(a position with no passers never says "Passed pawns"). The label voice
follows the coach ruling: the term, nothing else.
"""
from __future__ import annotations

import chess

from structures import classify
from suggest import holes_in, name_side


def _sq(sqs) -> list[str]:
    return sorted(chess.square_name(s) for s in sqs)


def features(fen: str) -> list[dict]:
    b = chess.Board(fen)
    out: list[dict] = []

    def add(stage: str, label: str, squares: list[str]) -> None:
        if squares:
            out.append({"stage": stage, "label": label,
                        "squares": sorted(set(squares))})

    # 1. pawn structure — every pawn; named when the catalog knows it
    pawns = _sq(b.pieces(chess.PAWN, chess.WHITE)) \
        + _sq(b.pieces(chess.PAWN, chess.BLACK))
    named = classify(b)
    label = "Pawn structure"
    if named:
        nm, owner = named[0]
        label = f"Pawn structure — {nm.replace('_', ' ')} ({name_side(owner)})"
    add("pawns", label, pawns)

    # 2. passed pawns
    from lucena_core.geometry import passers
    add("passers", "Passed pawns",
        _sq(passers(b, chess.WHITE)) + _sq(passers(b, chess.BLACK)))

    # 3. outposts & holes — the IMPORTANT ones only (same cut as the sheet:
    # rim/shallow are noise; a hole speaks when enemy-usable). Occupied
    # outposts come from their own detector — holes_in() never returns an
    # occupied square (Codex 2026-07-25).
    from weaknesses import knight_route, occupied_outposts
    holes: list[str] = []
    for side in (chess.WHITE, chess.BLACK):
        holes += _sq(occupied_outposts(b, side))     # enemy minors planted
        for h, tag in holes_in(b, side):
            if tag:
                continue
            sq = chess.parse_square(h)
            if b.attackers(not side, sq) or knight_route(b, not side, {sq}):
                holes.append(h)
    add("outposts", "Outposts & holes", holes)

    # 4. bishops — bad and entombed (home-square bishops are merely
    # undeveloped, not bad — the development stage owns them; and only
    # INSIDE-the-chain bad bishops light up, 2026-07-25 — an outside bishop
    # measures 0.517 vs 0.470 and is not a weakness to spotlight)
    from weaknesses import entombed_bishops, bad_bishop_problem
    _home = {chess.C1, chess.F1, chess.C8, chess.F8}
    bish: list[str] = []
    for side in (chess.WHITE, chess.BLACK):
        bish += _sq(s for s in entombed_bishops(b, side) if s not in _home)
        bish += _sq(s for s in bad_bishop_problem(b, side) if s not in _home)
    add("bishops", "Bishops", bish)

    # 5. weak color complexes
    from weaknesses import weak_color_complex
    cc: list[str] = []
    for side in (chess.WHITE, chess.BLACK):
        cc += _sq(weak_color_complex(b, side))
    add("color_complex", "Weak color complexes", cc)

    # 6. king safety — both kings' zones
    from lucena_core.geometry import king_zone
    kz: list[str] = []
    for side in (chess.WHITE, chess.BLACK):
        k = b.king(side)
        if k is not None:
            kz += [chess.square_name(s) for s in king_zone(k, side)]
    add("kings", "King safety", kz)

    # 7. development — minors still on their OWN original squares, WHENEVER
    # they exist (owner 2026-07-25: development is ply-independent geometry,
    # not phase-gated — a lagging side's home piece must light up even once
    # it's a middlegame for the developed opponent). One definition for the
    # whole stack: lucena_core.reads.development_debts, which is keyed by
    # piece type (a bishop on b1 is developed, not "home"). add() no-ops on
    # an empty list.
    from lucena_core.reads import development_debts
    home = [m[1:] for side in (chess.WHITE, chess.BLACK)
            for m in development_debts(b, side)["minors"]]
    add("development", "Development", home)

    return out
