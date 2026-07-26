"""Golden-ish structural tests for the JSON product sheet (the live path).

Locks the FEN-redaction invariant (#12), the details/route_note fix (#13), the
schema keys, and run-to-run determinism (#14). Uses a small canned {pvs, rolls}
bank so no engine is needed.
"""
import json

import chess
import pytest

from fact_sheet import post_verify_json, pre_verify_json

FEN = "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP3PPP/R1BQ1RK1 w - - 0 8"
PVS = [{"cp": 20, "ucis": ["c4d5", "e6d5", "c1d2"]},
       {"cp": 25, "ucis": ["f1e1", "f8e8", "h2h3"]}]
ROLLS = [["c4d5", "e6d5"], ["f1e1", "f8e8"], ["a2a3", "a7a6"]]


def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_strings(v)


def _looks_like_board(s):
    return " " in s and s.split(" ", 1)[0].count("/") == 7


# ---- #12 no FEN anywhere in the artifact -------------------------------

@pytest.mark.parametrize("builder", [pre_verify_json, post_verify_json])
def test_no_fen_leak(builder):
    out = builder(FEN, PVS, ROLLS)
    assert "fen" not in out
    board = FEN.split()[0]
    blob = json.dumps(out)
    assert board not in blob
    # and no OTHER board string (quiescence walks) survived the scrub
    assert not [s for s in _all_strings(out) if _looks_like_board(s)]


def test_id_is_opaque():
    out = post_verify_json(FEN, PVS, ROLLS)
    assert out["id"].startswith("POSITION-")


# ---- schema + plan-entry keys (#13) ------------------------------------

def test_plan_entries_carry_line_derived_keys():
    out = post_verify_json(FEN, PVS, ROLLS)
    plans = out["plans"]["white"] + out["plans"]["black"]
    assert plans, "expected some plan candidates"
    for p in plans:
        for k in ("families", "family", "details", "routes", "route_note",
                  "verified", "verdict"):
            assert k in p, k
    # a confirmed plan that produced line details must not keep a geometric
    # route_note (specifics come from the lines, not geometry)
    for p in plans:
        if p["verified"] and (p["details"] or p["routes"]):
            assert p["route_note"] is None


# ---- #14 determinism ----------------------------------------------------

def test_deterministic():
    a = post_verify_json(FEN, PVS, ROLLS)
    b = post_verify_json(FEN, PVS, ROLLS)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_only_enemy_trapped_pieces_reach_the_side_report():
    """TRAPPED is the ENEMY's doing (owner 2026-07-25: "why is Ra8 being
    tagged as trapped? ... they can move, right?"). On move 1 every rook,
    bishop and queen has zero safe moves — blocked by its OWN army — so the
    metric lists them all; the side report must surface none of them. A piece
    the enemy actually catches still comes through."""
    import chess
    from fact_sheet import pre_verify_json
    from lucena_core.metrics import trapped_pieces

    assert trapped_pieces(chess.STARTING_FEN)["black"]          # metric: yes
    sides = pre_verify_json(chess.STARTING_FEN, None, None)["sides"]
    assert sides["white"]["trapped"] == []                      # report: no
    assert sides["black"]["trapped"] == []

    # Bxa7 met by ...b6 — b8 and b6 covered, bishop attacked where it stands.
    fen = "rn1qkbnr/B1p1pppp/1p6/8/8/8/PPPPPPPP/RNBQK1NR b KQkq - 0 4"
    caught = pre_verify_json(fen, None, None)["sides"]["white"]["trapped"]
    assert [e["square"] for e in caught] == ["a7"]


def test_an_outside_bishop_is_not_a_bad_bishop():
    """QGD 7.Bh4 (owner 2026-07-25: "why is the bishop on h4 bad?"). Five of
    White's eight pawns sit on dark squares and the bishop's mobility lands
    exactly on the 2.5 bar, so the raw `bad_bishop` detector fires — but the
    bishop is developed, OUTSIDE its chain and pressing f6/e7. Finding 4
    measured that split: inside 0.470, outside 0.517 (no penalty at all), so
    nothing user-facing may call it bad, and neither cure plan may fire for
    it. An inside bishop still gets named."""
    import chess
    from fact_sheet import pre_verify_json
    from weaknesses import bad_bishop, bad_bishop_problem

    b = chess.Board()
    for m in "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6 Bh4".split():
        b.push_san(m)
    assert chess.H4 in bad_bishop(b, chess.WHITE)            # detector: yes
    assert bad_bishop_problem(b, chess.WHITE) == []          # presentation: no

    sides = pre_verify_json(b.fen(), None, None)["sides"]
    assert not any("bishop on h4" in w for w in sides["white"]["weaknesses"])
    assert not any("BAD BISHOP" in p["idea"].upper()
                   for p in sides["white"]["plans"])
    # Black's c8 bishop is inside its chain — but at move 7, with the queen's
    # knight still on b8, Black is DEVELOPING, so it is not called bad either
    # (2026-07-26; see test_a_home_bishop_is_bad_only_when_it_is_the_last_one_out).
    assert not any("bishop on c8" in w for w in sides["black"]["weaknesses"])
    assert any("Bc8" in a["idea"] for a in sides["black"]["advisory"])


