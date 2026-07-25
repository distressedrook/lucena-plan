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
    # Black's c8 bishop IS inside the chain — still named, with its door.
    assert any("bishop on c8" in w for w in sides["black"]["weaknesses"])


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
