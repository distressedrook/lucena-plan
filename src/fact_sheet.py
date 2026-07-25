#!/usr/bin/env python3
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
import logging
import re
import sys

import chess

_log = logging.getLogger(__name__)

# lucena_core is pip-installed (editable) — no path hacks (2026-07-23 core migration)
from lucena_core import positional as _positional          # noqa: E402
from lucena_core.board import Board as _LBoard             # noqa: E402

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


def _looks_like_fen(s: str) -> bool:
    """A board string (first field has 8 ranks) — the piece placement that
    hands a FEN-literate reader the position."""
    if not isinstance(s, str) or " " not in s:
        return False
    first = s.split(" ", 1)[0]
    return first.count("/") == 7 and any(c.isalpha() for c in first)


def _redact_fens(obj):
    """Recursively replace every FEN-valued field in the assembled sheet
    with its opaque POSITION-<hash> id (2026-07-24 fix). The redaction
    invariant is whole-sheet, not just the root: quiescence walks in
    `settled`/`material_stability`/`line_theories` (from lucena_core.metrics)
    embed walked-out FENs under keys like `fen`/`settled_fen`, each just as
    board-revealing as the root. A consumer keeps a stable position handle;
    the board itself never reaches the narrating model."""
    if isinstance(obj, dict):
        return {k: (opaque_id(v) if isinstance(v, str) and _looks_like_fen(v)
                    else _redact_fens(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_fens(v) for v in obj]
    if isinstance(obj, str) and _looks_like_fen(obj):
        return opaque_id(obj)
    return obj


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
        out.append("The center is completely locked.")
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
        L.append(f"Backward pawn on {chess.square_name(q)}"
                 + (f" — on a file {other} can pile onto"
                    if half else "") + ".")
    iso = isolated_pawns(b, side)
    for q, half in iso:
        L.append(f"Isolated pawn on {chess.square_name(q)}"
                 + (f" — on a file {other} can pile onto"
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
            L.append(f"Bad bishop on {sqb}. Try trading it off with "
                     + " or ".join(obs[:2]) + ".")
        elif obs:
            L.append(f"Bad bishop on {sqb}. Try maneuvering it out via "
                     + " or ".join(obs[:2]) + ".")
        elif route:
            L.append(f"Bad bishop on {sqb}. Try maneuvering it via "
                     + "-".join(chess.square_name(x) for x in route) + ".")
        else:
            L.append(f"Entombed bishop on {sqb}.")
    # INSIDE-the-chain bishops only (2026-07-25, owner: "why is the bishop on
    # h4 bad?"). An outside bishop scores 0.517 against the inside bishop's
    # 0.470 — finding 4's own numbers say it is not a weakness, so the sheet
    # no longer says it is. See weaknesses.bad_bishop_problem.
    from weaknesses import bad_bishop_problem as _bb, bishop_confinement
    ent_sqs = set(c["entombed_bishops"])
    for bsq in _bb(b, side):
        if bsq in ent_sqs:
            continue   # already reported as entombed (stronger statement)
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
                     "undeveloped but not fixed — "
                     f"{doors} opens it.")
        elif conf["open"]:
            L.append(f"The bishop on {chess.square_name(bsq)} has "
                     f"most of {name}'s pawns on its color but keeps "
                     "a clear diagonal.")
        else:
            L.append(f"Bad bishop on {chess.square_name(bsq)}, "
                     "inside its own pawn chain.")
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
                 + ", ".join(chess.square_name(q) for q in wcc) + ".")
    if c["back_rank_weak"]:
        L.append(f"{name}'s king has no luft.")
    if c["overextended_pawns"]:
        L.append("Overextended pawn(s) at "
                 + ", ".join(sorted(chess.square_name(q)
                                    for q in c["overextended_pawns"]))
                 + " — advanced past any support and not passed.")
    if f["doubled_files"]:
        L.append("Doubled pawns on the "
                 + "/".join(f["doubled_files"]) + "-file"
                 + ("s" if len(f["doubled_files"]) > 1 else "") + ".")
    # HOLES — only the IMPORTANT ones (owner 2026-07-25: "bringing up all the
    # holes is what is cluttering information"). The repo's own corpus laws
    # define important: rim holes price at nothing (0.496), shallow at 0.509
    # — dropped; a deep hole matters when the enemy can actually USE it
    # (attacked now, or a knight route reaches it — occupied ones are already
    # the "piece permanently anchored" line above). Cap 3.
    from weaknesses import knight_route as _kr
    keep = []
    for h, tag in holes_in(b, side):
        if tag:                                   # rim / shallow — noise
            continue
        sq = chess.parse_square(h)
        pc = b.piece_at(sq)
        if pc is not None and pc.color != side:
            continue                              # occupied outpost line owns it
        if b.attackers(not side, sq) or _kr(b, not side, {sq}):
            keep.append(h)
    if keep:
        L.append(f"Holes at {', '.join(keep[:3])}.")
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


_CONFIRMED = {"CONFIRMED-SOUND", "CONFIRMED-SOUND-LATER", "HUMAN-TYPICAL"}


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
        for fam in sorted(fams):   # deterministic order (2026-07-24 fix): a
            # set iteration let the same (fen,pvs,rolls) confirm via a
            # different family run-to-run under hash randomization
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
        elif v["verdict"] == "HUMAN-TYPICAL":
            # No engine leg fired (or it did but not within horizon) — only
            # human/policy rollouts confirm this, so `routes`/`timing` are
            # empty (both are engine-only fields; ply-level lag has no
            # meaning for a Maia rollout). 2026-07-22: this used to fall
            # through to the raw geometric BFS route with no signal that
            # the claim is weaker evidence — indistinguishable from an
            # engine-confirmed plan. Say the tier honestly instead; the
            # geometric route is still useful context, so keep it, but
            # never let it read as engine-verified.
            frac = round((v.get("maia") or {}).get("frac", 0) * 100)
            line = ("- " + _humanize(h) + _route_phrase(e)
                    + f" — typical of strong human play here ({frac}% of "
                      "rollouts), though the engine's own lines don't "
                      "confirm it")
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

    THIS IS A GROUNDING ARTIFACT, FOR A MODEL — exhaustive, redundant and
    hedged by design, so a narrator could select from it. It is NOT the
    user-facing presentation (owner 2026-07-24: "build fact sheet existed
    FOR the LLM"); that is `position_read.render`, which selects and
    orders instead of dumping.

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
    if v["verdict"] == "HUMAN-TYPICAL":
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
            "..", "research", "experiments", "tools"))
        from rolls import roll_both
        bank = roll_both(fen, 25)
    sheet, pid = build_fact_sheet(fen, bank.get("pvs"), bank.get("rolls"))
    print(sheet)
    print(f"\n[opaque id: {pid}]", file=sys.stderr)


# ═══════════════════════════════════════════════════════════════════════
# JSON sheets (2026-07-24, owner ruling): the plans layer emits STRUCTURED
# artifacts — a PRE-verify JSON (full sheet, every candidate from SUGGEST,
# unverified) and a POST-verify JSON (same shape, verdict/timing filled,
# unconfirmed candidates MARKED, never deleted). The text sheet is retired
# from the product path (build_fact_sheet stays for research
# reproducibility only). Standing rules carried into the schema:
#   - timing is a PLAN-level fact; no immediate_move field exists, ever
#     (user ruling 2026-07-22: plans, not move recommendations)
#   - consumers must SPEAK the evidence tier with the candidate (owner
#     2026-07-25): engine-confirmed / strong-human / structural, read off
#     `verdict`, never merged. Unverified entries are no longer hidden —
#     position_read.render labels them (dropping them cost real plans; see
#     that module's docstring) — but a structural candidate must never be
#     presented as though an engine line confirmed it
# ═══════════════════════════════════════════════════════════════════════

SHEET_SCHEMA = "lucena-plans/sheet@1"


def _candidates(b: chess.Board, menus: dict, t: str, fen: str,
                pvs, rolls, *, verify: bool) -> tuple[list[dict], list[dict]]:
    """(plan_entries, advisory_entries) for side `t` ('W'/'B'). Mirrors
    _plan_lines' candidate walk; emits data instead of sentences."""
    from verify import verify_plan
    from weaknesses import knight_route
    side = chess.WHITE if t == "W" else chess.BLACK
    plans, advisory = [], []
    for eff, trig, head, ev, verify_note, tsq in sorted(menus[t], key=lambda x: -x[0]):
        fams = candidate_family(head)
        if not fams:
            if "calibration pending" not in ev and "literature tier" \
                    not in verify_note and "situational" not in ev:
                # `effect` travels with the advisory entry too (2026-07-25):
                # it and the unconfirmed family plans share ONE tier in the
                # read, so they have to be rankable against each other —
                # without it every advisory idea sorted below every
                # structural plan regardless of its corpus effect.
                advisory.append({"idea": _humanize(head), "evidence": ev,
                                 "effect": eff})
            continue
        entry: dict = {
            "idea": _humanize(head),
            "families": list(fams),
            "trigger": trig,
            "target": tsq,
            "effect": eff,
            "route_note": _route_phrase(ev).strip(" ()") or None,
            "verified": None,          # pre-verify: unknown
            "verdict": None,
            "timing": None,
            "maia_frac": None,
            "family": None,            # the confirming arm (set on win)
            "details": [],             # line-derived specifics (set on win)
            "routes": [],              # observed journeys (set on win)
        }
        if verify:
            if pvs is None and rolls is None:
                entry["verified"] = False
                entry["verdict"] = "NO-ROLLED-DATA"
            else:
                hops = None
                if tsq:
                    r = knight_route(b, side, {chess.parse_square(tsq)})
                    hops = len(r) - 1 if r else None
                won = None
                for fam in sorted(fams):   # deterministic (2026-07-24 fix)
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
                    entry["verified"] = True
                    entry["verdict"] = won["verdict"]
                    entry["timing"] = won.get("timing")
                    # which arm of a clubbed candidate actually confirmed
                    # (e.g. families [passer_push, passer_creation] but only
                    # passer_creation fired) — the JSON consumer needs this to
                    # phrase the plan correctly (2026-07-24 fix).
                    entry["family"] = won.get("family")
                    # SPECIFICS COME FROM THE FIRING LINES, NEVER GEOMETRY
                    # (2026-07-24 fix, the ruling the text renderer already
                    # follows): carry the emitter's own details + the observed
                    # journeys, and DROP the geometric route_note when the
                    # lines produced their own — this un-does the phantom
                    # knight-route (a pair_break confirmed via BxB@f4 must not
                    # print a d7-b8-a6-b4-d3 route the lines never played).
                    entry["details"] = won.get("details") or []
                    entry["routes"] = won.get("routes") or []
                    if entry["details"] or entry["routes"]:
                        entry["route_note"] = None
                    maia = won.get("maia") or {}
                    if maia.get("frac") is not None:
                        entry["maia_frac"] = round(maia["frac"], 3)
                else:
                    entry["verified"] = False
                    entry["verdict"] = (v or {}).get("verdict") or "UNCONFIRMED"
        plans.append(entry)
    return plans, advisory


def _material_stability_block(fen: str) -> dict | None:
    try:
        from lucena_core.metrics import material_stability
        return material_stability(fen)
    except Exception:
        _log.warning("material_stability block failed", exc_info=True)
        return None


def _settled_block(fen: str, pvs) -> dict | None:
    try:
        from lucena_core.metrics import settled_view
        return settled_view(fen, pvs)
    except Exception:
        _log.warning("settled_view block failed", exc_info=True)
        return None


def _line_theories_block(fen: str, pvs, rolls) -> dict | None:
    try:
        from lucena_core.metrics import line_theories
        return line_theories(fen, pvs, rolls)
    except Exception:
        _log.warning("line_theories block failed", exc_info=True)
        return None


def _game_phase_block(fen: str) -> dict:
    """{'name': opening|middlegame|endgame, 'why': ..., 'developed': {...}}
    from the core's hybrid classifier; None-safe (the sheet must never die on
    a phase). `developed` is PER SIDE (2026-07-25): the game is a middlegame
    once EITHER side finishes developing, so the phase name alone no longer
    tells you whether the side to move still owes development — this is where
    that survives into the sheet."""
    try:
        from lucena_core.reads import game_phase
        gp = game_phase(fen)
        return {"name": gp["phase"], "why": gp["why"],
                "developed": gp.get("developed")}
    except Exception:
        _log.warning("game_phase block failed", exc_info=True)
        return {"name": None, "why": "phase classifier unavailable"}


def _activity_block(act: dict) -> dict:
    """The sheet's ACTIVITY section from the positional activity term's
    per-piece features (lucena_core.positional._activity_term). One entry
    per minor/major piece; the side score is the same sum the term's cp
    differential is built from."""
    f = act.get("features", {})
    out = {"diff_cp": act["cp"], "standing": act["standing"],
           # the structured verdict the UI badges (never the 0-1 number)
           "leader": f.get("leader")}
    for color in ("white", "black"):
        pieces = [{"piece": e["piece"], "square": e["square"],
                   "score": e["norm"], "cp": e["score"],
                   "mobility": e["mobility"], "placement": e["placement"]}
                  for e in f.get(f"pieces_{color}", [])]
        # side score = mean of its pieces' normalized scores (0-1); the raw
        # cp sum stays available as `cp`
        out[color] = {
            "score": round(sum(p["score"] for p in pieces)
                           / len(pieces), 2) if pieces else None,
            "cp": f.get(f"score_{color}", 0),
            "worst": f.get(f"worst_piece_{color}"),   # the problem piece
            "pieces": pieces,
        }
    return out


def _line_moves(fen: str, pvs, rolls, plies: int = 14) -> set[str] | None:
    """UCIs occurring early in the eval-equal engine lines or the Maia
    rolls — the filter set for line-gated inventories. None when no lines."""
    lines = []
    usable = [p for p in (pvs or []) if p.get("ucis")]
    if usable:
        # anchor the eval-equal band on the FIRST pv carrying a cp (MultiPV
        # is best-first) — an empty-ucis first pv must not disable gating
        # (Codex P1 2026-07-25)
        anchor = next((p.get("cp") for p in (pvs or [])
                       if p.get("cp") is not None), 0)
        lines += [p["ucis"] for p in usable
                  if abs((p.get("cp") or 0) - anchor) <= 60]
    for r in (rolls or []):
        if isinstance(r, list):
            lines.append(r)
    if not lines:
        # None ONLY when no line source existed at all; usable lines that
        # all fall outside the band still GATE — to empty (Codex P1 round 2)
        had_source = bool(usable) or any(isinstance(r, list)
                                         for r in (rolls or []))
        return set() if had_source else None
    return {u for ln in lines for u in ln[:plies]}


def _metrics_block(fen: str, pvs=None, rolls=None) -> dict:
    """Batch-2 deterministic metrics (owner work order 2026-07-23):
    regions (control incl. wings/files/holes), space + exploitability,
    development lag (side-conditioned, annoyance-gated `notable`), pawn
    breaks, passers, color complex, trapped pieces. None-safe per metric —
    the sheet must never die on a read.

    BREAKS are line-gated (owner 2026-07-25: "only the relevant ones after
    the roll must get presented"): with pvs/rolls supplied, a break survives
    only if its push actually occurs in an eval-equal engine line or a Maia
    roll — suggest proposes, the lines filter, same doctrine as the plans.
    Without lines (research CLI) the full inventory stays."""
    from lucena_core import positional as _pos
    from lucena_core import metrics as _met
    out = {}
    for key, fn in (("regions", _pos.region_control),
                    ("space", _met.space_report),
                    # development_lag (GM per-ply baseline) intentionally NOT
                    # surfaced (owner 2026-07-25: "let's not show the GM
                    # baseline, it's useless") — it is opening-window-bound and
                    # says nothing a student can act on. Development shows only
                    # through geometric tells (suggest.py's COMPLETE
                    # DEVELOPMENT) and the initiative dev-lead face.
                    ("breaks", _met.pawn_breaks),
                    ("passers", _met.passer_report),
                    ("color_complex", _met.color_complex),
                    ("trapped", _met.trapped_pieces)):
        try:
            out[key] = fn(fen)
        except Exception:
            _log.warning("metrics block %r failed", key, exc_info=True)
            out[key] = None
    moves = _line_moves(fen, pvs, rolls)
    if moves is not None and out.get("breaks"):
        for side in ("white", "black"):
            rows = out["breaks"].get(side) or []
            out["breaks"][side] = [r for r in rows
                                   if (r["pawn"] + r["push"]) in moves]
    return out


def _king_risk_block(fen: str) -> dict | None:
    """Per-side king risk: the raw danger composite, its bounded form, and
    the CALIBRATED P(catastrophe) in all three regimes (findings 21-25).

    The three regimes are the point — "P(catastrophe)" is not one number,
    it depends on who is ATTACKING as much as who is defending:
    `if_pressed` (engine-strength pressure — the ceiling), `typical_1500`
    (real rating-matched club games), `typical_gm` (real GM-vs-GM, carried
    as INDICATIVE only, n_pos=3). Each entry carries its own confidence
    tier so a consumer can never present the indicative one as settled."""
    try:
        from lucena_core.board import Board as _LB
        from lucena_core.positional import analyze_positional as _ap
        from king_danger_calibration import p_catastrophe_profile
        ks = _ap(_LB(fen))["terms"]["king_safety"]["features"]
    except Exception:
        _log.warning("king_risk block failed", exc_info=True)
        return None
    out = {}
    for side in ("white", "black"):
        f = ks.get(side)
        if not f:
            continue
        d = f.get("danger", 0)
        # WHY (owner 2026-07-25: "King is 'unsafe' — why?"): every danger
        # number ships with its citable board facts, assembled from the
        # term's own components — never re-derived, never a model's words.
        why: list[str] = []
        if f.get("zone_attackers"):
            why.append("attackers: " + ", ".join(f["zone_attackers"][:3]))
        if f.get("open_files_nearby"):
            why.append("open " + "/".join(f["open_files_nearby"])
                       + "-file beside the king")
        if f.get("shield_pawns") == 0:
            why.append("no pawn shield")
        if f.get("storm"):
            why.append("enemy pawn storm approaching")
        if f.get("line_pressure"):
            why.append("heavy pieces on the king's file or rank")
        out[side] = {
            "danger": d,
            "danger_bounded": f.get("danger_bounded"),
            "attack_units": f.get("attack_units"),
            "shield_pawns": f.get("shield_pawns"),
            "zone_attackers": f.get("zone_attackers"),
            "open_files_nearby": f.get("open_files_nearby"),
            "storm": f.get("storm"),
            "line_pressure": f.get("line_pressure"),
            "why": why,
            "p_catastrophe": p_catastrophe_profile(d),
        }
    return out or None


# Above this eval magnitude the position is DECISIVE, not a probing
# middlegame: positional verdicts ("more space kingside") are noise or
# actively misleading next to "a queen up". Matches the backend's
# PLANS_CP_BAND (±1.5 pawns) that gates the equal-position plans read.
_DECISIVE_CP = 150

# --- compensation read (owner 2026-07-24) ---
_COMP_MAT_MIN = 150      # settled (SEE-adjusted) material deficit before we
                         # even look for compensation — more than a pawn.
_COMP_MIN = 100          # the engine eval must offset at least this much
                         # BEYOND material for the down side, or it's just
                         # losing (the winning block already speaks).
_COMP_EVAL_FLOOR = -300  # if the down side is worse than a minor piece even
                         # AFTER the offset, it's losing, not compensated.
_COMP_KING_DANGER = 0.4  # enemy king "exposed" — same bar as _winning_reason.
_COMP_SPACE_MIN = 2      # raw space lead that counts as a bind (metrics.space).


def _is_decisive(assessment: dict) -> bool:
    """|eval| past the band. When we HAVE the engine eval (pvs supplied, which
    the backend always does), trust it OUTRIGHT — it already prices sacrificial
    compensation, so the material count must NOT override it (else a sound sac
    like Bobotsov-Tal 11...Nxd5, eval ~0 but 'White up a queen for two minors',
    wrongly reads as 'White is winning'). The settled-material backstop applies
    ONLY to the static, no-engine fallback, where total_cp is positional-only
    and would miss a clean material win."""
    total = assessment.get("total_cp")
    if assessment.get("eval_source") == "engine":
        return total is not None and abs(total) > _DECISIVE_CP
    adj = ((assessment.get("material_stability") or {}).get("adjusted_cp"))
    return (total is not None and abs(total) > _DECISIVE_CP) or \
           (adj is not None and abs(adj) > _DECISIVE_CP)


def _decisive_badge(assessment: dict) -> str:
    """The single honest verdict for a decisive position: name the winning
    side, and the material edge ONLY when settled material actually explains
    it. If the material leader disagrees with the winning side (a sacrifice —
    winning while nominally down), parroting the material count would mislead
    exactly as finding 26/27's decoy did, so we say only 'X is winning'."""
    total = assessment.get("total_cp") or 0
    ms = assessment.get("material_stability") or {}
    adj = ms.get("adjusted_cp") or 0
    # Prefer the real eval (present when pvs were supplied); fall back to the
    # settled-material leader when only the positional fallback cp exists.
    if abs(total) > _DECISIVE_CP:
        leader = "White" if total > 0 else "Black"
    else:
        leader = ms.get("leader") or ("White" if adj > 0 else "Black")
    if ms.get("leader") == leader and ms.get("standing"):
        return ms["standing"]           # e.g. "White is up a rook"
    return f"{leader} is winning"        # positional / attack / sacrifice


def _winning_leader(a: dict) -> str:
    """Which side is winning — the real eval when pvs are present, else the
    settled-material leader (same precedence as _decisive_badge)."""
    total = a.get("total_cp") or 0
    ms = a.get("material_stability") or {}
    if abs(total) > _DECISIVE_CP:
        return "White" if total > 0 else "Black"
    return ms.get("leader") or ("White" if (ms.get("adjusted_cp") or 0) > 0
                                else "Black")


def _winning_reason(a: dict) -> str:
    """One sentence saying WHY the leader is winning — the only thing worth
    showing once a side is outright winning (owner 2026-07-24: "don't show
    anything, just say why"). Material first (settled), then a fatal king
    attack, else a plain positional verdict. Never parrots a material count
    that disagrees with the winner (the finding 26/27 decoy)."""
    leader = _winning_leader(a)
    loser = "Black" if leader == "White" else "White"
    ms = a.get("material_stability") or {}
    if ms.get("leader") == leader and ms.get("standing"):
        phrase = ms["standing"].split(" is ", 1)[-1]      # "up a rook"
        return f"{leader} is winning — {phrase}."
    kr = a.get("king_risk") or {}
    if ((kr.get(loser.lower()) or {}).get("danger_bounded") or 0) >= 0.4:
        return f"{leader} is winning — {loser}'s king is fatally exposed."
    return f"{leader} is winning."


def _winning_advice(a: dict) -> list[str]:
    """Hardcoded generic advice for the WINNING side (owner 2026-07-24).
    Conversion technique ONLY when actually material up; a king-safety
    reminder ALWAYS rides along ("even king safety") — the one way to throw a
    material lead is to get mated or hand over counterplay. Addressed to the
    leader by name, so it reads right whether White or Black is ahead."""
    leader = _winning_leader(a)
    ms = a.get("material_stability") or {}
    material_up = (ms.get("leader") == leader
                   and "up" in (ms.get("standing") or ""))
    tips: list[str] = []
    if material_up:
        tips.append(f"{leader} should trade pieces, not pawns, and steer "
                    "into an endgame.")
        tips.append("No need to rush: convert with simple, safe moves and "
                    "avoid unnecessary complications.")
    tips.append(f"Keep {leader}'s king safe and shut down counterplay.")
    return tips


def _defender_advice(a: dict) -> list[str]:
    """Hardcoded advice for the LOSING side (owner: 'what about defender's
    tips?'). The mirror of conversion: keep pieces on when down material, make
    it messy, and mind your own king. Addressed to the loser by name."""
    leader = _winning_leader(a)
    loser = "Black" if leader == "White" else "White"
    ms = a.get("material_stability") or {}
    down = (ms.get("leader") == leader and "up" in (ms.get("standing") or ""))
    tips: list[str] = []
    if down:
        tips.append(f"{loser} should keep pieces on and avoid trades.")
    tips.append(f"{loser} must make it messy: seek complications, counterplay "
                "and traps — a practical swindle is the best chance.")
    tips.append(f"{loser} should still guard their own king.")
    return tips


def _join_terms(words: list[str]) -> str:
    words = [w for w in words if w]
    if not words:
        return "a lasting edge"
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def _concrete_from_lines(a: dict, underdog: str) -> tuple[str, str]:
    """Refine the 'concrete' branch by WALKING the engine lines instead of
    stopping at "no static feature explains it" (owner 2026-07-24: "when you
    say 'in the lines', is there a way to calculate and find out?" — yes).

    Reads `line_theories` (already on the sheet: each PV walked to quiescence,
    with the SEE-settled material and durable terms at the endpoint) plus the
    root settled material, and classifies the concrete compensation:
        regained  the deficit CLOSES down a line -> it wins the material back
                  (naming the settling move / capture from the line's own read)
        harvest   a term only decisive at the endpoint survives across lines
                  (finding 2: restructuring is invisible at creation, visible
                  at the harvest) -> it cashes into that term
        pressure  a line claws material back but stays nominally down
        dynamic   none of the above — a standing threat the lines hold, the
                  genuinely-hard ~half that stays 'read the lines'.
    Returns (kind, reason)."""
    lt = a.get("line_theories") or {}
    lines = lt.get("lines") or []
    root_adj = (a.get("material_stability") or {}).get("adjusted_cp")
    sgn = 1 if underdog == "White" else -1        # underdog-favorable sign
    best = None                                   # (recovery, leaf_signed, line)
    if root_adj is not None:
        root_signed = sgn * root_adj
        for ln in lines:
            leaf = (ln.get("material") or {}).get("adjusted_cp")
            if leaf is None:
                continue
            recov = sgn * leaf - root_signed      # +cp = down side gains material
            if best is None or recov > best[0]:
                best = (recov, sgn * leaf, ln)

    def _first_move(ln):
        li = ln.get("line")
        return li[0] if isinstance(li, list) and li else None

    def _resource(ln):
        # the down side's own material-winning move, named from the settled read
        for th in (ln.get("material") or {}).get("threats", []):
            if th.get("side") == underdog and (th.get("see") or 0) > 0:
                return th.get("san")
        return _first_move(ln)

    enemy = "Black" if underdog == "White" else "White"

    def _mechanism(ln):
        # the down side's strongest term at THIS line's endpoint — names WHAT
        # the pressure is (an attack / activity / a pawn or centre bind), even
        # when it isn't durable across every line. Falls back to the initiative.
        te = ln.get("terms") or {}
        best_t, best_v = None, 0
        for t in ("king_safety", "activity", "pawns", "center"):
            v = sgn * te.get(t, 0)
            if v > best_v:
                best_t, best_v = t, v
        if best_t and best_v >= 40:
            return {"king_safety": f"the attack on {enemy}'s king",
                    "activity": "the more active pieces",
                    "pawns": f"the pressure on {enemy}'s pawns",
                    "center": "the central bind"}[best_t]
        return "the initiative"

    def _mat_phrase(recov):
        return ("a rook" if recov >= 450 else "a piece" if recov >= 250
                else "the exchange" if recov >= 150 else "a pawn")

    # User-facing wording states the CHESS fact, never "the engine's lines"
    # (owner 2026-07-24: "I don't wanna bring up engine lines") — how we know
    # is meta; a coach speaks the board.
    terms = lt.get("summary") or []
    if best and best[0] >= 100 and best[1] >= -100:         # deficit fully closes
        mv = _resource(best[2])
        tail = f" with {mv}" if mv else ""
        return "regained", f"the material comes straight back{tail}."
    if terms:
        return "harvest", f"the play brings {_join_terms(terms)}."
    if best and best[0] >= 100:                             # claws back, STILL down
        # name the MECHANISM (what the pressure is) + the material it wins back
        mech = _mechanism(best[2])
        verb = "win back" if mech == "the more active pieces" else "wins back"
        mv = _resource(best[2])
        tail = f" ({mv})" if mv else ""
        return "pressure", (f"{mech} {verb} {_mat_phrase(best[0])}{tail}, though "
                            f"{underdog} stays nominally down.")
    return "dynamic", f"active threats offset the material."


def _initiative_block(fen: str, pvs) -> dict | None:
    """The initiative read for the sheet (src/initiative.py): per-side 0..1
    score + leader + the NAMED evidence. Trimmed to what a client renders."""
    try:
        from initiative import initiative as _init
        iv = _init(fen, pvs)
    except Exception:
        _log.warning("initiative block failed", exc_info=True)
        return None
    out = {"leader": iv["leader"], "diff": iv["diff"],
           "basis": iv.get("basis"), "magnitude": iv.get("magnitude"),
           "constrained": iv.get("constrained"),
           "mover_penalty_cp": iv.get("mover_penalty_cp"),
           "explained": iv.get("explained"),
           "resolves": iv.get("resolves"),
           # the two faces (owner 2026-07-25): mechanism names which carries
           # the verdict (threats/passer/development); deferred flags the slow
           # -positional kind neither face can honestly claim.
           "mechanism": iv.get("mechanism"),
           "development": iv.get("development"),
           "deferred": iv.get("deferred")}
    for s in ("white", "black"):
        e = iv[s]
        out[s] = {"score": e["score"],
                  "prior_score": e.get("prior_score"),
                  "resources": e.get("resources"),
                  "forcing_frac": e.get("forcing_frac"),
                  "forcing_moves": e.get("forcing_moves") or [],
                  "why": e["static"]["why"]}
    return out


# --- is-this-the-only-move (owner 2026-07-24: "isTheOnlyMove can be done very
# cheaply in this package") ---
_ONLY_MOVE_MIN = 150     # eval cliff best->2nd-best (mover's favour) = one move holds
_ONLY_MOVE_RAZOR = 300   # ...and everything else loses outright


def _only_move_block(fen: str, pvs) -> dict | None:
    """Is exactly ONE move holding the position? Measured from the caller's
    MultiPV alone — the eval cliff from the best line to the second best, in
    the side-to-move's favour. No engine roll, no hand-off to a tactics
    package: the drillability signal is already in `pvs`. A big cliff means the
    position is TACTICAL — the compensation is conditional on finding the move,
    so the read must lead with it, not a positional form (measured: ~45% of the
    fired imbalance reads are only-moves the positional label was masking). cp
    is +White throughout; MultiPV is ordered best-first for the mover."""
    if not pvs or len(pvs) < 2:
        return None
    c0, c1 = pvs[0].get("cp"), pvs[1].get("cp")
    u0 = pvs[0].get("ucis") or []
    if c0 is None or c1 is None or not u0:
        return None
    gap = (c0 - c1) if fen.split()[1] == "w" else (c1 - c0)
    if gap < _ONLY_MOVE_MIN:
        return None
    try:
        move = chess.Board(fen).san(chess.Move.from_uci(u0[0]))
    except Exception:
        return None
    return {"move": move, "gap_cp": round(gap), "razor": gap >= _ONLY_MOVE_RAZOR}


def _compensation_read(out: dict) -> dict | None:
    """WHY a materially-DOWN side is still holding — the compensation read
    (owner design 2026-07-24: "if less material -> isDrillable -> if not, what
    compensation do we have? king safety -> activity -> space").

    The split that makes it honest: MAGNITUDE is the ENGINE's to state, FORM is
    ours to name.

      * MAGNITUDE (how much comp) comes from engine_eval vs SEE-settled
        material, NEVER from summing our terms. Finding 18 measured that the
        static family explains only ~15% of eval-minus-material; worse, a naive
        centipawn sum points the WRONG WAY here — raw mobility (`diff_cp`) is
        queen-skewed toward the side that still HAS the queen, and the sacker's
        own exposed king counts against them. So we read the number the engine
        already priced and only classify it (winning/full/partial/slight).

      * FORM (what kind of comp) is a sharpest-to-slowest cascade, first hit is
        primary but all are listed:
            1. ATTACK   — the enemy (material-UP) king is exposed. This reads
                          the OPPONENT'S king danger, not the down side's own
                          (at Harikrishna 10.Kxf2 it is WHITE's king that is
                          exposed, so attack does NOT fire — activity does).
            2. ACTIVITY — the down side's pieces are the more active. Uses the
                          activity term's own material-neutral `leader` verdict
                          (per-side rescaled scores), never `diff_cp`.
            3. SPACE    — the down side holds a space bind.
            else CONCRETE — no static feature explains it; it lives in the
                          engine's lines (finding 18's ~85% residue), said so.

    Fires only on an ENGINE eval — a static-fallback sheet cannot honestly
    assert compensation. Returns None when there is no material deficit past
    _COMP_MAT_MIN or the engine prices no meaningful offset (< _COMP_MIN).

    NOTE (future work): the owner's design opens with an isDrillable branch — a
    forcing/tactical win as the sharpest 'compensation'. A true forcing-tree
    check lives in lucena-tactics (line_tree) and is not wired into this layer;
    `tactical` (dynamism SHARP/RAZOR) is the honest stand-in until it is — it
    flags 'this comp is dynamic, read it in the lines', not a verdict."""
    a = out.get("assessment") or {}
    if a.get("eval_source") != "engine":
        return None
    total = a.get("total_cp")
    ms = a.get("material_stability") or {}
    adj = ms.get("adjusted_cp")
    if total is None or adj is None or abs(adj) < _COMP_MAT_MIN:
        return None
    underdog = "White" if adj < 0 else "Black"
    enemy = "Black" if underdog == "White" else "White"
    deficit = abs(adj)
    eval_ud = total if underdog == "White" else -total   # +cp = good for down side
    comp = eval_ud + deficit                              # offset beyond material
    # Two gates: the engine must price REAL offset (>= _COMP_MIN beyond
    # material), AND the down side must not be losing outright anyway. Down a
    # rook and still worse by -700 nets ~100cp of "comp" arithmetically, but
    # calling that 'compensation' to a lost position is noise — if the down
    # side is worse by more than a minor piece, stay silent and let the
    # winning/normal read speak.
    if comp < _COMP_MIN or eval_ud < _COMP_EVAL_FLOOR:
        return None

    # --- FORM: sharpest-to-slowest cascade ---
    forms: list[str] = []
    reason: str | None = None
    kr = a.get("king_risk") or {}
    if ((kr.get(enemy.lower()) or {}).get("danger_bounded") or 0) >= _COMP_KING_DANGER:
        forms.append("attack")
        reason = (f"{enemy}'s king is exposed — {underdog} has an attack for "
                  "the material.")
    if (out.get("activity") or {}).get("leader") == underdog:
        forms.append("activity")
        if reason is None:
            reason = (f"{underdog}'s pieces are far more active; {enemy}'s are "
                      "passive or undeveloped.")
    sp = (out.get("metrics") or {}).get("space") or {}
    sw = sum((sp.get(r) or {}).get("white", {}).get("raw", 0)
             for r in ("center", "kingside", "queenside"))
    sb = sum((sp.get(r) or {}).get("black", {}).get("raw", 0)
             for r in ("center", "kingside", "queenside"))
    space_lead = (sw - sb) if underdog == "White" else (sb - sw)
    if space_lead >= _COMP_SPACE_MIN:
        forms.append("space")
        if reason is None:
            reason = f"{underdog} holds a space bind for the material."
    concrete_kind = None
    if not forms:
        forms.append("concrete")
        # No ROOT static feature — walk the engine lines to say WHAT the
        # compensation is (regained material / a harvest term / dynamic).
        concrete_kind, reason = _concrete_from_lines(a, underdog)

    # --- RUNG-0: isTheOnlyMove. If one move holds the position, the
    # compensation is CONDITIONAL on finding it — that is the headline, not the
    # positional form (which describes the aftermath and stays in `forms`). ---
    om = a.get("only_move")
    if om:
        forms.insert(0, "only_move")
        lead = ("only one move holds it" if om["razor"]
                else "it hinges on a single move")
        reason = f"{lead} — {om['move']}; anything else loses."

    # --- MAGNITUDE: the engine's word, never a term sum ---
    if eval_ud >= _DECISIVE_CP:
        magnitude = "winning"          # comp more than paid — the sac is winning
    elif eval_ud >= -60:
        magnitude = "full"             # balance holds despite the deficit
    else:
        magnitude = "partial"          # cushions the deficit, doesn't erase it

    down_phrase = ((ms.get("standing") or "").split(" is ", 1)[-1]
                   .replace("up ", "down ", 1)) or "down material"
    mag_word = {"winning": "and is already winning",
                "full": "with full compensation",
                "partial": "with partial compensation"}[magnitude]
    summary = f"{underdog} is {down_phrase} {mag_word} — {reason}"

    # --- EVIDENCE (owner 2026-07-25: "wire these explanations in"): the
    # citable board facts behind the PRIMARY form, pulled from the blocks the
    # sheet already computed — never re-derived, never free text. ---
    evidence: list[str] = []
    primary = forms[0]
    if primary == "only_move" and om:
        evidence.append(f"best-to-second-best gap {om['gap_cp']}cp — "
                        f"{om['move']} is the move")
    elif primary == "attack":
        evidence = list(((kr.get(enemy.lower()) or {}).get("why")) or [])
    elif primary == "activity":
        act = out.get("activity") or {}
        for col, lbl in ((underdog.lower(), "working"),
                         (enemy.lower(), "idle")):
            ps = (act.get(col) or {}).get("pieces") or []
            ps = sorted(ps, key=lambda p: -(p.get("score") or 0))
            pick = ps[:2] if lbl == "working" else ps[-2:]
            for p in pick:
                evidence.append(f"{p['piece']}@{p['square']} "
                                f"activity {p['score']:.2f} ({lbl})")
    elif primary == "space":
        evidence.append(f"space squares White {sw} vs Black {sb}")
    elif primary == "concrete":
        iv = a.get("initiative") or {}
        w = ((iv.get(underdog.lower()) or {}).get("why")) or {}
        if w.get("checks"):
            evidence.append("checks that stand: " + ", ".join(w["checks"][:3]))
        if w.get("captures"):
            evidence.append("sound captures: " + ", ".join(w["captures"][:3]))
        if w.get("loose"):
            evidence.append("loose targets: " + ", ".join(w["loose"][:3]))
        fm = (iv.get(underdog.lower()) or {}).get("forcing_moves") or []
        if fm:
            evidence.append("best play keeps forcing: " + ", ".join(fm[:4]))

    return {
        "side": underdog,
        "magnitude": magnitude,
        "summary": summary,
        "reason": reason,
        "forms": forms,
        "primary": forms[0],
        # for a concrete primary: what the LINES showed —
        # regained/harvest/pressure/dynamic (None when a static form fired)
        "concrete_kind": concrete_kind,
        # citable board facts behind the primary form (owner: "let's verify")
        "evidence": evidence,
        "deficit_cp": round(deficit),   # settled material the side is down
        "comp_cp": round(comp),         # engine eval offset beyond material
        "eval_cp": round(eval_ud),      # engine eval, +cp = good for the down side
        # RUNG-0 only-move: {move, gap_cp, razor} when one move holds, else None
        "only_move": om,
        # dynamism SHARP/RAZOR: the comp is dynamic — verify it in the lines,
        # not a static read. Honest stand-in for the isDrillable branch.
        "tactical": (a.get("character") or {}).get("bucket") in ("SHARP", "RAZOR"),
    }


def _bars_block(out: dict) -> list[dict]:
    """Labeled 0-1 bars (owner 2026-07-24: 'reintroduce bars instead of
    labels'). Each is driven by a COMPARABLE, head-to-head quantity so the
    per-side-normalization trap that made us switch to badges can't recur:

      * Eval / Activity / Space are CENTERED (mid=0.5) off White-minus-Black
        differentials — 0.5 is dead even, fill past the midline is White's
        edge. (Activity uses diff_cp, the raw Stockfish mobility differential,
        NOT the per-side 0-1 norm; Space uses raw counts.)
      * King safety uses its true ABSOLUTE scale (danger_bounded, 0=safe..
        1=lost), one bar per king — the two ARE comparable there.

    NO control bar (owner: dropped as noise). Activity/Space are shown only in
    an equalish position (decisive -> the Eval bar tells the story)."""
    a = out.get("assessment") or {}
    def c01(x): return max(0.0, min(1.0, x))
    bars: list[dict] = []
    total = a.get("total_cp")
    if total is not None:
        bars.append({"label": "Eval", "value": c01(0.5 + total / 1000.0),
                     "mid": 0.5})
    if not _is_decisive(a):
        # Activity bar off the MATERIAL-NEUTRAL per-side scores (mean per-piece
        # 0-1 mobility) — NOT the raw diff_cp sum, which a queen's mobility
        # skews (Bobotsov-Tal move 18 read +31 White on square-count alone).
        # The per-side scores self-correct: near-even there (0.65 vs 0.63), yet
        # they SHOW a sacrifice's positional comp (Harikrishna 10.Kxf2: White
        # 0.62 vs Black 0.30, down a queen but far more active).
        act = out.get("activity") or {}
        aw = (act.get("white") or {}).get("score")
        ab = (act.get("black") or {}).get("score")
        if aw is not None and ab is not None:
            bars.append({"label": "Activity",
                         "value": c01(0.5 + (aw - ab) * 1.5), "mid": 0.5})
        # Space is a DIFFERENTIAL on a scale, like Activity — not a share
        # (owner 2026-07-26: "why is the space maxxed out for black in this
        # position?"). It was w/(w+b), which saturates the moment one side is
        # at zero: after 1.Nf3 e5 the bar read 100% Black, and after 1.e4 it
        # read 100% White, off a single pawn move. `raw` counts squares
        # claimed past the second rank, so the same scale the space BADGE is
        # calibrated on applies here — a raw lead of 2 is a real edge
        # (_SPACE_EDGE_MIN, corpus-checked), so 2 nudges the bar and a
        # thumping 8 fills it.
        sp = (out.get("metrics") or {}).get("space") or {}
        w = sum((sp.get(r) or {}).get("white", {}).get("raw", 0)
                for r in ("center", "kingside", "queenside"))
        b = sum((sp.get(r) or {}).get("black", {}).get("raw", 0)
                for r in ("center", "kingside", "queenside"))
        if w + b > 0:
            bars.append({"label": "Space", "value": c01(0.5 + (w - b) / 16.0),
                         "mid": 0.5})
    bars.extend(_king_bars(a))
    return bars


def _king_bars(a: dict) -> list[dict]:
    """The two king-safety bars — absolute 0=safe..1=exposed (danger_bounded,
    now storm-aware). Shown always, INCLUDING when winning (owner: 'run the
    numbers even when winning' — the diagnostic view)."""
    kr = a.get("king_risk") or {}
    out: list[dict] = []
    for side, lbl in (("white", "White king"), ("black", "Black king")):
        db = (kr.get(side) or {}).get("danger_bounded")
        if db is not None:
            out.append({"label": lbl, "value": max(0.0, min(1.0, db))})
    return out


def _badges_block(out: dict) -> list[str]:
    """The sheet's VERDICTS, as short badge strings (owner 2026-07-24:
    "all the 0-1 values share this problem — show them as badges").

    DECISIVE guardrail (2026-07-24): once |eval| > _DECISIVE_CP the
    positional chips below stop meaning anything a reader can use — a "more
    space kingside" badge next to "a queen up" is noise at best. Above the
    band the only badge is the decisive verdict; the equal-position chips are
    suppressed. (The full conversion/resistance read is separate work.)

    Every 0-1 on this sheet was false precision on screen. A control share
    is complementary by construction, so at balance both sides read ~0.50
    and look identical; a space percentile of 0.57 tells a reader nothing;
    an activity 0.681-vs-0.527 hid that the raw sum ordered the sides the
    other way. Each of these ALREADY had a computed verdict server-side
    (`regions[r].leader`, `space[r].edge`, `color_complex.weak_for`,
    `activity.leader`) — the UI was just drawing the number instead. The
    numbers stay in the JSON as data; this is what gets displayed.

    A badge appears only when there IS a verdict — a near-tie prints
    nothing rather than a meaningless bar."""
    assessment = out.get("assessment") or {}
    if _is_decisive(assessment):
        return [_decisive_badge(assessment)]
    m = out.get("metrics") or {}
    badges: list[str] = []
    # Activity and Space are now BARS, not labels (owner 2026-07-24: "bars
    # instead of labels") — see _bars_block. Region-control stays dropped
    # (raw attacker-count share; a quiet Italian reads kingside 0.62 Black and
    # the Ruy centre 0.85 Black, both false and both above a genuine storm at
    # 0.74 — no threshold separates signal from noise). Only the categorical
    # weak-colour-complex flag remains a label here.
    cc = m.get("color_complex") or {}
    for tone in ("light", "dark"):
        weak = (cc.get(tone) or {}).get("weak_for")
        if weak:
            badges.append(f"{weak}'s {tone} squares are weak")
    return badges


def _sides_block(out: dict) -> dict:
    """TEMPORARY per-side reprojection (owner 2026-07-23): 'two sections,
    White and Black, under which the JSON lives'. Derived entirely from the
    blocks already assembled in `out` — a VIEW, not a new computation, so it
    can be dropped or promoted without touching any producer. Everything
    with a natural owner is filed under its side; whole-board facts
    (assessment, reads, structure, tension) stay at top level."""
    m = out.get("metrics") or {}
    regions = m.get("regions") or {}
    space = m.get("space") or {}
    cc = m.get("color_complex") or {}
    sides = {}
    for side, Side in (("white", "White"), ("black", "Black")):
        enemy = "black" if side == "white" else "white"
        sides[side] = {
            "activity": (out.get("activity") or {}).get(side),
            "weaknesses": (out.get("weaknesses") or {}).get(side, []),
            "plans": (out.get("plans") or {}).get(side, []),
            "advisory": (out.get("advisory") or {}).get(side, []),
            "control": {r: regions[r][side] for r in
                        ("center", "kingside", "queenside") if r in regions},
            # outposts/holes THIS side controls (in the enemy camp)
            "outposts": [h for h in regions.get("holes", [])
                         if h.get("controller") == Side],
            "space": {r: space[r][side] for r in
                      ("center", "kingside", "queenside") if r in space},
            "breaks": (m.get("breaks") or {}).get(side, []),
            "passers": (m.get("passers") or {}).get(side, []),
            # TRAPPED means the ENEMY caught it (owner 2026-07-25: "why is
            # Ra8 being tagged as trapped? ... they can move, right?"). A
            # piece with no safe square only because its OWN army is in the
            # way is UNDEVELOPED — every starting rook, bishop and queen
            # qualifies on move 1 — and that is the development plan's job,
            # not a weakness chip. Surface only pieces the enemy is
            # attacking or whose squares the enemy denies.
            "trapped": [t for t in (m.get("trapped") or {}).get(side, [])
                        if t.get("attacked") or t.get("denied_by") == "enemy"],
            "color_control": {c: cc[c][side] for c in ("light", "dark")
                              if c in cc},
            # files this side's heavies control
            "files": [f for f in regions.get("files", [])
                      if f.get("controller") == Side],
        }
    return sides


def _sheet_json(fen: str, pvs, rolls, *, verify: bool) -> dict:
    b = chess.Board(fen)
    pid = opaque_id(fen)
    d = _positional.analyze_positional(_LBoard(fen))
    terms, leads = d["terms"], d["leads"]
    menus = build_menus(b)
    ecp = pvs[0]["cp"] if pvs else None
    total = ecp if ecp is not None else (
        sum(v["cp"] for v in terms.values()) + _hanging_correction(b))
    from dynamism import dynamism as _dyn
    dy = _dyn(fen, pvs, rolls)
    from tension import analyze as _tension, render as _trender
    out: dict = {
        "schema": SHEET_SCHEMA,
        "phase": "post-verify" if verify else "pre-verify",
        "id": pid,
        # NO raw FEN in the artifact (2026-07-24 fix): the opaque `id` hash is
        # the only position handle. The backend json.dumps this whole dict into
        # the narrating LLM's prompt; embedding the FEN handed a FEN-literate
        # model full board access and defeated the POSITION-<hash> redaction
        # the grounding architecture exists to enforce.
        "assessment": {
            "total_cp": round(total) if total is not None else None,
            # whether total_cp is the real ENGINE eval (pvs supplied, which the
            # backend always does) or the STATIC term-sum fallback. Decisiveness
            # trusts an engine eval outright — it already prices compensation,
            # so a sound sacrifice (Bobotsov-Tal 11...Nxd5!) reads as EQUAL, not
            # "White is up a queen". The material backstop is for the static
            # case only. See _is_decisive.
            "eval_source": "engine" if ecp is not None else "static",
            "verdict": _assessment(total),
            # game phase (2026-07-23): lucena_core.reads.game_phase — the
            # hybrid classifier (endgame = material event, opening =
            # development event). NOT the top-level "phase" key, which is
            # the ARTIFACT stage (pre/post-verify).
            "game_phase": _game_phase_block(fen),
            # material stability (2026-07-23): the tension/structure-aware
            # read — WHY an edge holds or dissolves ("up a pawn now, won't
            # be soon"). Validated: soft edges lose 2/3 of the lead in 12
            # plies (125k GM anchors).
            "material_stability": _material_stability_block(fen),
            # SETTLED read (2026-07-23): walk the engine's top line to a
            # quiet position and re-read it — quiescence. The static terms
            # are blind to tension; the settled position tells the truth
            # ("up a doubled pawn now" -> "up a clean pawn"). Needs pvs.
            "settled": _settled_block(fen, pvs),
            # LINE THEORIES (2026-07-23): the eval's decomposition — walk
            # each engine PV + Maia roll to quiescence, measure the settled
            # terms, keep the reason that survives across every line.
            "line_theories": _line_theories_block(fen, pvs, rolls),
            # KING RISK (2026-07-24, findings 21-25): the danger composite
            # plus its calibrated P(catastrophe) in all three regimes.
            "king_risk": _king_risk_block(fen),
            # ONLY-MOVE (2026-07-24): is one move holding the position? — the
            # eval cliff best->2nd-best in the caller's MultiPV. Drillability
            # signal, no roll. Consumed as the compensation read's rung-0.
            "only_move": _only_move_block(fen, pvs),
            # INITIATIVE (2026-07-25): who is making the threats — validated
            # (AUC 0.74 held-vs-failed on 1,581 real-deficit positions) and
            # evidence-carrying: every unit is a citable board fact (the
            # checks that stand, sound captures, loose pieces, the forcing
            # moves in best play). src/initiative.py.
            "initiative": _initiative_block(fen, pvs),
            "character": {"bucket": dy["bucket"], "score": dy["score"],
                          "summary": dy["summary"],
                          "components": [{"name": n, "pts": p, "why": w}
                                         for n, p, w in dy["components"]]},
        },
        "reads": _position_read(b, terms, leads),
        # ACTIVITY (2026-07-23, user request): the per-piece minor/major
        # activity scores the positional term already computes — score is
        # cp-flavored (PeSTO placement, phase-tapered, + weighted mobility
        # above the piece's baseline), most-active first per side.
        "activity": _activity_block(terms["activity"]),
        # batch-2 metrics (2026-07-23): regions/space/development/breaks/
        # passers/color_complex/trapped — deterministic geometry, data tier
        "metrics": _metrics_block(fen, pvs, rolls),
        "structure": [{"name": n, "owner": name_side(o)} for n, o in classify(b)],
        "weaknesses": {
            "white": _weakness_lines(b, terms, chess.WHITE, pvs, rolls),
            "black": _weakness_lines(b, terms, chess.BLACK, pvs, rolls),
        },
        "tension": _trender(_tension(fen, pvs, rolls)) or [],
        "plans": {},
        "advisory": {},
    }
    for t, key in (("W", "white"), ("B", "black")):
        plans, advisory = _candidates(b, menus, t, fen, pvs, rolls, verify=verify)
        out["plans"][key] = plans
        out["advisory"][key] = advisory
    # TEMPORARY: the per-side White/Black view, projected from the blocks
    # above (owner 2026-07-23). Producers are unchanged; this is additive.
    out["sides"] = _sides_block(out)
    out["badges"] = _badges_block(out)
    out["bars"] = _bars_block(out)
    # OUTRIGHT WINNING (owner): show nothing but WHY + generic advice. When
    # set, the client renders only this — no bars, no side reports, no badges.
    _a = out["assessment"]
    out["winning"] = ({"reason": _winning_reason(_a),
                       "advice": _winning_advice(_a),
                       "defense": _defender_advice(_a),
                       # the king numbers even when winning (owner's diagnostic
                       # view — and the storm term makes them worth watching)
                       "king_bars": _king_bars(_a)}
                      if _is_decisive(_a) else None)
    # COMPENSATION (owner 2026-07-24): WHY a materially-down side is holding —
    # engine states the magnitude, the cascade (attack -> activity -> space ->
    # concrete) names the form. Coexists with `winning` (a winning sacrifice
    # gets both: the verdict AND why it worked) and appears on the equalish
    # sheet too (down material, eval level = full comp, no winning block).
    out["compensation"] = _compensation_read(out)
    # whole-sheet FEN redaction, last (2026-07-24): scrub any board string
    # embedded by a nested block (quiescence walks etc.) to its opaque id.
    return _redact_fens(out)


def pre_verify_json(fen: str, pvs: list | None, rolls: list | None) -> dict:
    """The full sheet with every PLAN candidate left unverified — the
    progressive first artifact. NOTE: not verify-free — the WEAKNESSES
    section still runs verify_plan for entombed bishops (extraction/trade
    tracking) regardless of this flag; it is only the PLAN candidates that
    skip verification here."""
    return _sheet_json(fen, pvs, rolls, verify=False)


def post_verify_json(fen: str, pvs: list | None, rolls: list | None) -> dict:
    """The same shape with verdict/timing/maia filled; unconfirmed
    candidates are MARKED (verified=false), never deleted."""
    return _sheet_json(fen, pvs, rolls, verify=True)
