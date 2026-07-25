"""The compensation read (2026-07-24, owner design: "if less material ->
isDrillable -> if not, what compensation do we have? king safety -> activity
-> space").

WHY a materially-DOWN side is still holding. The honest split the read
enforces: MAGNITUDE (how much comp) is the ENGINE's to state — never a term
sum, which finding 18 measured explains only ~15% of eval-minus-material and
which points the WRONG way here (raw mobility is queen-skewed toward the side
that still has the queen; the sacker's own exposed king counts against them).
FORM (what kind) is a sharpest-to-slowest cascade: enemy-king attack ->
activity -> space -> concrete.

These test the pure decision function with crafted `out` dicts (no engine).
"""

import fact_sheet as F


def _out(total, adj, standing, *, king=None, act_leader=None, space=None,
         bucket="QUIET", eval_source="engine"):
    king = king or {}
    return {
        "assessment": {
            "total_cp": total, "eval_source": eval_source,
            "material_stability": {"adjusted_cp": adj, "standing": standing},
            "king_risk": {"white": {"danger_bounded": king.get("white", 0.0)},
                          "black": {"danger_bounded": king.get("black", 0.0)}},
            "character": {"bucket": bucket},
        },
        "activity": {"leader": act_leader},
        "metrics": {"space": space or {}},
    }


def _sp(w, b):
    return {"center": {"white": {"raw": w}, "black": {"raw": b}}}


def test_activity_is_the_form_when_the_down_sides_own_king_is_the_exposed_one():
    # Harikrishna 10.Kxf2: WHITE is down a queen AND White's own king is
    # exposed, so ATTACK must NOT fire (that rung reads the ENEMY king).
    # Activity carries it: White's pieces far more active.
    out = _out(0, -900, "Black is up a queen",
               king={"white": 0.5}, act_leader="White")
    r = F._compensation_read(out)
    assert r["side"] == "White"
    assert r["magnitude"] == "full"          # eval ~ 0 despite -900 material
    assert r["forms"] == ["activity"]        # not "attack" — wrong king
    assert r["primary"] == "activity"
    assert r["deficit_cp"] == 900 and r["comp_cp"] == 900


def test_winning_sacrifice_gets_attack_form_and_winning_magnitude():
    out = _out(320, -280, "Black is up a rook",
               king={"black": 0.55}, act_leader="White", bucket="SHARP")
    r = F._compensation_read(out)
    assert r["magnitude"] == "winning"        # eval past the decisive band
    assert r["forms"][0] == "attack"          # enemy king exposed = sharpest
    assert "activity" in r["forms"]           # both can be listed
    assert r["tactical"] is True              # SHARP -> read it in the lines


def test_no_static_form_falls_to_concrete_finding18():
    # Down 3 (queen for two minors), eval level, no static feature, and no
    # line_theories on this synthetic dict -> concrete/dynamic.
    out = _out(0, 300, "White is up a queen")
    r = F._compensation_read(out)
    assert r["side"] == "Black"
    assert r["forms"] == ["concrete"]
    assert r["primary"] == "concrete"
    assert r["concrete_kind"] == "dynamic"     # nothing to walk -> standing threat


def test_concrete_regained_material_from_lines():
    # No root static form, but the engine LINE closes the deficit (SEE-settled
    # material goes from Black-down to even) -> "wins the material back".
    out = _out(-30, -400, "Black is up a piece")   # White down a piece, eval ~0
    out["assessment"]["line_theories"] = {
        "summary": [],
        "lines": [{
            "line": ["Nxe6", "fxe6", "Qxe6+"],
            "material": {"adjusted_cp": 0,        # settles to even -> recovered
                         "threats": [{"san": "Nxe6", "see": 300, "side": "White"}]},
        }],
    }
    r = F._compensation_read(out)
    assert r["primary"] == "concrete"
    assert r["concrete_kind"] == "regained"
    assert "Nxe6" in r["reason"]                  # names the winning move
    assert "comes straight back" in r["reason"]
    assert "engine" not in r["summary"].lower()   # never mention engine lines


