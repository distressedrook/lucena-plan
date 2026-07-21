"""Static structure recognizers — the pawn-skeleton catalog from theory
(Soltis pawn-structure families / Flores Rios "Chess Structures").

Every structure is written ONCE, in its White-owner form, as a predicate over
(own, opp) pawn square-name sets. The Black-owned version is checked by
mirroring both sets (a2 <-> a7). "Owner" = the side the theory names the
structure for (the minority side in the Carlsbad, Black in the Sicilian
families -> its White form is the reversed/English version, etc.).

classify(board) returns [(name, owner_color), ...] for all matches.
Corpus validation: experiments/validate_structures.py (frequency + ECO
fingerprint per structure — a wrong definition shows up as a wrong ECO list).
"""
from __future__ import annotations

import chess

# ---------------------------------------------------------------- helpers

def pawn_sets(b: chess.Board) -> tuple[set[str], set[str]]:
    return ({chess.square_name(s) for s in b.pieces(chess.PAWN, chess.WHITE)},
            {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.BLACK)})


def mirror(sqs: set[str]) -> set[str]:
    return {s[0] + str(9 - int(s[1])) for s in sqs}


def file_of(sqs: set[str], f: str) -> set[str]:
    return {s for s in sqs if s[0] == f}


def no_file(sqs: set[str], f: str) -> bool:
    return not file_of(sqs, f)


# ------------------------------------------------- predicates (White-owner)
# own / opp are square-name sets; the predicate states the WHITE version.

def carlsbad(own, opp):
    """QGD-Exchange skeleton; owner = the minority side."""
    return ("d4" in own and no_file(own, "c")
            and "c6" in opp and "d5" in opp and no_file(opp, "e"))


def isolani(own, opp):
    """Owner has the isolated queen's pawn (d-pawn, no c/e); opp no d-pawn."""
    return (bool(file_of(own, "d")) and no_file(own, "c") and no_file(own, "e")
            and no_file(opp, "d")
            and bool(file_of(opp, "c") or file_of(opp, "e")))


def hanging_pawns(own, opp):
    """Owner's c4+d4 pair with open b/e files; opp no c/d pawns."""
    return ("c4" in own and "d4" in own
            and no_file(own, "b") and no_file(own, "e")
            and no_file(opp, "c") and no_file(opp, "d"))


def french_advance(own, opp):
    """The d4-e5 chain against d5-e6; owner = the space side."""
    return ("d4" in own and "e5" in own and "d5" in opp and "e6" in opp)


def advance_caro(own, opp):
    """French-advance chain with opp's ...c6 (Advance Caro-Kann shape)."""
    return french_advance(own, opp) and "c6" in opp


def mar_del_plata(own, opp):
    """Closed KID center: d5+e4 vs d6+e5; owner = the d5 space side."""
    return ("d5" in own and "e4" in own and "d6" in opp and "e5" in opp)


def benoni(own, opp):
    """Owner's d5 wedge vs c5+d6, opp's e-pawn gone (Modern Benoni)."""
    return ("d5" in own and "c5" in opp and "d6" in opp and no_file(opp, "e"))


def maroczy_bind(own, opp):
    """c4+e4 bind, own d-pawn traded; opp Sicilian small center d6, no c."""
    return ("c4" in own and "e4" in own and no_file(own, "d")
            and "d6" in opp and no_file(opp, "c"))


def hedgehog(own, opp):
    """Owner = the hedgehog side (White form = reversed/English hedgehog):
    a3+b3+d3+e3 crouch, no c-pawn, against opp's c5."""
    return ({"a3", "b3", "d3", "e3"} <= own and no_file(own, "c")
            and "c5" in opp)


def open_sicilian(own, opp):
    """Owner = the Sicilian side, Scheveningen shape (Black: d6+e6, no c-pawn,
    vs e4 with White's d-pawn traded). Written in White-owner (reversed) form."""
    return (no_file(own, "c") and "d3" in own and "e3" in own
            and "e5" in opp and no_file(opp, "d") and "c5" not in opp)


def boleslavsky_wall(own, opp):
    """Owner = the d6+e5 side (White form: d3+e4 vs opp e5-less...):
    white form own d3+e4, no c; opp e-pawn on e5 traded -> opp no e,
    opp d-pawn present? Classic: ...d6+e5 vs e4, hole on d5. White form:
    d3+e4? -- keep canonical: own d3,e4 no c-pawn; opp no d-pawn."""
    return (no_file(own, "c") and "d3" in own and "e4" in own
            and no_file(opp, "d") and bool(file_of(opp, "e")))


def stonewall(own, opp):
    """Owner's d4+e3+f4 wall against a fixed d5."""
    return ({"d4", "e3", "f4"} <= own and "d5" in opp)


def grunfeld_center(own, opp):
    """Owner's full d4+e4 center; opp traded the d-pawn and hits it from
    afar (has a c-pawn, no central rams)."""
    return ("d4" in own and "e4" in own and no_file(opp, "d")
            and "e5" not in opp and bool(file_of(opp, "c")))


def spanish_center(own, opp):
    """The e4+d4 vs e5+d6 tension center (closed Ruy / Italian / Philidor)."""
    return ("d4" in own and "e4" in own and "e5" in opp and "d6" in opp)


def slav_triangle(own, opp):
    """Owner's c3+d4+e3 triangle vs opp d5 with c-pawn (White form = Colle/
    semi-Slav reversed; Black form = the Noteboom/semi-Slav triangle)."""
    return ({"c3", "d4", "e3"} <= own and "d5" in opp
            and bool(file_of(opp, "c")))


STRUCTURES = {
    "carlsbad": carlsbad,
    "isolani": isolani,
    "hanging_pawns": hanging_pawns,
    "french_advance": french_advance,
    "advance_caro": advance_caro,
    "mar_del_plata": mar_del_plata,
    "benoni": benoni,
    "maroczy_bind": maroczy_bind,
    "hedgehog": hedgehog,
    "open_sicilian": open_sicilian,
    "boleslavsky_wall": boleslavsky_wall,
    "stonewall": stonewall,
    "grunfeld_center": grunfeld_center,
    "spanish_center": spanish_center,
    "slav_triangle": slav_triangle,
}


def classify_sets(wp: set[str], bp: set[str]) -> list[tuple[str, bool]]:
    out = []
    mw, mb = mirror(bp), mirror(wp)      # black-owner view
    for name, pred in STRUCTURES.items():
        if pred(wp, bp):
            out.append((name, chess.WHITE))
        if pred(mw, mb):
            out.append((name, chess.BLACK))
    return out


def classify(b: chess.Board) -> list[tuple[str, bool]]:
    wp, bp = pawn_sets(b)
    return classify_sets(wp, bp)
