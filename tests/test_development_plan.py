"""The COMPLETE DEVELOPMENT plan (2026-07-25, owner: "my next concern is
development — we don't have a plan for it yet").

Gated on a SIDE's OWN development debts, not the global phase (owner
2026-07-25: "the other team may not have completed the development") — it
fires for any side with >= 1 debt (a minor still on its home square, or an
uncastled king with rights), even once the game is a middlegame for the
developed opponent. Concrete, ply-independent geometry: no rook-connection
tell ("sometimes the rook may not be connected at all"), no ply-20 cap, and
no GM baseline ("let's not show the GM baseline, it's useless"). Names the
actual home pieces. The initiative read's development face cites the same
concrete tells.
"""

import chess

from suggest import build_menus


def _danish():
    b = chess.Board()
    for m in "e4 e5 d4 exd4 c3 dxc3 Bc4 cxb2 Bxb2".split():
        b.push_san(m)
    return b


def _develop(menus, t):
    return [c for c in menus[t] if c[2].startswith("COMPLETE DEVELOPMENT")]


def test_fires_in_the_opening_naming_the_home_pieces():
    menus = build_menus(_danish())
    for t, pieces in (("W", ["Nb1", "Ng1"]), ("B", ["Bc8", "Bf8", "Nb8", "Ng8"])):
        (eff, trig, head, ev, verify, tsq), = _develop(menus, t)
        for p in pieces:
            assert p in head                     # names the actual pieces
        assert "castle without delay" in head    # both kings uncastled
        assert "development debts" in trig
        assert "no engine contract" in verify    # advisory tier


def test_fires_for_a_lagging_side_in_a_middlegame():
    # White is fully developed (a middlegame for White), but Black's Bc8 is
    # still home. The lagging side's debt must still surface — this is the
    # case that started the redefinition (owner 2026-07-25: "the other team
    # may not have completed the development"). Per side, no phase gate.
    from lucena_core.reads import game_phase
    fen = "r1bq2k1/p4R2/2np2rb/2p4Q/PpN1P2P/3P2P1/1PP5/5RK1 b - - 0 26"
    gp = game_phase(fen)
    assert gp["phase"] == "middlegame"
    assert gp["developed"] == {"white": True, "black": False}
    menus = build_menus(chess.Board(fen))
    assert not _develop(menus, "W")              # developed -> silent
    (eff, trig, head, ev, verify, tsq), = _develop(menus, "B")
    assert "Bc8" in head                         # names the lagging piece
    assert "1 development debt" in trig


def test_fires_on_a_single_home_piece():
    # Castled, everything out except Nb1 — one debt. A lone undeveloped minor
    # is still undeveloped: no >=2 gate (owner 2026-07-25 — the c8 bishop that
    # started this). Concrete geometry, not a corpus threshold.
    b = chess.Board()
    for m in ("e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 d3 d6 Bg5 O-O".split()):
        b.push_san(m)
    menus = build_menus(b)
    (eff, trig, head, ev, verify, tsq), = _develop(menus, "W")
    assert "Nb1" in head                         # only Nb1 home -> debt 1
    assert "1 development debt" in trig


def test_initiative_dev_face_cites_the_debt():
    from initiative import initiative
    fen = _danish().fen()
    # engine-free geometry-prior path is fine: the dev why enrichment needs a
    # dev-face verdict, which needs pvs — craft the minimal pvs shape instead
    pvs = [{"cp": -30, "ucis": ["b8c6"]}, {"cp": -60, "ucis": ["d7d6"]},
           {"cp": -80, "ucis": ["g8f6"]}]
    iv = initiative(fen, pvs)
    if iv["leader"] == "White" and iv.get("mechanism") == ["development"]:
        tells = iv["white"]["why"].get("development") or []
        assert any("still home" in t for t in tells)
        assert any("king uncastled" in t for t in tells)