def test_the_space_bar_is_a_differential_not_a_share():
    """A share saturates the instant one side is at zero: after 1.Nf3 e5 the bar
    read 100% Black off a single pawn move, and after 1.e4 it read 100% White
    (owner 2026-07-26: "why is the space maxxed out for black in this
    position?"). It is a centered differential now, on the same scale the space
    badge is calibrated on — a raw lead of 2 is a real edge, so it nudges."""
    import chess
    from fact_sheet import pre_verify_json

    def space_bar(moves):
        b = chess.Board()
        for m in moves.split():
            b.push_san(m)
        bars = {bar["label"]: bar for bar in pre_verify_json(b.fen(), None, None)["bars"]}
        return bars.get("Space")

    one_pawn = space_bar("Nf3 e5")                  # White has moved no pawn at all
    assert one_pawn is not None
    assert 0.3 < one_pawn["value"] < 0.5            # off centre toward Black, nowhere near maxed
    assert space_bar("e4 e5")["value"] == 0.5       # symmetrical fronts: dead even
    assert 0.5 < space_bar("e4 Nf6")["value"] < 0.7  # White's one pawn: a nudge, not a rout


def test_a_home_bishop_is_bad_only_when_it_is_the_last_one_out():
    """Fried Liver, move 10 (owner 2026-07-26: "I am a bit skeptical about the
    claims on Black's bad bishops"). Black's Bc8 and Bf8 were both called bad
    and drew two FREE THE BAD BISHOP plans — pushing ...b6 and ...g6 in front of
    a king already sitting on e6 under fire. They are not bad bishops, they are
    pieces that have not moved; one ...c6 was all it took to flip them, by
    making the third light-square pawn.

    The discrimination is the development debt, not the square: the French
    light-squared bishop behind a fixed e6/d5 chain, with everything else
    already developed, IS the textbook bad bishop and still fires."""
    import chess
    from weaknesses import bad_bishop, bad_bishop_problem
    from fact_sheet import pre_verify_json

    fried = chess.Board("r1bq1b1r/pp2n1pp/2p1k3/3np1B1/2BP4/2N2Q2/PPP2PPP/R3K2R b KQ - 1 10")
    assert [chess.square_name(s) for s in bad_bishop(fried, chess.BLACK)] == ["c8", "f8"]
    assert bad_bishop_problem(fried, chess.BLACK) == []          # ...none surfaced
    black = pre_verify_json(fried.fen(), None, None)["sides"]["black"]
    assert not any("bishop" in w for w in black["weaknesses"])
    assert not any("BAD BISHOP" in p["idea"].upper() for p in black["plans"])
    # the development plan owns them, and says so by name
    assert any("Bc8" in a["idea"] and "Bf8" in a["idea"] for a in black["advisory"])

    # the real thing: everything out except the bishop, behind a fixed chain
    french = chess.Board("r1bq1rk1/pp1nbppp/2p1pn2/3pP3/3P4/2N2N2/PPP2PPP/R1BQ1RK1 b - - 0 10")
    assert [chess.square_name(s) for s in bad_bishop_problem(french, chess.BLACK)] == ["c8"]
    # ...but put one knight back on b8 and it is a developing position again
    developing = chess.Board("rnbq1rk1/pp2bppp/2p1p3/3pP3/3P4/2N2N2/PPP2PPP/R1BQ1RK1 b - - 0 10")
    assert bad_bishop_problem(developing, chess.BLACK) == []


def test_the_bad_bishop_plans_name_the_bishop():
    """Two bad bishops produced two identical plan lines — the reader could not
    tell which one either was about (2026-07-26)."""
    import chess
    from suggest import build_menus
    b = chess.Board("r1bq1rk1/pp1nbppp/2p1pn2/3pP3/3P4/2N2N2/PPP2PPP/R1BQ1RK1 b - - 0 10")
    heads = [h for _, _, h, _, _, _ in build_menus(b)["B"] if "BAD BISHOP" in h]
    assert heads and all("c8" in h for h in heads)


