"""Color-mirror property tests. Under a rank flip (board.mirror()), White and
Black swap: every geometric read must mirror. This class of test just caught a
real SEE bug in lucena-core (CLAUDE.md finding 18) and the tension/color-complex
asymmetries in this audit (#17, #18)."""
import chess
import pytest

from structures import classify
from closed_v0 import skeleton
from tension import central_tension
from weaknesses import weak_color_complex, census

# A battery spanning structures, imbalances, king positions, edge pawns.
FENS = [
    "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R1BQ1RK1 w - - 0 8",
    "rnbqkbnr/pp2pppp/8/2pp4/3P4/4P3/PPP2PPP/RNBQKBNR w KQkq - 0 3",
    "2bqr1k1/ppp1nppp/8/8/8/2N5/PPP2PPP/2BQRBK1 w - - 0 1",
    "6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1",
    "r2q1rk1/1b1nbppp/p2ppn2/1p6/3NP3/1BN1B3/PPP1QPPP/R4RK1 w - - 0 12",
    "4k3/p7/8/8/1p6/8/PPP1PPPP/4K3 w - - 0 1",
]


@pytest.mark.parametrize("fen", FENS)
def test_central_tension_count_mirrors(fen):
    b = chess.Board(fen)
    assert len(central_tension(b)) == len(central_tension(b.mirror()))


@pytest.mark.parametrize("fen", FENS)
def test_weak_color_complex_count_mirrors(fen):
    b = chess.Board(fen)
    w = weak_color_complex(b, chess.WHITE)
    bm = weak_color_complex(b.mirror(), chess.BLACK)
    assert len(w) == len(bm)


@pytest.mark.parametrize("fen", FENS)
def test_skeleton_mirrors(fen):
    b = chess.Board(fen)
    s, sm = skeleton(b), skeleton(b.mirror())
    # scalar structural counts are color-agnostic and must be identical
    for key in ("rams", "central", "tension", "open_files"):
        if key in s and key in sm:
            assert s[key] == sm[key], key


@pytest.mark.parametrize("fen", FENS)
def test_classify_owner_flips_under_mirror(fen):
    b = chess.Board(fen)
    direct = {(n, o) for n, o in classify(b)}
    # mirror the board, classify, then flip owners back — should match
    flipped = {(n, not o) for n, o in classify(b.mirror())}
    assert direct == flipped


@pytest.mark.parametrize("fen", FENS)
def test_census_mirrors_side(fen):
    b = chess.Board(fen)
    cw = census(b, chess.WHITE)
    cb = census(b.mirror(), chess.BLACK)
    for k in cw:
        a, bb = cw[k], cb.get(k)
        la = len(a) if hasattr(a, "__len__") else a
        lb = len(bb) if hasattr(bb, "__len__") else bb
        assert la == lb, k
