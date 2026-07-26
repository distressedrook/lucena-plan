"""Golden-ish structural tests for the JSON product sheet (the live path).

Locks the FEN-redaction invariant (#12), the details/route_note fix (#13), the
schema keys, and run-to-run determinism (#14). Uses a small canned {pvs, rolls}
bank so no engine is needed.
"""
import json

import chess
import pytest

from fact_sheet import post_verify_json, pre_verify_json

FEN = "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R1BQ1RK1 w - - 0 8"
PVS = [{"cp": 20, "ucis": ["c4d5", "e6d5", "c1d2"]},
       {"cp": 25, "ucis": ["f1e1", "f8e8", "h2h3"]}]
ROLLS = [["c4d5", "e6d5"], ["f1e1", "f8e8"], ["a2a3", "a7a6"]]


def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_strings(v)


def _looks_like_board(s):
    return " " in s and s.split(" ", 1)[0].count("/") == 7


# ---- #12 no FEN anywhere in the artifact -------------------------------

@pytest.mark.parametrize("builder", [pre_verify_json, post_verify_json])
def test_no_fen_leak(builder):
    out = builder(FEN, PVS, ROLLS)
    assert "fen" not in out
    board = FEN.split()[0]
    blob = json.dumps(out)
    assert board not in blob
    # and no OTHER board string (quiescence walks) survived the scrub
    assert not [s for s in _all_strings(out) if _looks_like_board(s)]


def test_id_is_opaque():
    out = post_verify_json(FEN, PVS, ROLLS)
    assert out["id"].startswith("POSITION-")


# ---- schema + plan-entry keys (#13) ------------------------------------

def test_plan_entries_carry_line_derived_keys():
    out = post_verify_json(FEN, PVS, ROLLS)
    plans = out["plans"]["white"] + out["plans"]["black"]
    assert plans, "expected some plan candidates"
    for p in plans:
        for k in ("families", "family", "details", "routes", "route_note",
                  "verified", "verdict"):
            assert k in p, k
    # a confirmed plan that produced line details must not keep a geometric
    # route_note (specifics come from the lines, not geometry)
    for p in plans:
        if p["verified"] and (p["details"] or p["routes"]):
            assert p["route_note"] is None


# ---- #14 determinism ----------------------------------------------------

def test_deterministic():
    a = post_verify_json(FEN, PVS, ROLLS)
    b = post_verify_json(FEN, PVS, ROLLS)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_only_enemy_trapped_pieces_reach_the_side_report():
    """TRAPPED is the ENEMY's doing (owner 2026-07-25: "why is Ra8 being
    tagged as trapped? ... they can move, right?"). On move 1 every rook,
    bishop and queen has zero safe moves — blocked by its OWN army — so the
    metric lists them all; the side report must surface none of them. A piece
    the enemy actually catches still comes through."""
    import chess
    from fact_sheet import pre_verify_json
    from lucena_core.metrics import trapped_pieces

    assert trapped_pieces(chess.STARTING_FEN)["black"]          # metric: yes
    sides = pre_verify_json(chess.STARTING_FEN, None, None)["sides"]
    assert sides["white"]["trapped"] == []                      # report: no
    assert sides["black"]["trapped"] == []

    # Bxa7 met by ...b6 — b8 and b6 covered, bishop attacked where it stands.
    fen = "rn1qkbnr/B1p1pppp/1p6/8/8/8/PPPPPPPP/RNBQK1NR b KQkq - 0 4"
    caught = pre_verify_json(fen, None, None)["sides"]["white"]["trapped"]
    assert [e["square"] for e in caught] == ["a7"]


def test_an_outside_bishop_is_not_a_bad_bishop():
    """QGD 7.Bh4 (owner 2026-07-25: "why is the bishop on h4 bad?"). Five of
    White's eight pawns sit on dark squares and the bishop's mobility lands
    exactly on the 2.5 bar, so the raw `bad_bishop` detector fires — but the
    bishop is developed, OUTSIDE its chain and pressing f6/e7. Finding 4
    measured that split: inside 0.470, outside 0.517 (no penalty at all), so
    nothing user-facing may call it bad, and neither cure plan may fire for
    it. An inside bishop still gets named."""
    import chess
    from fact_sheet import pre_verify_json
    from weaknesses import bad_bishop, bad_bishop_problem

    b = chess.Board()
    for m in "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bh4".split():
        b.push_san(m)
    assert chess.H4 in bad_bishop(b, chess.WHITE)            # detector: yes
    assert bad_bishop_problem(b, chess.WHITE) == []          # presentation: no

    sides = pre_verify_json(b.fen(), None, None)["sides"]
    assert not any("bishop on h4" in w for w in sides["white"]["weaknesses"])
    assert not any("BAD BISHOP" in p["idea"].upper()
                   for p in sides["white"]["plans"])
    # Black's c8 bishop is inside its chain — but at move 7, with the queen's
    # knight still on b8, Black is DEVELOPING, so it is not called bad either
    # (2026-07-26; see test_a_home_bishop_is_bad_only_when_it_is_the_last_one_out).
    assert not any("bishop on c8" in w for w in sides["black"]["weaknesses"])
    assert any("Bc8" in a["idea"] for a in sides["black"]["advisory"])


