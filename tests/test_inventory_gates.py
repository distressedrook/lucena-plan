"""Clutter gates (owner 2026-07-25): "bringing up all the holes is what is
cluttering information" / "breaks too — only the relevant ones after the roll
must get presented."

HOLES in the weakness lines: rim and shallow dropped (corpus: 0.496/0.509 —
noise), occupied ones owned by the anchored-piece line, and a deep hole speaks
only when the enemy can use it (attacks it now or a knight route reaches it).
BREAKS in the metrics block: with lines supplied, a break survives only if its
push occurs in an eval-equal engine line or a Maia roll; the full inventory
stays only for the line-less research path.
"""

import chess

import fact_sheet as F


def test_breaks_are_line_gated():
    # a GM position with two White breaks (f3-f4 and b4-b5); give lines that
    # contain exactly one of them.
    fen = "6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32"
    full = F._metrics_block(fen)["breaks"]
    all_w = {r["pawn"] + r["push"] for r in full["white"]}
    assert all_w == {"f3f4", "b4b5"}
    pick = "b4b5"
    pvs = [{"cp": 20, "ucis": [pick, "c6b5"]},
           {"cp": 15, "ucis": ["f1e2"]}]
    gated = F._metrics_block(fen, pvs, None)["breaks"]
    kept = {r["pawn"] + r["push"] for r in gated["white"]}
    assert kept == {pick}                        # only the line-confirmed one
    # no lines -> full inventory (research path unchanged)
    assert {r["pawn"] + r["push"]
            for r in F._metrics_block(fen)["breaks"]["white"]} == all_w


def test_break_survives_via_maia_rolls_alone():
    fen = "6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32"
    pvs = [{"cp": 20, "ucis": ["f1e2"]}]         # no break in the engine lines
    rolls = [["b4b5", "c6b5"]]                   # ...but the roll plays one
    kept = {r["pawn"] + r["push"]
            for r in F._metrics_block(fen, pvs, rolls)["breaks"]["white"]}
    assert kept == {"b4b5"}


def test_break_pv_at_exactly_the_60cp_band_is_included():
    fen = "6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32"
    pvs = [{"cp": 20, "ucis": ["f1e2"]},
           {"cp": -40, "ucis": ["f3f4"]}]        # best-60 exactly: still equal
    kept = {r["pawn"] + r["push"]
            for r in F._metrics_block(fen, pvs, None)["breaks"]["white"]}
    assert kept == {"f3f4"}
    pvs[1]["cp"] = -41                           # one past the band: dropped
    assert F._metrics_block(fen, pvs, None)["breaks"]["white"] == []


def test_break_beyond_the_14_ply_window_is_excluded():
    fen = "6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32"
    filler = ["f1e2"] * 14                       # membership is by uci string
    pvs = [{"cp": 20, "ucis": filler + ["b4b5"]}]   # the break is ply 15
    assert F._metrics_block(fen, pvs, None)["breaks"]["white"] == []
    pvs = [{"cp": 20, "ucis": filler[:13] + ["b4b5"]}]  # ply 14: included
    kept = {r["pawn"] + r["push"]
            for r in F._metrics_block(fen, pvs, None)["breaks"]["white"]}
    assert kept == {"b4b5"}


def test_holes_line_keeps_only_usable_deep_holes():
    from lucena_core import positional as P
    from lucena_core.board import Board as LB
    # a position with rim + shallow + deep holes on the White side
    fen = "r2q1rk1/pp3ppp/2n1bn2/2bp4/8/1PN2NP1/PB2PPBP/R2Q1RK1 w - - 0 11"
    b = chess.Board(fen)
    terms = P.analyze_positional(LB(fen))["terms"]
    lines = F._weakness_lines(b, terms, chess.WHITE)
    hole_lines = [l for l in lines if l.startswith("Holes")]
    if hole_lines:                               # when it speaks, it is terse
        body = hole_lines[0]
        assert "low value" not in body and "shallow" not in body
        assert body.count(",") <= 2              # cap 3 squares


def test_gating_survives_an_empty_first_pv():
    # Codex P1: an empty-ucis first PV must not disable the gate when later
    # PVs carry real lines.
    fen = "6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32"
    pvs = [{"cp": 20, "ucis": []},
           {"cp": 18, "ucis": ["b4b5", "c6b5"]}]
    kept = {r["pawn"] + r["push"]
            for r in F._metrics_block(fen, pvs, None)["breaks"]["white"]}
    assert kept == {"b4b5"}


def test_out_of_band_lines_gate_to_empty_not_ungated():
    # Codex P1 round 2: usable PVs that all fall OUTSIDE the eval-equal band
    # must still gate (to empty) — never fall back to the full inventory.
    fen = "6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32"
    pvs = [{"cp": 100, "ucis": []},
           {"cp": 0, "ucis": ["b4b5", "c6b5"]}]   # 100cp off the anchor
    assert F._metrics_block(fen, pvs, None)["breaks"]["white"] == []
