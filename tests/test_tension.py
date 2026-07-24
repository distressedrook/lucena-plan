"""tension.py fixes: classify_line must track ALL original pairs (#16), and
central_tension must be color-symmetric (#17)."""
import chess

from tension import central_tension, classify_line


def test_classify_line_tracks_second_pair():
    # two central tensions (d4/e5 and e4/d5); resolving EITHER must read as
    # 'resolve', not be mislabeled 'keep' because only pairs0[0] was tracked
    fen = "4k3/8/8/3pp3/3PP3/8/8/4K3 w - - 0 1"
    assert classify_line(fen, ["e4d5"])["mode"] == "resolve"
    assert classify_line(fen, ["d4e5"])["mode"] == "resolve"


def test_central_tension_is_color_symmetric():
    # White b4 vs Black c5 — the color-mirror of White c4 vs Black b5. Both
    # must be detected (the b-file pawn is the wing pawn, the c-file is central)
    b = chess.Board("4k3/8/8/2p5/1P6/8/8/4K3 w - - 0 1")
    assert len(central_tension(b)) == 1
    assert len(central_tension(b.mirror())) == 1


def test_central_tension_none_when_no_contact():
    assert central_tension(chess.Board()) == []
