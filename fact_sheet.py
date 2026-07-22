"""fact_sheet — the MECHANICAL fact-sheet generator. Zero free-form
authorship: every fact traces to a fixed template over deterministic tool
output (suggest.py's build_menus()/describe(), lucena-engine's static
positional terms). This replaces hand-written prose fact sheets, which
silently let an LLM (the author) be the ungrounded translation layer
between the deterministic tool and the narrating LLM (2026-07-22 finding).

USER RULING (2026-07-22, second pass): the sheet itself must read in
NATURAL LANGUAGE, not machine numbers — no cp values, no corpus-lift
figures, no "engine says" / "strong humans play" framing (those are
implementation details, not facts a coach states to a student). Required
shape:
  1. ASSESSMENT — equal / slightly better / better / winning, in words.
     Sourced from the caller-supplied engine PVs' top-line cp (2026-07-22
     — the static term-sum had no lookahead and mis-scored a hanging pawn
     as a real advantage); falls back to the static sum + a one-ply SEE
     correction if no engine lines were supplied.
  2. POSITION READ — prose, not labeled data lines.
  3. STRUCTURE — name it if the catalog recognizes it (the narrating LLM
     is free to recite textbook theory about a named structure; we don't
     inject that theory ourselves).
  4. PLAN FOR WHITE / PLAN FOR BLACK — the top candidate(s) in plain
     imperative language, no pp/lift/verify jargon.

Two outputs from one call:
  build_fact_sheet(fen, pvs, rolls)   the TEST sheet described above
                                  (the (fen, pvs, rolls) contract: the
                                  caller supplies the rolled lines).
  build_control_prompt(fen)      the CONTROL: same task framing, an OPAQUE
                                  position id, but NO chess facts at all —
                                  measures how much a model free-associates
                                  plausible-sounding chess commentary from
                                  nothing. A real grounding win requires the
                                  TEST sheet to beat this control, not just
                                  read fluently on its own.

FEN REDACTION (2026-07-22 finding): embedding the raw FEN string in a
prompt silently grants full board access to any model that can parse FEN
notation, undermining "reason only from the facts below." Both outputs
here use an opaque id ("POSITION-<hash>") instead of the FEN.
"""
from __future__ import annotations

import hashlib
import re
import sys

import chess

sys.path.insert(0, "/Users/avismara/Development/lucena/engine/python")
from lucena_engine import positional as _positional          # noqa: E402
from lucena_engine.board import Board as _LBoard             # noqa: E402

from structures import classify
from weaknesses import (census, bishop_escape_route, backward_pawns,
                        isolated_pawns, side_rank)
from plan_diff import snapshot, _see
from suggest import (build_menus, name_side, pawn_decomposition, holes_in,
                     skeleton, candidate_family, standing_batteries)

PREAMBLE = (
    "You are a chess coach for an intermediate club player. Below is a "
    "FACT SHEET for one position, identified only by an opaque id (not a "
    "FEN — you cannot parse the board yourself). You have no independent "
    "board access, engine, or other source on this position; use ONLY the "
    "facts given.\n\n"
    "Two reliability tiers, and you must keep them distinct:\n"
    "  - PLAN FOR WHITE/BLACK has been checked against real engine "
    "analysis and human game data FOR THIS EXACT POSITION. Treat these as "
    "confirmed.\n"
    "  - Everything else (the position read, the weaknesses, the pawn "
    "breaks) is board geometry — true facts about the position, but NOT "
    "individually checked against engine lines. Don't imply a listed "
    "weakness or break is currently winning or forcing unless the PLAN "
    "section says so.\n\n"
    "Every fact below is labeled for a specific side (White or Black). A "
    "fact under WEAKNESSES FOR X is a liability for X, not an asset — "
    "don't invert this. Don't invent anything not stated (piece "
    "locations, legal moves, tactics, threats, evaluation, whose king a "
    "square is near) — if unsure which side a fact refers to, reread it "
    "rather than guess.\n\n"
    "Write a short, natural coaching explanation (180-280 words) from "
    "these facts alone."
)

TERMS = ["material", "king_safety", "activity", "pawns", "center"]


def opaque_id(fen: str) -> str:
    return "POSITION-" + hashlib.sha256(fen.encode()).hexdigest()[:10]


