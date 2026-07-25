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
    # undeveloped, not bad — the development stage owns them)
    from weaknesses import entombed_bishops, bad_bishop
    _home = {chess.C1, chess.F1, chess.C8, chess.F8}
    bish: list[str] = []
    for side in (chess.WHITE, chess.BLACK):
        bish += _sq(s for s in entombed_bishops(b, side) if s not in _home)
        bish += _sq(s for s in bad_bishop(b, side) if s not in _home)
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

    # 7. development — home minors, opening only
    from lucena_core.reads import game_phase
    if game_phase(fen)["phase"] == "opening":
        home: list[str] = []
        for side, back in ((chess.WHITE, 0), (chess.BLACK, 7)):
            home += [chess.square_name(s)
                     for pt in (chess.KNIGHT, chess.BISHOP)
                     for s in b.pieces(pt, side)
                     if chess.square_rank(s) == back]
        add("development", "Development", home)

    return out
