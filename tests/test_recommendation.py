"""The committed recommendation (owner ruling 2026-07-30: "I am OK with the
commit, as long as we tell the student why").

The block's contract, tested here without an engine:
  * the MOVE is pvs[0]'s first move, the WHY is a detected plan entry whose
    family the top line actually fires (plan_diff attribution);
  * no grounded why -> no recommendation (a bare move must never render);
  * pre-verify sheets never carry one;
  * the render speaks it as a line-level claim ("the strongest continuation
    pursues this plan"), and only when both move and why are present.

Measured basis for the feature: reading/LOG.md P11/P18 — naming the move is
+34pp for a weak reader; every wording short of it measures ~0. The ruling
gates that effect on honesty.
"""

import chess

import fact_sheet as F
import position_read as R

# A real benchmark position (n10017_a50) whose top engine line's first move
# puts the e3 rook on the open second rank / e-file complex and goes on to
# fire rook_activation under the grammar (plan_diff TAIL=6 satisfied by the
# banked 12-ply prefix). Frozen here so the test needs no bank access.
FEN = "2r3k1/2q1rpp1/3pb2p/pBn1p3/P3P1n1/1PB1R1P1/2QN1P1P/3R2K1 w - - 8 26"
PV1 = ["e3e2", "g4f6", "d1c1", "e6h3", "c2b1", "d6d5",
       "c3a5", "c7a5", "b3b4", "a5a7", "b4c5", "c8c5"]


def _pvs(*lines):
    return [{"cp": 30, "ucis": list(l)} for l in lines]


def test_recommendation_move_and_grounded_why():
    b = chess.Board(FEN)
    plans = {"white": [{"idea": "Rook activation: put a rook on the open file",
                        "family": "rook_activation", "families": [],
                        "verdict": "CONFIRMED-SOUND"}],
             "black": []}
    rec = F._recommendation_block(b, FEN, _pvs(PV1), plans)
    assert rec is not None
    assert rec["move"] == "Re2"
    assert rec["family"] == "rook_activation"
    assert rec["why"].startswith("Rook activation")


def test_no_matching_plan_entry_means_no_recommendation():
    b = chess.Board(FEN)
    # The line fires rook_activation but NO plan entry carries that family —
    # there is nothing verified to cite, so the ruling forbids committing.
    plans = {"white": [{"idea": "Something else", "family": "pair_break",
                        "families": [], "verdict": "CONFIRMED-SOUND"}],
             "black": []}
    assert F._recommendation_block(b, FEN, _pvs(PV1), plans) is None


def test_no_pvs_means_no_recommendation():
    b = chess.Board(FEN)
    assert F._recommendation_block(b, FEN, None, {"white": [], "black": []}) is None
    assert F._recommendation_block(b, FEN, [], {"white": [], "black": []}) is None


def test_render_speaks_it_first_and_as_a_line_claim():
    post = {
        "assessment": {"verdict": "The position is roughly equal"},
        "recommendation": {"move": "Rfc1", "family": "rook_activation",
                           "why": "Rook activation: put a rook on the open file",
                           "verdict": "CONFIRMED-SOUND"},
        "weaknesses": {"white": ["Isolated pawn on d4."], "black": []},
        "plans": {}, "advisory": {}, "structure": [],
    }
    out = R.render(post)
    lines = out.split("\n")
    assert lines[1].startswith("**Play Rfc1**")
    assert "the strongest continuation pursues this plan" in lines[1]


def test_render_never_commits_without_a_why():
    post = {
        "assessment": {"verdict": "The position is roughly equal"},
        "recommendation": {"move": "Rfc1", "family": None, "why": None,
                           "verdict": None},
        "weaknesses": {"white": ["Isolated pawn on d4."], "black": []},
        "plans": {}, "advisory": {}, "structure": [],
    }
    assert "**Play" not in R.render(post)