def _humanize(s: str) -> str:
    """Sentence-case an ALL-CAPS action head without touching mixed-case
    chess notation (NxB, BxB, square names) — turns 'BREAK THE BISHOP
    PAIR: trade a minor' into 'Break the bishop pair: trade a minor'."""
    s2 = re.sub(r"\b[A-Z]{2,}\b", lambda m: m.group(0).lower(), s)
    return (s2[:1].upper() + s2[1:]) if s2 else s2


def _route_phrase(ev: str) -> str:
    """Pull just the knight-route clause out of a candidate's `ev` field
    (which also carries corpus-lift numbers we must not surface)."""
    parts = [p.strip() for p in ev.split(";")]
    route = [p for p in parts
             if p.startswith("knight route") or p.startswith("knight shortcut")]
    if not route:
        return ""
    return " (" + "; ".join(route) + ")"


def _cap1(s: str) -> str:
    return (s[:1].upper() + s[1:]) if s else s


def _hanging_correction(b: chess.Board) -> int:
    """The best SEE-positive capture available to the side to move, in cp
    (White POV). NOT a search — one-ply static-exchange evaluation, same
    tool as backward_push's preparedness gate. Corrects the static
    material term for pieces that are counted as present but are, in
    fact, already lost: a 4-attacker/1-defender hanging pawn scores as a
    real material edge in the term-sum with zero lookahead, which
    overstates ASSESSMENT (2026-07-22 finding: a real position scored
    'Black clearly better' on an extra pawn that White simply recaptures
    next move for free)."""
    side = b.turn
    best = 0
    for sq in chess.SQUARES:
        occ = b.piece_at(sq)
        if occ is None or occ.color == side:
            continue
        best = max(best, _see(b, sq, side))
    return best * 100 if side == chess.WHITE else -best * 100


def _assessment(total_cp: float) -> str:
    a = abs(total_cp)
    if a < 50:
        return "The position is roughly equal."
    who = "White" if total_cp > 0 else "Black"
    if a < 125:
        return f"{who} is slightly better."
    if a < 250:
        return f"{who} is clearly better."
    return f"{who} is winning."


def _position_read(b: chess.Board, terms: dict, leads: list[str]) -> list[str]:
    """Prose lines: the salient static-eval standings (already natural
    language from lucena_engine), then space/king, material/minors, and
    pawn-skeleton facts. Per-side weaknesses live in their own WEAKNESSES
    FOR WHITE/BLACK sections (_weakness_lines), not mixed in here."""
    L = []
    seen = set()
    for k in leads:
        L.append(_cap1(terms[k]["standing"]) + ".")
        seen.add(k)
    for k in TERMS:
        if k not in seen and abs(terms[k]["cp"]) >= 15:
            L.append(_cap1(terms[k]["standing"]) + ".")
    L.append(_space_words(b))
    L.append(_material_words(b))
    wi = terms["pawns"]["features"]["white"]["islands"]
    bi = terms["pawns"]["features"]["black"]["islands"]
    L.append(f"White's pawns form {wi} island{'s' if wi != 1 else ''}; "
             f"Black's form {bi} island{'s' if bi != 1 else ''}.")
    L.extend(_skeleton_lever_words(b))
    bats = standing_batteries(b)
    for t in ("W", "B"):
        name = "White" if t == "W" else "Black"
        for fn, kind in bats[t]:
            L.append(f"{name} has heavy pieces doubled on the {kind} "
                     f"{fn}-file — a standing battery.")
    for t, side in (("W", chess.WHITE), ("B", chess.BLACK)):
        s = snapshot(b)
        if s[f"{t}.n_passers"]:
            name = "White" if side == chess.WHITE else "Black"
            kinds = [k for k, f in (("protected", s[f"{t}.protected_passer"]),
                                    ("outside", s[f"{t}.outside_passer"]),
                                    ("connected", s[f"{t}.connected_passers"]))
                    if f]
            pas = _passer_squares(b, side)
            names = ", ".join(chess.square_name(q) for q in pas)
            txt = (f"{name}'s passed pawn"
                   f"{'s' if len(pas) > 1 else ''}: {names}")
            if kinds:
                txt += " (" + ", ".join(kinds) + ")"
            L.append(txt + ".")
            # A passed ISOLANI is deliberately NOT a weakness (see
            # isolated_pawns' exclusion) — but its isolation is still a
            # coaching fact: no pawn can ever escort it (2026-07-22, the
            # d6 question).
            own_files = {chess.square_file(p)
                         for p in b.pieces(chess.PAWN, side)}
            for q in pas:
                f = chess.square_file(q)
                if not ({f - 1, f + 1} & own_files):
                    L.append(f"The {chess.square_name(q)} passer has no "
                             "neighbor pawn to escort it — it advances "
                             "only with piece support.")
    return L