def test_the_strong_square_is_actually_in_front_of_the_king():
    """The claim names a square "in front of {enemy}'s king" (owner 2026-07-26:
    "check if those squares are actually in front of the king"). The DETECTOR's
    rule is about who can challenge a square, not where it sits, so it admits
    one up to two files away — e5 against a king on g8 was being announced as
    the square in front of Black's king. The plan now requires the king's file
    or a neighbour, which is what the sentence says."""
    import chess
    from suggest import build_menus
    from weaknesses import strong_squares

    fen = "r2q1rk1/pp1nbppp/2p2n2/3p2B1/3P4/2NQPN2/PP3PPP/R4RK1 w - - 5 11"
    b = chess.Board(fen)
    # the detector still offers the wide ones...
    assert {chess.square_name(s) for s in strong_squares(b, chess.WHITE)} >= {"e5", "f5"}
    # ...and the plan takes only what is in front of the king on g8
    heads = [h for _, _, h, _, _, _ in build_menus(b)["W"] if h.startswith("KNIGHT TO")]
    assert heads == ["KNIGHT TO f5: maneuver a knight to the strong square in "
                     "front of Black's king"]
    black = [h for _, _, h, _, _, _ in build_menus(b)["B"] if h.startswith("KNIGHT TO")]
    assert black, "Black's own strong-square plan should still fire"
    assert any(h.startswith("KNIGHT TO g4:") for h in black)     # in front of g1
    assert not any(h.startswith("KNIGHT TO e4:") for h in black)  # two files off


def test_a_strong_square_knight_is_never_presented_unverified(monkeypatch):
    """Owner 2026-07-26: "these have to be engine verified". The evidence tags
    are honest for an idea a reader can weigh on its own — doubling rooks is
    sound advice whether or not this engine plays it — but this plan asserts a
    SPECIFIC maneuver to a SPECIFIC square, and unconfirmed it is unfalsifiable
    filler. It is dropped, not tagged."""
    import chess
    import verify as _verify
    from fact_sheet import post_verify_json

    fen = "r2q1rk1/pp1nbppp/2p2n2/3p2B1/3P4/2NQPN2/PP3PPP/R4RK1 w - - 5 11"
    pvs = [{"cp": 20, "pv": [], "ucis": [], "san": []}]

    def refused(fen, t, fam, **kw):
        return {"verdict": "NOT-IN-BEST-LINES", "family": fam}
    monkeypatch.setattr(_verify, "verify_plan", refused)
    plans = post_verify_json(fen, pvs, [])["sides"]["white"]["plans"]
    assert not any("Knight to" in p["idea"] for p in plans)
    assert any("Rook activation" in p["idea"] for p in plans)   # others still tagged

    def confirmed(fen, t, fam, **kw):
        return {"verdict": "CONFIRMED-SOUND", "family": fam, "timing": "developing"}
    monkeypatch.setattr(_verify, "verify_plan", confirmed)
    plans = post_verify_json(fen, pvs, [])["sides"]["white"]["plans"]
    knight = [p for p in plans if "Knight to" in p["idea"]]
    assert knight and knight[0]["verified"] is True             # ...and it survives


def test_holes_and_outposts_are_different_things():
    """Owner 2026-07-26: "let's separate holes and outposts. Holes are
    differently used than outposts."

    A hole belongs to the camp whose pawns can never guard it again; the side
    that can USE it is the other one. The old projection filed every hole a
    side CONTROLLED as that side's outpost, whatever camp it was in — so a hole
    in your own camp that you happen to cover was listed as your asset, exactly
    backwards. In the Carlsbad below d3 is White's weakness and Black's target,
    and d6 is the mirror."""
    import chess
    from fact_sheet import pre_verify_json
    from weaknesses import holes_report

    fen = "r2q1rk1/pp1nbppp/2p2n2/3p2B1/3P4/2NQPN2/PP3PPP/R4RK1 w - - 5 11"
    sides = pre_verify_json(fen, None, None)["sides"]
    assert [h["square"] for h in sides["black"]["holes"]] == ["d6"]
    assert [h["square"] for h in sides["white"]["outposts"]] == ["d6"]
    # ...and it is on nobody else's list: White's own camp has d3, occupied
    assert [h["square"] for h in sides["white"]["holes"]] == []
    assert [h["square"] for h in sides["black"]["outposts"]] == []
    d3, = [h for h in holes_report(chess.Board(fen)) if h["square"] == "d3"]
    assert d3["camp"] == "white" and d3["empty"] is False
    # every outpost is in the enemy camp, every hole in one's own
    for side, enemy in (("white", "black"), ("black", "white")):
        assert all(h["camp"] == enemy for h in sides[side]["outposts"])
        assert all(h["camp"] == side for h in sides[side]["holes"])

    # ...and a hole the camp's OWN piece is standing on is nobody's target: the
    # structure can never guard e3 again, but White's bishop is on it.
    kid = "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 0 9"
    e3, = [h for h in holes_report(chess.Board(kid)) if h["square"] == "e3"]
    assert e3["camp"] == "white" and e3["empty"] is False
    ksides = pre_verify_json(kid, None, None)["sides"]
    assert not any(h["square"] == "e3" for h in ksides["black"]["outposts"])
    assert not any(h["square"] == "e3" for h in ksides["white"]["holes"])


