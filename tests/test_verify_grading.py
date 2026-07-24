"""verify_plan verdict-grading units on hand-built pvs/rolls — no engine.

Pins the grading ladder, the timing split, the keep_king_uncastled floor fix
(#9), one-leg-None degradation, and the horizon/floor table completeness (#10).
"""
import chess
import pytest

from verify import verify_plan, PLAN_HORIZON, FLOOR_ROLL, DEFAULT_FLOOR

CASTLE_FEN = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"


# ---- timing split: CONFIRMED-SOUND (<=2) vs -LATER (>2) ------------------

def test_castle_immediate_is_confirmed_sound():
    pvs = [{"cp": 0, "ucis": ["e1g1"]}]
    r = verify_plan(CASTLE_FEN, "W", "castle_kingside", pvs=pvs, rolls=None)
    assert r["verdict"] == "CONFIRMED-SOUND"
    assert r["timing"] == "immediate"


def test_castle_later_is_confirmed_sound_later():
    # king castles only at ply 4 -> developing -> CONFIRMED-SOUND-LATER
    pvs = [{"cp": 0, "ucis": ["a2a3", "a7a6", "b2b3", "b7b6", "e1g1"]}]
    r = verify_plan(CASTLE_FEN, "W", "castle_kingside", pvs=pvs, rolls=None)
    assert r["verdict"] == "CONFIRMED-SOUND-LATER"
    assert r["timing"] == "developing"
    assert r["immediate_move"] == "a3"    # play the actual next move, not O-O


# ---- #9 keep_king_uncastled must not over-grade at 0% support -----------

def test_keep_king_uncastled_all_castle_is_unsupported():
    pvs = [{"cp": 0, "ucis": ["e1g1", "e8g8"]},
           {"cp": 10, "ucis": ["e1c1", "e8c8"]}]
    rolls = [["e1g1", "e8g8"], ["e1c1", "e8c8"], ["e1g1", "e8c8"]]
    r = verify_plan(CASTLE_FEN, "W", "keep_king_uncastled", pvs=pvs, rolls=rolls)
    assert r["verdict"] == "UNSUPPORTED"
    assert r["pooled_held_frac"] == 0.0


def test_keep_king_uncastled_confirmed_when_held():
    # nobody castles in any line -> pooled 1.0 -> CONFIRMED-SOUND
    pvs = [{"cp": 0, "ucis": ["a2a3", "a7a6"]}]
    rolls = [["b2b3", "b7b6"], ["h2h3", "h7h6"]]
    r = verify_plan(CASTLE_FEN, "W", "keep_king_uncastled", pvs=pvs, rolls=rolls)
    assert r["verdict"] == "CONFIRMED-SOUND"


# ---- one-leg-None degradation ------------------------------------------

def test_engine_leg_none_degrades_and_says_so():
    rolls = [["e1g1"], ["a2a3"]]
    r = verify_plan(CASTLE_FEN, "W", "castle_kingside", pvs=None, rolls=rolls)
    assert r["engine"] is None          # degraded, not fabricated
    assert r["maia"] is not None


# ---- #10 horizon/floor table completeness ------------------------------

def test_pair_break_has_horizon_and_floor():
    assert "pair_break" in PLAN_HORIZON
    assert "pair_break" in FLOOR_ROLL
    assert FLOOR_ROLL["pair_break"] != DEFAULT_FLOOR