def _passer_squares(b: chess.Board, side: bool) -> list[int]:
    """Own pawns with no enemy pawn ahead on the same or adjacent files
    (mirrors plan_diff's snapshot passer rule, which stores only counts)."""
    out = []
    for sq in b.pieces(chess.PAWN, side):
        f, r = chess.square_file(sq), side_rank(sq, side)
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r
                   for s in b.pieces(chess.PAWN, not side)):
            out.append(sq)
    return out


def _material_words(b: chess.Board) -> str:
    s = snapshot(b)
    wB, bB = s["W.bishops"], s["B.bishops"]
    wN, bN = s["W.knights"], s["B.knights"]
    line = (f"White has {wB} bishop(s) and {wN} knight(s); Black has {bB} "
           f"bishop(s) and {bN} knight(s).")
    if s["W.has_pair"] != s["B.has_pair"]:
        who = "White" if s["W.has_pair"] else "Black"
        line += f" {who} holds the bishop pair."
    if wB == 1 and bB == 1:
        wsq = next(iter(s["W.bishop_sqs"]))
        bsq = next(iter(s["B.bishop_sqs"]))
        light = lambda q: bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[q])
        if light(wsq) != light(bsq):
            line += " The bishops are opposite-colored."
    return line


def _skeleton_lever_words(b: chess.Board) -> list[str]:
    """Rams/tension/open-files/majorities/levers — parsed from the same
    structured computations pawn_decomposition()/skeleton() already do
    (single source of truth; this only rephrases their output as prose,
    it doesn't recompute anything)."""
    out = []
    rams, central, tension, open_files = skeleton(b)
    closed = central >= 2 and open_files == 0 and tension <= 1 and rams >= 4
    if closed:
        out.append("The center is completely locked — no file can ever be "
                   "forced open by pawn play alone.")
    elif rams >= 2:
        out.append(f"There are {rams} pawns locked head-to-head across the "
                   "board.")
    lines = pawn_decomposition(b)
    files_line = next(l for l in lines if l.strip().startswith("files:"))
    m = re.search(r"open (.*?) \| semi-open for White: (.*?) \| for Black: "
                 r"(.*)", files_line)
    open_f, semi_w, semi_b = (g.strip() for g in m.groups())
    if open_f != "-":
        out.append(f"The {open_f.replace(',', '/')}-file is fully open.")
    if semi_w != "-":
        out.append(f"The {semi_w.replace(',', '/')}-file is semi-open for "
                   "White.")
    if semi_b != "-":
        out.append(f"The {semi_b.replace(',', '/')}-file is semi-open for "
                   "Black.")
    maj_line = next(l for l in lines if l.strip().startswith("majorities:"))
    maj_txt = maj_line.split(":", 1)[1].strip()
    if maj_txt and not maj_txt.startswith("none"):
        parts = []
        for chunk in maj_txt.split(";"):
            mm = re.search(r"(\w+) (\d)v(\d) \((\w+)\)", chunk)
            if mm:
                wing, wc, bc, who = mm.groups()
                own, other = (wc, bc) if who == "White" else (bc, wc)
                parts.append(f"{who} has a pawn majority on the {wing} "
                             f"({own} vs {other})")
        if parts:
            out.append(". ".join(parts) + ".")
    for side_name, prefix in (("White", "White levers"),
                              ("Black", "Black levers")):
        lv = next((l for l in lines if l.strip().startswith(prefix)), None)
        if not lv:
            continue
        mm = re.search(r"now (.*?) \| one move away: (.*)", lv)
        if not mm:
            continue
        now, pot = (g.strip() for g in mm.groups())
        if now != "-":
            out.append(f"{side_name} can immediately trade pawns with "
                       + now.replace(",", " or ") + ".")
        if pot != "-":
            out.append(f"{side_name}'s next pawn break available: " + pot + ".")
    return out


_HOLE_TAG_WORDS = {"": "a deep, central hole", "rim": "a hole along the edge "
                   "(a/h-file, low value)", "shallow": "a shallow hole "
                   "(only 3 ranks in)"}