def test_a_hole_says_what_it_means():
    """The weakness line states the USE, not just the square: a hole is not a
    square you do something with, it is one your pawns can never guard again."""
    from fact_sheet import pre_verify_json
    fen = "r1bq1b1r/pp2n1pp/2p1k3/3np1B1/2BP4/2N2Q2/PPP2PPP/R3K2R b KQ - 1 10"
    black = pre_verify_json(fen, None, None)["sides"]["black"]["weaknesses"]
    line, = [w for w in black if w.startswith("Holes at")]
    assert "cannot be chased off" in line and "guard it again" in line


def test_planting_a_minor_is_never_claimed_unverified(monkeypatch):
    """"I don't think we are engine-verifying this. Let's do that." Same rule as
    the strong-square knight: naming a square and asserting a piece gets there
    is either something the lines do, or it is filler."""
    import verify as _verify
    from fact_sheet import post_verify_json
    # the Carlsbad, where White's outpost plan (d6) genuinely fires
    fen = "r2q1rk1/pp1nbppp/2p2n2/3p2B1/3P4/2NQPN2/PP3PPP/R4RK1 w - - 5 11"
    pvs = [{"cp": 20, "pv": [], "ucis": [], "san": []}]

    monkeypatch.setattr(_verify, "verify_plan",
                        lambda fen, t, fam, **kw: {"verdict": "NOT-IN-BEST-LINES",
                                                   "family": fam})
    plans = post_verify_json(fen, pvs, [])["sides"]["white"]["plans"]
    assert not any("Outpost plan" in p["idea"] for p in plans)
    assert any("Rook activation" in p["idea"] for p in plans)   # others still tagged

    monkeypatch.setattr(_verify, "verify_plan",
                        lambda fen, t, fam, **kw: {"verdict": "CONFIRMED-SOUND",
                                                   "family": fam})
    plans = post_verify_json(fen, pvs, [])["sides"]["white"]["plans"]
    planted = [p for p in plans if "Outpost plan" in p["idea"]]
    assert planted and planted[0]["verified"] is True


def test_the_chips_and_the_prose_read_the_same_holes():
    """ONE definition (owner 2026-07-26: "let's unify"). The chips came from
    lucena_core.region_control's hole list and the sentence from
    suggest.holes_in — same predicate, same rank window, different relevance
    rules — so a Fried Liver position reported e4/e5/e6 in a chip row and
    "Holes at d6" in the prose beside it. Both filter one canonical list now."""
    import re
    from fact_sheet import pre_verify_json
    fen = "r1bq1b1r/pp2n1pp/2p1k3/3np1B1/2BP4/2N2Q2/PPP2PPP/R3K2R b KQ - 1 10"
    sheet = pre_verify_json(fen, None, None)
    black = sheet["sides"]["black"]
    chips = {h["square"] for h in black["holes"]}
    line, = [w for w in black["weaknesses"] if w.startswith("Holes at")]
    prose = set(re.findall(r"[a-h][1-8]", line.split("—")[0]))
    assert chips == prose == {"d6"}
    # e5 and e6 ARE holes in Black's camp — no black pawn can ever guard them —
    # but Black's own pawn and king are standing there, so neither list calls
    # them targets (Codex 2026-07-26: `occupied` is about the USER's minor and
    # cannot double as "the square is taken").
    assert {h["square"] for h in sheet["holes"] if not h["empty"]} >= {"e5", "e6"}
    # e4 is the user's own 4th rank — "shallow", priced at 0.509 — so it is in
    # the canonical list, tagged, and shown by nobody.
    assert any(h["square"] == "e4" and h["tag"] == "shallow" for h in sheet["holes"])
    assert "e4" not in chips and "e4" not in prose
    # and every hole is somebody's outpost: the mirror is exact
    assert {h["square"] for h in sheet["sides"]["white"]["outposts"]} == chips