def test_only_move_block_detects_the_cliff():
    # White to move, best +51, second -212 -> a 263cp cliff = one move holds.
    fen = "rn3rk1/1b1q4/p3Rbp1/3p2BQ/P7/8/1PP2PPP/R5K1 w - - 0 20"
    pvs = [{"cp": 51, "ucis": ["h5g6"]}, {"cp": -212, "ucis": ["h5e2"]}]
    om = F._only_move_block(fen, pvs)
    assert om is not None and om["gap_cp"] == 263 and om["razor"] is False
    assert om["move"] == "Qxg6+"                 # named in SAN
    # a flat position (no cliff) is not an only-move
    assert F._only_move_block(fen, [{"cp": 30, "ucis": ["h5e2"]},
                                    {"cp": 10, "ucis": ["h5g6"]}]) is None


def test_only_move_is_rung_zero_over_a_positional_form():
    # A material-down holding position that is ALSO an only-move: the read must
    # lead with the move, not the activity form (which stays in `forms`).
    out = _out(0, -900, "Black is up a queen", act_leader="White")
    out["assessment"]["only_move"] = {"move": "Qxg6+", "gap_cp": 263, "razor": False}
    r = F._compensation_read(out)
    assert r["primary"] == "only_move"
    assert "activity" in r["forms"]              # positional form kept as aftermath
    assert "Qxg6+" in r["summary"] and "anything else loses" in r["summary"]
    assert r["only_move"]["gap_cp"] == 263


def test_concrete_harvest_from_durable_terms():
    # No root form, deficit doesn't close, but a term survives to quiescence
    # across the lines -> the comp cashes into that term (finding 2 harvest).
    out = _out(-40, -250, "Black is up a piece")
    out["assessment"]["line_theories"] = {
        "summary": ["more active pieces"],
        "lines": [{"line": ["Re1"], "material": {"adjusted_cp": -250}}],
    }
    r = F._compensation_read(out)
    assert r["concrete_kind"] == "harvest"
    assert "more active pieces" in r["reason"]


def test_space_form():
    out = _out(-120, -350, "Black is up a piece", space=_sp(9, 4))
    r = F._compensation_read(out)
    assert r["forms"] == ["space"]
    assert r["magnitude"] == "partial"        # cushioned but still worse


def test_just_losing_returns_none():
    # Down a rook and STILL worse by -700 -> nets ~100cp arithmetically, but
    # that is not compensation, it is a lost position. Below the eval floor.
    assert F._compensation_read(_out(-700, -800, "Black is up a rook")) is None


def test_even_material_returns_none():
    assert F._compensation_read(_out(40, -30, "material is even")) is None


def test_static_fallback_never_asserts_compensation():
    out = _out(0, -900, "Black is up a queen",
               act_leader="White", eval_source="static")
    assert F._compensation_read(out) is None


def test_sheet_wires_evidence_initiative_and_king_why():
    # End-to-end through the real sheet builder: the assessment carries the
    # initiative block (with named why), king_risk carries per-side why, and
    # a fired compensation read carries citable evidence.
    import chess as _c
    fen = "rn3rk1/1b1q4/p3Rbp1/3p2BQ/P7/8/1PP2PPP/R5K1 w - - 0 20"
    pvs = [{"cp": 51, "ucis": ["h5g6", "d7g7", "e6f6"], "pv": [], "san": []},
           {"cp": -212, "ucis": ["h5e2"], "pv": [], "san": []}]
    out = F.post_verify_json(fen, pvs, None)
    iv = out["assessment"]["initiative"]
    assert iv and set(iv["white"]["why"]) == {"checks", "captures",
                                             "loose", "attacked"}
    kr = out["assessment"]["king_risk"]
    assert isinstance(kr["white"].get("why"), list)
    c = out["compensation"]
    assert c is not None and c["primary"] == "only_move"
    assert any("Qxg6+" in e for e in c["evidence"])


def test_magnitude_is_engine_signed_not_a_term_sum():
    # The magnitude reads the ENGINE eval, side-signed for the down side.
    full = F._compensation_read(_out(-40, -400, "Black is up a piece",
                                     act_leader="White"))
    partial = F._compensation_read(_out(-200, -400, "Black is up a piece",
                                        act_leader="White"))
    assert full["magnitude"] == "full"        # eval ~ 0 for the down side
    assert partial["magnitude"] == "partial"  # down side clearly worse
    assert full["eval_cp"] == -40 and partial["eval_cp"] == -200