def _weakness_lines(b: chess.Board, terms: dict, side: bool,
                    pvs: list | None = None,
                    rolls: list | None = None) -> list[str]:
    """Everything the original mechanical sheet said about ONE side's camp
    that IS actually a weakness — weak pawns (backward ones called out by
    name), entombed bishop (with escape route if one exists), occupied
    outposts, exposed king, doubled pawns, holes, plus the rest of the
    census vocabulary (passive rooks, weak color complex, back-rank,
    overextended pawns) that was computed but never surfaced before.
    Absent weaknesses are simply omitted — no 'No X' lines; pawn islands
    are a structural feature, not a weakness, and live in POSITION READ."""
    name = "White" if side == chess.WHITE else "Black"
    other = "Black" if side == chess.WHITE else "White"
    pf_key = "white" if side == chess.WHITE else "black"
    c = census(b, side)
    f = terms["pawns"]["features"][pf_key]
    L = []
    backward = backward_pawns(b, side)          # Kmoch (2026-07-22 ruling)
    back_sqs = {q for q, _ in backward}
    for q, half in backward:
        L.append(f"Backward pawn on {chess.square_name(q)} — behind its "
                 "neighbors, and its advance square is controlled by "
                 f"{other}'s pawns"
                 + (f"; it sits on a file {other} can pile onto"
                    if half else "") + ".")
    iso = isolated_pawns(b, side)
    for q, half in iso:
        L.append(f"Isolated pawn on {chess.square_name(q)} — no neighbor "
                 "pawn can ever defend it"
                 + (f", and it sits on a file {other} can pile onto"
                    if half else "") + ".")
    iso_sqs = {q for q, _ in iso}
    plain_weak = [q for q in c["weak_pawns"]
                  if q not in back_sqs and q not in iso_sqs]
    if plain_weak:
        L.append("Weak pawn(s) at "
                 + ", ".join(sorted(chess.square_name(q)
                                    for q in plain_weak)) + ".")
    for bsq in c["entombed_bishops"]:
        # EXTRACTION verification (2026-07-22, user ask): the printed way
        # out must be what the ENGINE's lines play, not the BFS exit —
        # KNOWN_ISSUES #5's evidence had 'e3-g5' printed while every line
        # extracted via a recapture on d4. Forward-track the bishop
        # through the firing eval-equal lines; the geometric route is
        # demoted to an explicitly-unverified aside when no line plays it.
        sqb = chess.square_name(bsq)
        obs, traded = [], False
        if pvs is not None or rolls is not None:
            from verify import verify_plan
            t2 = "W" if side == chess.WHITE else "B"
            for fam in ("bad_bishop_escape", "bad_bishop_trade"):
                v = verify_plan(b.fen(), t2, fam, pvs, rolls, track=sqb)
                if v["verdict"] in _CONFIRMED and v.get("routes"):
                    obs, traded = v["routes"], fam == "bad_bishop_trade"
                    break
        route = bishop_escape_route(b, side, bsq)
        if obs and traded:
            L.append(f"The bishop on {sqb} is shut in behind its own "
                     "pawns; the engine's lines resolve it by TRADING it "
                     "off (" + " or ".join(obs[:2]) + ").")
        elif obs:
            L.append(f"The bishop on {sqb} is shut in behind its own "
                     "pawns, but the engine's lines extract it: "
                     + " or ".join(obs[:2]) + ".")
        elif route:
            L.append(f"The bishop on {sqb} is shut in behind its own "
                     "pawns; a geometric way out exists ("
                     + "-".join(chess.square_name(x) for x in route)
                     + "), though the engine's lines don't play the "
                     "extraction here.")
        else:
            L.append(f"The bishop on {sqb} is shut in "
                     "behind its own pawns with no way out.")
    from weaknesses import bad_bishop as _bb, bishop_inside_chain, \
        bishop_confinement
    ent_sqs = set(c["entombed_bishops"])
    for bsq in _bb(b, side):
        if bsq in ent_sqs:
            continue   # already reported as entombed (stronger statement)
        if bishop_inside_chain(b, side, bsq):
            # Wall-vs-door split (2026-07-22 user ruling: the Carlsbad c1
            # bishop isn't 'choked' — it stands BETWEEN two chains and one
            # pawn tempo opens it). 'Badly choking it' is reserved for
            # bishops whose blockers are all FIXED; a doored bishop is
            # stated as undeveloped-with-a-door, naming the door move —
            # which also stops this line contradicting a confirmed
            # FREE-THE-BISHOP plan in the same sheet.
            conf = bishop_confinement(b, side, bsq)
            if conf["doors"]:
                doors = ", ".join(f"{chess.square_name(p)}-"
                                  f"{chess.square_name(q)}"
                                  for p, q in conf["doors"])
                L.append(f"The bishop on {chess.square_name(bsq)} is "
                         f"undeveloped, hemmed between {name}'s pawn "
                         "chains — but its blockers aren't fixed: "
                         f"{doors} opens lines for it.")
            elif conf["open"]:
                L.append(f"The bishop on {chess.square_name(bsq)} has "
                         f"most of {name}'s pawns on its color, but keeps "
                         "a clear diagonal — it can reposition rather "
                         "than break out.")
            else:
                L.append(f"The bishop on {chess.square_name(bsq)} is bad "
                         f"and sits INSIDE its own pawn chain — most of "
                         f"{name}'s pawns are on its color and in front "
                         "of it, badly choking it.")
        else:
            L.append(f"The bishop on {chess.square_name(bsq)} is a bad "
                     f"bishop but stands OUTSIDE the pawn chain — most of "
                     f"{name}'s pawns are on its color, but it has scope on "
                     "the outside, so the problem is mild (worth exchanging, "
                     "not critical).")
    if c["occupied_outposts"]:
        L.append(f"{other} has a piece permanently anchored on "
                 + ", ".join(sorted(chess.square_name(q)
                                    for q in c["occupied_outposts"]))
                 + " in this camp.")
    if c["exposed_king"]:
        L.append(f"{name}'s king is exposed (open lanes toward it).")
    if c["passive_rooks"]:
        L.append("Rook(s) on "
                 + ", ".join(sorted(chess.square_name(q)
                                    for q in c["passive_rooks"]))
                 + " with no file to ever get active on.")
    if c["weak_color_complex"]:
        wcc = sorted(c["weak_color_complex"])
        color = "light" if chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[
            wcc[0]] else "dark"
        L.append(f"A weak {color}-square complex around {name}'s king on "
                 + ", ".join(chess.square_name(q) for q in wcc)
                 + f" — no bishop of that color is left to cover them.")
    if c["back_rank_weak"]:
        L.append(f"{name}'s king has no luft — the back rank is a mating "
                 "vulnerability.")
    if c["overextended_pawns"]:
        L.append("Overextended pawn(s) at "
                 + ", ".join(sorted(chess.square_name(q)
                                    for q in c["overextended_pawns"]))
                 + " — advanced past any support and not passed.")
    if f["doubled_files"]:
        L.append("Doubled pawns on the "
                 + "/".join(f["doubled_files"]) + "-file"
                 + ("s" if len(f["doubled_files"]) > 1 else "") + ".")
    hz = holes_in(b, side)
    if hz:
        by_tag = {}
        for h, tag in hz:
            by_tag.setdefault(tag, []).append(h)
        bits = [f"{', '.join(sqs)} ({_HOLE_TAG_WORDS[tag]})"
               for tag, sqs in by_tag.items()]
        L.append(f"Holes in {name}'s camp (squares no {name} pawn can ever "
                 f"guard, which {other} can aim to occupy): "
                 + "; ".join(bits) + ".")
    return L or ["No significant weaknesses."]