def test_a_hole_someone_is_standing_on_is_not_announced_as_empty():
    """`occupied` means the USER's minor is there, so it cannot double as "the
    square is taken": a hole the CAMP's own piece covers is neither occupied nor
    empty by that field, and the prose was announcing it as somewhere a piece
    could land (Codex 2026-07-26). The prose reads `empty`."""
    import chess
    from weaknesses import holes_report
    from fact_sheet import pre_verify_json
    fen = "4k3/8/8/8/5n2/3N4/8/4K3 b - - 0 1"          # White's own knight on d3
    d3, = [h for h in holes_report(chess.Board(fen)) if h["square"] == "d3"]
    assert d3["camp"] == "white" and d3["empty"] is False and d3["occupied"] is False
    line, = [w for w in pre_verify_json(fen, None, None)["sides"]["white"]["weaknesses"]
             if w.startswith("Holes at")]
    assert "d3" not in line.split("—")[0]
    # ...while f4, where BLACK's knight sits in White's camp, is that side's
    # realised outpost rather than an empty square either
    f4, = [h for h in holes_report(chess.Board(fen))
           if h["square"] == "f4" and h["camp"] == "white"]
    assert f4["occupied"] is True and f4["empty"] is False


def test_an_unreachable_hole_is_geography_not_a_target():
    """The chips and the prose apply the SAME relevance rule (Codex
    2026-07-26): an empty prime hole that nobody attacks and no knight can get
    to is a fact about the pawn structure, not a target, and listing it in a
    chip row while the sentence ignored it would rebuild the disagreement this
    unification exists to remove."""
    import chess
    from weaknesses import holes_report
    from fact_sheet import pre_verify_json
    # kings and a pair of rooks: plenty of holes, no knight anywhere, and the
    # rooks reach almost none of them.
    fen = "4k3/8/8/8/8/8/r6r/4K3 w - - 0 40"
    unreachable = [h for h in holes_report(chess.Board(fen))
                   if h["camp"] == "white" and not h["tag"] and h["empty"]
                   and not h["reachable"]]
    assert unreachable, "fixture should contain an unreachable hole"
    sheet = pre_verify_json(fen, None, None)
    chips = {h["square"] for h in sheet["sides"]["white"]["holes"]}
    prose = " ".join(w for w in sheet["sides"]["white"]["weaknesses"]
                     if w.startswith("Holes at"))
    for h in unreachable:
        assert h["square"] not in chips
        assert h["square"] not in prose


def test_harvest_names_the_pawn():
    """Owner 2026-07-26: "Harvest the weak pawns. What weak pawns? It should
    name the exact pawn that is weak that can be harvested." The trigger always
    knew the squares — only the sentence was vague."""
    import chess
    from suggest import build_menus
    # one weak pawn: a5, on a file White has no pawn on and Black cannot support
    b = chess.Board("1r3rk1/1q3ppp/4b3/pPbp4/3P1B2/3Q2PP/1P3PB1/5RK1 w - - 0 26")
    head, = [h for _, _, h, _, _, _ in build_menus(b)["W"] if h.startswith("HARVEST")]
    assert head == "HARVEST the weak pawn on a5"
    # ...and three of them are listed, not summarised as "the weak pawn(s)"
    many = chess.Board("6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32")
    head, = [h for _, _, h, _, _, _ in build_menus(many)["W"] if h.startswith("HARVEST")]
    assert head == "HARVEST the weak pawns on e4, e5, c6"


def test_a_confirmed_harvest_names_the_pawn_the_lines_take(monkeypatch):
    """With several weak pawns the trigger lists them all; the lines take ONE.
    Same rule as the freeing push and the pair-break trade — when the
    confirmation knows the specific, the specific wins."""
    import verify as _verify
    from fact_sheet import post_verify_json
    fen = "6k1/p2n2pp/2pB4/4p3/1PN1p3/P2n1PP1/7P/5K2 w - - 0 32"   # e4, e5, c6
    pvs = [{"cp": 20, "pv": [], "ucis": [], "san": []}]

    monkeypatch.setattr(_verify, "verify_plan",
                        lambda fen, t, fam, **kw: {"verdict": "CONFIRMED-SOUND",
                                                   "family": fam,
                                                   "details": ["e4"],
                                                   "timing": "immediate"})
    plans = post_verify_json(fen, pvs, [])["sides"]["white"]["plans"]
    harvest, = [p for p in plans if "arvest" in p["idea"]]
    assert harvest["idea"] == "Harvest the weak pawn on e4"        # not all three
    assert harvest["details"] == ["e4"]
