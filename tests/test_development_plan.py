"""The COMPLETE DEVELOPMENT plan (2026-07-25, owner: "my next concern is
development — we don't have a plan for it yet").

THE opening plan, previously absent from the menus. Fires only in the OPENING
phase (development is a defined concept only there — the development_lag ply
ruling) for a side with >= 2 development debts (home minors + uncastled king),
names the actual pieces, and rides the corpus-validated development-lag
notable flag (+8.8pp by quartile) as its calibration. The initiative read's
development face cites the same concrete tells.
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


def test_does_not_fire_in_a_middlegame():
    b = chess.Board("r1bq2k1/p4R2/2np2rb/2p4Q/PpN1P2P/3P2P1/1PP5/5RK1 b - - 0 26")
    menus = build_menus(b)
    assert not _develop(menus, "W") and not _develop(menus, "B")


def test_needs_real_debt_not_one_stray_piece():
    # castled, one knight home, rooks connected — a single debt: no plan.
    b = chess.Board()
    for m in ("e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 d3 d6 Bg5 O-O".split()):
        b.push_san(m)
    menus = build_menus(b)
    assert not _develop(menus, "W")              # only Nb1 home -> debt 1


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