def _space_words(b: chess.Board) -> str:
    """Castling status is stated as a plain geometric fact only — NOT a
    safety judgment. The safety verdict ('reasonably safe' / 'a little
    exposed' / 'in danger') already comes from the king_safety term's own
    `standing` text (surfaced earlier in _position_read via leads/
    threshold); re-deriving a second, independent judgment here from
    castled-status alone risks contradicting the API's actual danger
    score (2026-07-22 finding: it did, on a real position)."""
    s = snapshot(b)
    dw = s["W.space"] - s["B.space"]
    king_bits = []
    for t, name in (("W", "White"), ("B", "Black")):
        if s[f"{t}.castled"]:
            base = f"{name}'s king has castled"
        elif s[f"{t}.can_castle"]:
            base = f"{name}'s king hasn't castled yet but still can"
        elif s[f"{t}.king_central"]:
            base = f"{name}'s king is still in the center, uncastled"
        else:
            base = f"{name}'s king never castled and can no longer"
        king_bits.append(base)
    line = "; ".join(king_bits) + "."
    if abs(dw) >= 6:
        who, other = ("White", "Black") if dw > 0 else ("Black", "White")
        line = (f"{who} controls considerably more space than {other}. "
                + line)
    elif abs(dw) >= 3:
        who, other = ("White", "Black") if dw > 0 else ("Black", "White")
        line = f"{who} has a modest space edge over {other}. " + line
    return line


