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
        # activity bar off the per-side scores (material-neutral), only when
        # comparable (equal queen counts)
        "activity": {"diff_cp": 40, "comparable": True,
                     "white": {"score": 0.60}, "black": {"score": 0.50}},
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


def test_winning_reason():
    """Outright winning shows only WHY (owner). Material first, sacrifice never
    parrots material, equal -> no reason."""
    A = _assess
    # material win -> names the edge
    r = F._winning_reason({"total_cp": 520, "material_stability":
                           {"leader": "White", "standing": "White is up a rook",
                            "adjusted_cp": 500}})
    assert r == "White is winning — up a rook."
    # sacrifice (material disagrees with the winner) -> plain, no material count
    r = F._winning_reason({"total_cp": 300, "material_stability":
                           {"leader": "Black", "standing": "Black is up a rook",
                            "adjusted_cp": -1720}, "king_risk": {}})
    assert r == "White is winning."
    # material even but the loser's king is fatally exposed -> the attack
    r = F._winning_reason({"total_cp": 400, "material_stability":
                           {"leader": None, "standing": "material is even",
                            "adjusted_cp": 0},
                           "king_risk": {"black": {"danger_bounded": 0.6}}})
    assert r == "White is winning — Black's king is fatally exposed."


def test_winning_advice():
    """Hardcoded advice (owner): conversion tips ONLY when material up, the
    king-safety reminder ALWAYS, addressed to the leader."""
    # White up material -> conversion tips + king safety, all to "White"
    tips = F._winning_advice({"total_cp": 520, "material_stability":
                              {"leader": "White", "standing": "White is up a rook",
                               "adjusted_cp": 500}})
    assert any("trade pieces" in t.lower() for t in tips)
    assert tips[-1].startswith("Keep White's king safe")
    assert all("White" in t or "your" not in t for t in tips)   # addressed to White
    # Black up material -> mirrored to "Black"
    tips = F._winning_advice({"total_cp": -520, "material_stability":
                              {"leader": "Black", "standing": "Black is up a rook",
                               "adjusted_cp": -500}})
    assert tips[0].startswith("Black should trade")
    assert tips[-1].startswith("Keep Black's king safe")
    # winning by ATTACK (not material up) -> only the king-safety reminder
    tips = F._winning_advice({"total_cp": 400, "material_stability":
                              {"leader": None, "standing": "material is even",
                               "adjusted_cp": 0}})
    assert tips == ["Keep White's king safe and shut down counterplay."]
    # SACRIFICE: White is winning but BLACK is the material leader -> no
    # conversion tips (material_up False), only the king-safety reminder to White
    tips = F._winning_advice({"total_cp": 300, "material_stability":
                              {"leader": "Black", "standing": "Black is up a rook",
                               "adjusted_cp": -1720}})
    assert tips == ["Keep White's king safe and shut down counterplay."]


def test_defender_advice():
    """The loser's mirror (owner: 'what about defender's tips?'): keep-pieces-on
    only when down material, always make-it-messy + guard-your-king, to the
    loser by name."""
    # White up material -> Black is the defender, down material
    tips = F._defender_advice({"total_cp": 520, "material_stability":
                               {"leader": "White", "standing": "White is up a rook",
                                "adjusted_cp": 500}})
    assert tips[0].startswith("Black should keep pieces on")   # avoid trades
    assert any("swindle" in t or "counterplay" in t for t in tips)
    assert tips[-1].startswith("Black should still guard their own king")
    # Black up material -> White is the defender (mirror)
    tips = F._defender_advice({"total_cp": -520, "material_stability":
                               {"leader": "Black", "standing": "Black is up a rook",
                                "adjusted_cp": -500}})
    assert tips[0].startswith("White should keep pieces on")
    # winning by attack (defender not down material) -> no keep-pieces-on tip
    tips = F._defender_advice({"total_cp": 400, "material_stability":
                               {"leader": None, "standing": "material is even",
                                "adjusted_cp": 0}})
    assert not any("keep pieces on" in t for t in tips)
    assert any("messy" in t for t in tips)


def test_winning_field_only_when_decisive():
    """out['winning'] = {reason, advice, defense} when decisive; None else."""
    dec = F._sheet_json("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
                        [{"cp": 520, "pv": [], "ucis": [], "san": []}], None, verify=False)
    w = dec["winning"]
    assert w and "winning" in w["reason"]
    assert isinstance(w["advice"], list) and w["advice"]
    assert isinstance(w["defense"], list) and w["defense"]
    eq = F._sheet_json("r1bqkbnr/ppp2ppp/2np4/4p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 1 4",
                       None, None, verify=False)
    assert eq["winning"] is None


def test_engine_eval_beats_material_backstop():
    """A SOUND SACRIFICE: engine eval ~equal but raw material lopsided. With
    the engine eval present, decisiveness trusts it — the material backstop
    must NOT override (Bobotsov-Tal 11...Nxd5!: eval ~0, settled 'White is up a
    queen for two minors', is EQUAL, not 'White is winning'). Found by walking
    the game against our eval, 2026-07-24."""
    comp = {"total_cp": -39, "eval_source": "engine",
            "material_stability": {"leader": "White",
                                   "standing": "White is up a queen for a bishop and a knight",
                                   "adjusted_cp": 250}}
    assert F._is_decisive(comp) is False          # trust the engine eval
    assert F._winning_reason(comp)                # (still callable, but unused)
    # the SAME imbalance with NO engine eval (static fallback) keeps the
    # material backstop, so a real material win isn't missed offline
    static = {**comp, "eval_source": "static", "total_cp": 10}
    assert F._is_decisive(static) is True


def test_winning_shows_king_bars():
    """King numbers are shown even when winning (owner: 'run the numbers even
    when winning') — out['winning'].king_bars carries both kings' danger."""
    dec = F._sheet_json("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
                        [{"cp": 520, "pv": [], "ucis": [], "san": []}], None, verify=False)
    kb = dec["winning"]["king_bars"]
    assert [b["label"] for b in kb] == ["White king", "Black king"]
    assert all(0.0 <= b["value"] <= 1.0 and "mid" not in b for b in kb)


def test_activity_bar_uses_per_side_scores_not_diff_cp():
    """The activity bar is driven by the MATERIAL-NEUTRAL per-side scores, not
    the queen-skewed diff_cp sum — so it stays honest across a material
    imbalance in BOTH directions:
      * near-even scores -> near-even bar, even when diff_cp is large
        (Bobotsov-Tal move 18: mobility read +31 White, but scores ~0.65/0.63);
      * a big score gap SHOWS a sacrifice's positional comp
        (Harikrishna 10.Kxf2: down a queen, White 0.62 vs Black 0.30)."""
    base = {
        "assessment": {"total_cp": 20,
                       "material_stability": {"leader": None, "standing": None, "adjusted_cp": 0},
                       "king_risk": {}},
        "metrics": {"space": {}},
    }
    # large diff_cp but near-even scores -> bar stays near 0.5 (not skewed)
    out = {**base, "activity": {"diff_cp": 300,
                                "white": {"score": 0.65}, "black": {"score": 0.63}}}
    bar = next(b for b in F._bars_block(out) if b["label"] == "Activity")
    assert abs(bar["value"] - 0.5) < 0.1
    # a real activity edge (the compensation) SHOWS, even down material
    out = {**base, "activity": {"diff_cp": -300,   # down material -> negative sum
                                "white": {"score": 0.62}, "black": {"score": 0.30}}}
    bar = next(b for b in F._bars_block(out) if b["label"] == "Activity")
    assert bar["value"] > 0.6      # White clearly more active despite the sum
