"""The PRE-phase feature scan feeding the interactive loading (owner
2026-07-25): ordered stages, each with the squares the app highlights.
Pure geometry, empty stages skipped, home bishops never 'bad'."""

import chess

from preroll import features


def test_startpos_stages_are_clean():
    st = features(chess.STARTING_FEN)
    stages = [f["stage"] for f in st]
    assert stages[0] == "pawns" and len(st[0]["squares"]) == 16
    assert "development" in stages          # opening: home minors highlighted
    assert "bishops" not in stages          # home bishops are not bad bishops
    assert "passers" not in stages          # empty stages skipped


def test_middlegame_stage_shape():
    fen = "r1bq2k1/p4R2/2np2rb/2p4Q/PpN1P2P/3P2P1/1PP5/5RK1 b - - 0 26"
    st = features(fen)
    by = {f["stage"]: f for f in st}
    assert by["passers"]["squares"]         # a4/b4-side passers exist
    assert "development" not in by          # not the opening
    for f in st:                            # every stage carries real squares
        assert f["squares"] and f["label"]
        assert all(len(s) == 2 for s in f["squares"])


def test_planted_enemy_outpost_is_highlighted():
    # Codex 2026-07-25: holes_in never returns occupied squares, so a planted
    # enemy minor must come from the occupied-outpost detector. White knight
    # anchored on d6 (pawn-supported hole in Black's camp).
    fen = "r3k2r/pp3ppp/2pN4/4P3/8/8/PPP2PPP/R3K2R b KQkq - 0 12"
    st = {f["stage"]: f for f in features(fen)}
    assert "outposts" in st and "d6" in st["outposts"]["squares"]