_CONFIRMED = {"CONFIRMED-SOUND", "CONFIRMED-SOUND-LATER", "MAIA-TYPICAL"}


def _pair_break_words(d: str) -> str:
    """plan_diff's pair_break detail ('NxB@d3', 'BxB@f4', 'N-offer@d5',
    'B-offer@c4') in coaching words."""
    if "@" not in d:
        return d
    kind, sq = d.split("@", 1)
    return {
        "NxB": f"the knight takes the bishop on {sq}",
        "BxB": f"the bishop takes the bishop on {sq}",
        "N-offer": f"offer the knight on {sq} so the bishop must take it",
        "B-offer": f"offer the bishop on {sq} so their bishop must take it",
    }.get(kind, d)


def _plan_lines(menus: dict, t: str, fen: str, pvs, rolls,
                max_n: int = 3) -> list[str]:
    """VERIFY-GATED plan list (user ruling 2026-07-22: 'SUGGEST by itself
    is useless — never surface unverified engine-contract plans'). Every
    candidate that carries a plan_diff family is checked against the
    position's ROLLED lines (banked engine PVs + Maia rollouts — zero new
    engine calls); it survives only if it appears in an eval-equal engine
    line or is Maia-typical FOR THIS POSITION. The corpus effect size is
    now only the tiebreaker AMONG confirmed plans, not the admission
    ticket. Advisory-tier candidates (no family: SIMPLIFY, AVOID TRADES,
    the literature weakness matrix) are a separate epistemic tier and pass
    through unverified — their evidence is the corpus dose-response curve,
    not a per-position engine line."""
    from verify import verify_plan
    from weaknesses import knight_route
    b = chess.Board(fen)
    side = chess.WHITE if t == "W" else chess.BLACK
    confirmed, advisory = [], []
    for eff, trig, head, ev, verify, tsq in sorted(menus[t], key=lambda x: -x[0]):
        fams = candidate_family(head)
        if not fams:
            # Advisory tier: keep ONLY the ones backed by a real corpus
            # dose-response curve (user ruling 2026-07-22: 'drop the
            # uncalibrated ones'). SIMPLIFY / AVOID TRADES are calibrated
            # (|space| >= 6, +9pp); the literature weakness matrix
            # (BESIEGE/LIQUIDATE/...) and situational plans (PROPHYLAXIS/
            # DEFEND) say 'calibration pending' or cite no curve — dropped
            # until each earns a number, same bar as engine-contract plans.
            if "calibration pending" not in ev and "literature tier" \
                    not in verify and "situational" not in ev:
                advisory.append((eff, head, ev))
            continue
        if pvs is None and rolls is None:
            continue   # engine-contract plan, no rolled data to confirm it
        hops = None
        if tsq:
            r = knight_route(b, side, {chess.parse_square(tsq)})
            hops = len(r) - 1 if r else None
        won = None
        for fam in fams:
            # EXTRACTION plans (2026-07-22): the emitter names no square, so
            # the observed route comes from forward-tracking the bishop
            # itself (its square is in the trigger text) — the printed
            # route must be what the lines play, never the BFS exit.
            track = None
            if fam in ("bad_bishop_escape", "bad_bishop_trade"):
                m = re.search(r"bishop ([a-h][1-8])", trig)
                track = m.group(1) if m else None
            v = verify_plan(fen, t, fam, square=tsq, route_hops=hops,
                            pvs=pvs, rolls=rolls, track=track)
            if v["verdict"] in _CONFIRMED:
                won = v
                break
        if won:
            confirmed.append((eff, head, ev, won))
    # TIMING is a PLAN-level fact (when this idea matures), never a move
    # recommendation (user ruling 2026-07-22: "do NOT pick the best engine
    # move and suggest in the plan... this is NOT to suggest the next
    # move, but to suggest plans" — so no `immediate_move` here, ever).
    out = []
    for _, h, e, v in confirmed[:max_n]:
        # FREE THE BAD BISHOP: name the SPECIFIC freeing push(es), and only
        # the ones the eval-equal engine lines actually play (2026-07-22
        # ruling: 'name specific pawns... only if it appears in the engine
        # lines — right now it's too generic'). The details come from the
        # verified lines themselves (plan_diff's emitter records the exact
        # push, e.g. 'b2-b3'), never from the raw geometric menu of every
        # push that merely exists.
        if v.get("family") == "free_bad_bishop" and v.get("details"):
            pushes = " or ".join(v["details"])
            line = (f"- Free the bad bishop with {pushes} — the freeing "
                    "push the engine's own lines play")
        elif v.get("family") == "pair_break" and v.get("details"):
            # Same ruling, sharper case (2026-07-22: the d7-b8-a6-b4-d3
            # knight route printed on this plan appeared in ZERO rolled
            # lines — the plan verified via a different arm entirely,
            # BxB@f4). State the mechanism the lines actually play and
            # DROP the geometric route annotation.
            ways = " or ".join(_pair_break_words(d) for d in v["details"])
            line = (f"- Break the bishop pair: {ways} — the trade the "
                    "engine's lines play")
        elif v.get("family") == "passer_creation" \
                and h.startswith("PUSH THE PASSER"):
            # The clubbed PUSH-THE-PASSER candidate maps to two families
            # (push the existing passer / create a new one). When only
            # CREATION confirmed, advancing the existing passer is NOT
            # what the verified lines play — say what actually confirmed
            # (2026-07-22: the d6 case — passer_push NOT-IN-BEST-LINES,
            # passer_creation Maia-typical, yet the sheet said 'push').
            line = ("- Create another passed pawn — the passer plan the "
                    "verified lines play here (advancing the existing "
                    "passer is not in the engine's best lines)")
        elif v.get("family") == "attack_passer" and v.get("details"):
            # Detail comes from the line itself: 'd6, taken by the rook' /
            # 'd6, attacked by rook+knight' (2026-07-22, user-defined —
            # the attacking pieces are extracted deterministically).
            facts = "; ".join(v["details"][:2])
            line = f"- Attack the enemy passer — in the verified lines: {facts}"
            if v.get("routes"):
                line += f" (attacker's route: {v['routes'][0]})"
        elif v.get("routes"):
            # Square-bearing plans (outposts, knight maneuvers): print the
            # OBSERVED journey(s) from the firing eval-equal lines — each a
            # route a distinct engine line plays — and drop the geometric
            # BFS clause (suggest proposes, verify filters; 2026-07-22).
            line = ("- " + _humanize(h) + " (route the engine plays: "
                    + " or ".join(v["routes"][:2]) + ")")
        else:
            line = "- " + _humanize(h) + _route_phrase(e)
        if v.get("timing") == "immediate":
            line += " — playable in the short term."
        elif v.get("timing") == "developing":
            line += " — not immediate: other moves happen first."
        elif v.get("timing") == "long-term":
            line += " — a longer-term idea, not for right now."
        out.append(line)
    for eff, h, e in advisory[:max_n]:
        out.append("- " + _humanize(h) + "  [general principle, not "
                   "position-verified]")
    return out or ["- no plan is confirmed by the engine/human-play lines "
                   "in this position."]


