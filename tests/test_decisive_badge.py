"""The DECISIVE guardrail on the sheet's badges (2026-07-24).

Once |eval| passes _DECISIVE_CP the positional verdict chips ("more space
kingside") are noise or actively misleading next to "a queen up". Above the
band the only badge is the decisive verdict; and it must never parrot a
material count that disagrees with who is actually winning (the finding
26/27 decoy — winning while nominally down after a sacrifice).

These test the pure decision functions with crafted assessment dicts (no
engine), plus one integration through the real sheet builder.
"""

import fact_sheet as F


def _assess(total_cp, mat_leader=None, standing=None, adjusted_cp=0):
    return {
        "total_cp": total_cp,
        "material_stability": {
            "leader": mat_leader, "standing": standing, "adjusted_cp": adjusted_cp,
        },
    }


# (assessment, expected badges). Positional chips are suppressed whenever
# decisive; the chip names the winner and uses material only when it agrees.
_CASES = [
    # equal band -> NOT decisive (the guardrail is transparent; positional
    # badges, computed elsewhere, are left untouched -> here just [])
    (_assess(40), False, []),
    (_assess(-149), False, []),
    # clean material win -> the settled standing IS the chip
    (_assess(480, "White", "White is up a rook", 500), True, ["White is up a rook"]),
    (_assess(-320, "Black", "Black is up a knight", -320), True, ["Black is up a knight"]),
    # positional / attack win, material even -> "X is winning"
    (_assess(300, None, "material is even", 0), True, ["White is winning"]),
    # total_cp ALONE decisive (adjusted_cp non-decisive), both signs — proves
    # the union's eval leg fires without help from material
    (_assess(200, None, None, 0), True, ["White is winning"]),
    (_assess(-200, None, None, 0), True, ["Black is winning"]),
    # SACRIFICE: eval says White, material says Black -> never the material
    # count; "White is winning"
    (_assess(300, "Black", "Black is up a rook", -1720), True, ["White is winning"]),
    # no engine eval (positional fallback ~0) but settled material decisive
    # -> backstop fires off adjusted_cp, leader from material
    (_assess(-20, "Black", "Black is up a queen", -900), True, ["Black is up a queen"]),
]


def test_is_decisive_and_badge():
    for assessment, decisive, expected in _CASES:
        assert F._is_decisive(assessment) is decisive, assessment
        badges = F._badges_block({"assessment": assessment})
        if decisive:
            assert badges == expected, assessment
        else:
            # non-decisive: the decisive chip must NOT appear (positional
            # badges depend on `metrics`, absent here -> empty list)
            assert badges == expected, assessment


def test_total_cp_alone_triggers_without_material():
    """adjusted_cp missing entirely (block absent) — total_cp must still
    trip the guardrail, and shape must be a one-string list."""
    assessment = {"total_cp": 250}   # no material_stability block at all
    assert F._is_decisive(assessment) is True
    badges = F._badges_block({"assessment": assessment})
    assert isinstance(badges, list) and len(badges) == 1
    assert isinstance(badges[0], str) and badges[0] == "White is winning"


def test_decisive_suppresses_every_positional_chip_type():
    """All four positional chip sources populated at once (activity, control,
    space, color-complex) — a decisive assessment must collapse to the single
    verdict, proving none of them survive the guardrail."""
    out = {
        "assessment": _assess(480, "White", "White is up a rook", 500),
        "activity": {"leader": "Black"},
        "metrics": {
            "regions": {"center": {"leader": "Black"},
                        "kingside": {"leader": "White"}},
            "space": {"queenside": {"edge": "Black"}},
            "color_complex": {"dark": {"weak_for": "White"}},
        },
    }
    badges = F._badges_block(out)
    assert badges == ["White is up a rook"]
    assert isinstance(badges, list) and isinstance(badges[0], str)


def test_boundary_exact():
    # exactly at the band is NOT past it
    assert F._is_decisive(_assess(F._DECISIVE_CP)) is False
    assert F._is_decisive(_assess(F._DECISIVE_CP + 1)) is True
    assert F._is_decisive(_assess(0, adjusted_cp=F._DECISIVE_CP)) is False
    assert F._is_decisive(_assess(0, adjusted_cp=-(F._DECISIVE_CP + 1))) is True


def test_decisive_suppresses_positional_badges_end_to_end():
    # a real position with a lopsided eval: only the verdict, no space/
    # activity chips (pvs supplies the decisive eval, production's shape)
    fen = "r3r1k1/1pp2ppp/p1np1n2/2b1p3/2B1P3/3P1N1P/PPP2PP1/3R1RK1 w - - 0 8"
    winning_pv = [{"cp": 600, "pv": [], "ucis": [], "san": []}]
    sheet = F._sheet_json(fen, winning_pv, None, verify=False)
    assert isinstance(sheet["badges"], list) and len(sheet["badges"]) == 1
    assert isinstance(sheet["badges"][0], str)
    only = sheet["badges"][0].lower()
    for noise in ("space", "active", "controls", "squares are weak"):
        assert noise not in only


def test_region_control_never_badges():
    """region_control is too noisy to be a verdict (owner 2026-07-24: 'Black
    controls the kingside' after 4.O-O is misleading) — it produces NO badge
    even with region leaders set in a non-decisive position."""
    out = {
        "assessment": _assess(20),                       # non-decisive
        "metrics": {"regions": {"center": {"leader": "Black"},
                                "kingside": {"leader": "White"},
                                "queenside": {"leader": "Black"}}},
    }
    badges = F._badges_block(out)
    assert not any("controls" in b for b in badges), badges


def test_bars_are_comparable_and_gated():
    """Bars (owner: 'bars instead of labels'): Eval + king bars always, and
    Activity/Space (centered, comparable) only when NOT decisive."""
    out = {
        "assessment": {
            "total_cp": 80,                        # ~equal
            "material_stability": {"leader": None, "standing": None, "adjusted_cp": 0},
            "king_risk": {"white": {"danger_bounded": 0.0},
                          "black": {"danger_bounded": 0.2}},
        },
        "activity": {"diff_cp": 40},
        "metrics": {"space": {
            "center": {"white": {"raw": 2}, "black": {"raw": 1}},
            "kingside": {"white": {"raw": 0}, "black": {"raw": 0}},
            "queenside": {"white": {"raw": 0}, "black": {"raw": 0}}}},
    }
    bars = {b["label"]: b for b in F._bars_block(out)}
    assert set(bars) == {"Eval", "Activity", "Space", "White king", "Black king"}
    assert bars["Eval"]["mid"] == 0.5 and 0.5 < bars["Eval"]["value"] < 0.6   # slight White
    assert bars["Activity"]["mid"] == 0.5 and bars["Activity"]["value"] > 0.5  # White edge
    assert bars["Space"]["value"] == 2 / 3 and bars["Space"]["mid"] == 0.5     # 2 vs 1 raw
    assert "mid" not in bars["Black king"] and bars["Black king"]["value"] == 0.2  # absolute

    # decisive: Activity/Space drop, Eval + kings remain
    out["assessment"]["total_cp"] = 900
    labels = {b["label"] for b in F._bars_block(out)}
    assert labels == {"Eval", "White king", "Black king"}
