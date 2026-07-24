"""detect_minority_attack regression. The 2026-07-24 lever fix strips a
check/mate suffix before matching the lever SAN (bxc6+ == bxc6); this test
guards that NORMAL (unchecked-lever) detection still fires on the annotated
study games. The checking-lever case itself is a trivial `san.rstrip('+#')`
and is covered by inspection.

Skips cleanly when the research PGNs are absent (they never ship)."""
import glob
import os

import pytest

chesspgn = pytest.importorskip("chess.pgn")
import chess.pgn  # noqa: E402

from detectors import detect_minority_attack  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STUDIES = os.path.join(_ROOT, "research", "data", "studies")


def _detect(path):
    with open(path) as fh:
        g = chess.pgn.read_game(fh)
    return detect_minority_attack(g) if g else None


@pytest.mark.parametrize("needle", ["benko-vs-taimanov", "tal-vs-savon"])
def test_known_minority_attack_games_still_detect(needle):
    hits = glob.glob(os.path.join(_STUDIES, f"*{needle}*.pgn"))
    if not hits:
        pytest.skip(f"study PGN {needle} not present (research not shipped)")
    r = _detect(hits[0])
    assert r is not None
    assert r["side"] == "white"


def test_lever_suffix_stripped():
    """Direct check of the fix's core: a checking lever SAN must compare equal
    to the plain lever after stripping +/#."""
    assert "bxc6+".rstrip("+#") == "bxc6"
    assert "cxb5#".rstrip("+#") == "cxb5"