def build_fact_sheet(fen: str, pvs: list | None, rolls: list | None,
                     verify_results: list[dict] | None = None
                     ) -> tuple[str, str]:
    """Returns (sheet, opaque_id) — the fact sheet text ONLY, no PREAMBLE
    and no LLM-prompt wrapper.

    THE CONTRACT: (fen, pvs, rolls). This module never rolls — the caller
    supplies the position's engine PVs and Maia rollouts (a horizon-25
    MultiPV=4 roll covers nearly every family; the same lines feed every
    candidate's verify_plan call below). Pass None for an absent leg:
    engine-contract plans then can't be confirmed and are not surfaced,
    and ASSESSMENT falls back to the static term-sum.

    `verify_results` (optional list of verify.verify_plan() dicts) is
    folded in as plain sentences — e.g. 'This has been checked against
    engine lines and looks sound' — never as raw verdict jargon. Callers
    that need an LLM prompt should wrap the returned sheet themselves
    (see build_control_prompt for the framing)."""
    b = chess.Board(fen)
    pid = opaque_id(fen)
    d = _positional.analyze_positional(_LBoard(fen))
    terms, leads = d["terms"], d["leads"]
    menus = build_menus(b)
    ecp = pvs[0]["cp"] if pvs else None
    total = ecp if ecp is not None else (
        sum(v["cp"] for v in terms.values()) + _hanging_correction(b))

    lines = [f"=== POSITION ({pid}) ==="]
    lines.append("")
    # DYNAMISM (2026-07-22, user ruling): the eval number alone must never
    # imply 'quiet' — 0.00 spans dead-drawn to razor-sharp. The character
    # verdict is deterministic from the same banked lines (narrowness /
    # forcing density / human divergence / board tension), with its
    # evidence named.
    from dynamism import dynamism as _dyn
    d_dy = _dyn(fen, pvs, rolls)
    dy_txt = f" Character: {d_dy['summary']}"
    if d_dy["components"]:
        dy_txt += (" — "
                   + "; ".join(w for _, _, w in d_dy["components"][:2]))
    lines.append("ASSESSMENT: " + _assessment(total) + dy_txt + ".")
    lines.append("")
    lines.append("POSITION READ:")
    for ln in _position_read(b, terms, leads):
        lines.append("  " + ln)
    lines.append("")
    structs = classify(b)
    if structs:
        lines.append("STRUCTURE: " + "; ".join(
            f"{n} (owned by {name_side(o)})" for n, o in structs)
            + ". (Standard textbook theory for this structure may be "
              "drawn on.)")
    else:
        lines.append("STRUCTURE: no textbook structure from the catalog "
                     "is recognized here.")
    lines.append("")
    lines.append("WEAKNESSES FOR WHITE:")
    for ln in _weakness_lines(b, terms, chess.WHITE, pvs, rolls):
        lines.append("  " + ln)
    lines.append("")
    lines.append("WEAKNESSES FOR BLACK:")
    for ln in _weakness_lines(b, terms, chess.BLACK, pvs, rolls):
        lines.append("  " + ln)
    lines.append("")
    from tension import analyze as _tension, render as _trender
    tsec = _trender(_tension(fen, pvs, rolls))
    if tsec:
        lines.extend(tsec)
        lines.append("")
    lines.append("PLAN FOR WHITE:")
    lines.extend(_plan_lines(menus, "W", fen, pvs, rolls))
    lines.append("")
    lines.append("PLAN FOR BLACK:")
    lines.extend(_plan_lines(menus, "B", fen, pvs, rolls))
    lines.append("")
    if verify_results:
        lines.append("NOTES:")
        for v in verify_results:
            lines.append("  " + _verify_sentence(v))
    sheet = "\n".join(lines)
    return sheet, pid