def test_the_space_bar_is_a_differential_not_a_share():
    """A share saturates the instant one side is at zero: after 1.Nf3 e5 the bar
    read 100% Black off a single pawn move, and after 1.e4 it read 100% White
    (owner 2026-07-26: "why is the space maxxed out for black in this
    position?"). It is a centered differential now, on the same scale the space
    badge is calibrated on — a raw lead of 2 is a real edge, so it nudges."""
    import chess
    from fact_sheet import pre_verify_json

    def space_bar(moves):
        b = chess.Board()
        for m in moves.split():
            b.push_san(m)
        bars = {bar["label"]: bar for bar in pre_verify_json(b.fen(), None, None)["bars"]}
        return bars.get("Space")

    one_pawn = space_bar("Nf3 e5")                  # White has moved no pawn at all
    assert one_pawn is not None
    assert 0.3 < one_pawn["value"] < 0.5            # off centre toward Black, nowhere near maxed
    assert space_bar("e4 e5")["value"] == 0.5       # symmetrical fronts: dead even
    assert 0.5 < space_bar("e4 Nf6")["value"] < 0.7  # White's one pawn: a nudge, not a rout


def test_a_home_bishop_is_bad_only_when_it_is_the_last_one_out():
    """Fried Liver, move 10 (owner 2026-07-26: "I am a bit skeptical about the
    claims on Black's bad bishops"). Black's Bc8 and Bf8 were both called bad
    and drew two FREE THE BAD BISHOP plans — pushing ...b6 and ...g6 in front of
    a king already sitting on e6 under fire. They are not bad bishops, they are
    pieces that have not moved; one ...c6 was all it took to flip them, by
    making the third light-square pawn.

    The discrimination is the development debt, not the square: the French
    light-squared bishop behind a fixed e6/d5 chain, with everything else
    already developed, IS the textbook bad bishop and still fires."""
    import chess
    from weaknesses import bad_bishop, bad_bishop_problem
    from fact_sheet import pre_verify_json

    fried = chess.Board("r1bq1b1r/pp2n1pp/2p1k3/3np1B1/2BP4/2N2Q2/PPP2PPP/R3K2R b KQ - 1 10")
    assert [chess.square_name(s) for s in bad_bishop(fried, chess.BLACK)] == ["c8", "f8"]
    assert bad_bishop_problem(fried, chess.BLACK) == []          # ...none surfaced
    black = pre_verify_json(fried.fen(), None, None)["sides"]["black"]
    assert not any("bishop" in w for w in black["weaknesses"])
    assert not any("BAD BISHOP" in p["idea"].upper() for p in black["plans"])
    # the development plan owns them, and says so by name
    assert any("Bc8" in a["idea"] and "Bf8" in a["idea"] for a in black["advisory"])

    # the real thing: everything out except the bishop, behind a fixed chain
    french = chess.Board("r1bq1rk1/pp1nbppp/2p1pn2/3pP3/3P4/2N2N2/PPP2PPP/R1BQ1RK1 b - - 0 10")
    assert [chess.square_name(s) for s in bad_bishop_problem(french, chess.BLACK)] == ["c8"]
    # ...but put one knight back on b8 and it is a developing position again
    developing = chess.Board("rnbq1rk1/pp2bppp/2p1p3/3pP3/3P4/2N2N2/PPP2PPP/R1BQ1RK1 b - - 0 10")
    assert bad_bishop_problem(developing, chess.BLACK) == []


def test_the_bad_bishop_plans_name_the_bishop():
    """Two bad bishops produced two identical plan lines — the reader could not
    tell which one either was about (2026-07-26)."""
    import chess
    from suggest import build_menus
    b = chess.Board("r1bq1rk1/pp1nbppp/2p1pn2/3pP3/3P4/2N2N2/PPP2PPP/R1BQ1RK1 b - - 0 10")
    heads = [h for _, _, h, _, _, _ in build_menus(b)["B"] if "BAD BISHOP" in h]
    assert heads and all("c8" in h for h in heads)
