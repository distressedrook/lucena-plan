"""Regression tests for the plan-grammar detector fixes (2026-07-24 audit).

Each test pins a bug the audit reproduced by execution. The helper replays a
SAN line from a FEN and returns the (name, side, ply, stage) tuples the grammar
emits for the given side.
"""
import chess
import pytest

from plan_diff import parse_line


def _fams(fen, sans, side, horizon=40):
    b = chess.Board(fen)
    mvs = []
    for s in sans:
        m = b.parse_san(s)
        mvs.append(m)
        b.push(m)
    pls = parse_line(chess.Board(fen), mvs, horizon, 6)
    return [(p["name"], p["side"], p["ply"], p.get("stage"))
            for p in pls if p["side"] == side]


def _names(fam_tuples):
    return {t[0] for t in fam_tuples}


# ---- #1 castle detection must require the KING to move ------------------

def test_castle_not_emitted_for_rook_lift():
    # White king already castled on g1; a rook lift Re1-c1 must NOT be a castle
    fen = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3R1K1 w kq - 0 1"
    got = _names(_fams(fen, ["Rec1"], "W"))
    assert "castle_queenside" not in got and "castle_kingside" not in got


def test_real_castling_still_fires():
    fen = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"
    assert "castle_kingside" in _names(_fams(fen, ["O-O"], "W"))
    assert "castle_queenside" in _names(_fams(fen, ["O-O-O"], "W"))


# ---- #2 bad_bishop_trade must be reachable (opponent captures it) -------

def test_bad_bishop_trade_fires_when_opponent_captures():
    # White Be3 entombed behind rammed d4/f4; black Nc4 captures it
    fen = "4k3/8/8/3p1p2/2nP1P2/2P1B3/PP4PP/4K3 b - - 0 1"
    assert "bad_bishop_trade" in _names(_fams(fen, ["Nxe3"], "W"))


# ---- #3 minority_block ram sign ----------------------------------------

def test_minority_block_fires_on_real_ram():
    # Black minority_pre (a7,b4 vs White a2,b2,c2); White rams b2-b3 onto b4
    fen = "4k3/p7/8/8/1p6/8/PPP1PPPP/4K3 w - - 0 1"
    line = ["b3", "Kd8", "Kd1", "Ke8", "Ke1", "Kd8", "Kd1", "Ke8"]
    assert "minority_block" in _names(_fams(fen, line, "W"))


# ---- #4 trade_into_endgame must credit the QxQ initiator ----------------

def test_trade_into_endgame_credits_initiator():
    # White holds the bishop pair, initiates Qxd8, Black recaptures, minors trade
    fen = "2bqr1k1/ppp1nppp/8/8/8/2N5/PPP2PPP/2BQRBK1 w - - 0 1"
    line = ["Qxd8", "Rxd8", "Nd5", "Nxd5", "Kh1", "Kf8", "Kg1", "Kg8"]
    got = _names(_fams(fen, line, "W"))
    assert "trade_into_endgame" in got


# ---- #5 free_bad_bishop must reject a double push that stays on-color ----

def test_free_bad_bishop_rejects_double_push():
    # White dark bishop c1 bad; d2-d4 keeps the pawn dark -> not a freeing move
    fen = "4k3/8/8/8/8/2P1P3/PP1P1PPP/2B1K3 w - - 0 1"
    assert "free_bad_bishop" not in _names(_fams(fen, ["d4"], "W"))


def test_free_bad_bishop_accepts_single_push():
    fen = "4k3/8/8/8/8/2P1P3/PP1P1PPP/2B1K3 w - - 0 1"
    assert "free_bad_bishop" in _names(_fams(fen, ["c4"], "W"))
