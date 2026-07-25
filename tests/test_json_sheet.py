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