def _verify_sentence(v: dict) -> str:
    who = "White" if v["side"] == "W" else "Black"
    fam = v["family"].replace("_", " ")
    if v["verdict"] in ("CONFIRMED-SOUND", "CONFIRMED-SOUND-LATER"):
        return f"{who}'s {fam} plan has been checked and holds up."
    if v["verdict"] == "MAIA-TYPICAL":
        return f"{who}'s {fam} plan is typical of how strong players handle this."
    return f"{who}'s {fam} plan has not been confirmed as sound here."


def build_control_prompt(fen: str) -> tuple[str, str]:
    """The CONTROL: identical task framing and an opaque position id, but
    ZERO chess facts. Tests how much of a narrating model's output is
    genuine grounding vs fluent free-association. A real pass requires the
    TEST sheet's output to differ meaningfully from this — matching prose
    quality on the control with no facts is a red flag, not a pass."""
    pid = opaque_id(fen)
    prompt = (
        f"{PREAMBLE}\n\n"
        f"=== POSITION ({pid}) ===\n"
        f"(No facts are available for this position. The analysis tool "
        f"returned no data.)\n"
        f"=== END FACT SHEET ===\n\n"
        f"Write the coaching explanation now, using only what's above."
    )
    return prompt, pid


if __name__ == "__main__":
    # ./fact_sheet.py "FEN" [bank.json]
    # bank.json = {"pvs": [...], "rolls": [...]}. Without a bank, rolls
    # live through the research harness (~1-2 min: one engine search + K
    # policy rollouts; the library itself never rolls).
    import json
    import os
    fen = sys.argv[1]
    if len(sys.argv) > 2:
        bank = json.load(open(sys.argv[2]))
    else:
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "experiments", "tools"))
        from rolls import roll_both
        bank = roll_both(fen, 25)
    sheet, pid = build_fact_sheet(fen, bank.get("pvs"), bank.get("rolls"))
    print(sheet)
    print(f"\n[opaque id: {pid}]", file=sys.stderr)
