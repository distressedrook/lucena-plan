"""INITIATIVE — a deterministic score for "who is making the threats"
(owner 2026-07-25: "can we build a deterministic system to calculate
initiative? Given a position, give an initiative score? Go figure.").

Initiative is NOT left as intuition here; it is defined operationally:
    the side with the initiative has forcing resources (checks, sound
    captures, threats on loose pieces) that force the opponent to respond,
    and — the future-tense half — its best play KEEPS forcing (the holding
    lines are checks/captures, measured 81% vs 17% on the imbalance
    benchmark's forced-compensation family).

Two components, reported separately because they have different epistemic
weight (finding 18: static features explain ~15% of the dynamic residue —
a static initiative count is salience, the LINES are the truth):

  STATIC  (geometry only, no engine)  — per side, tempo-weighted:
      safe_checks      checking moves that don't hang the checker (SEE >= 0)
      good_captures    captures with SEE >= 0 (material-sound forcing moves)
      loose_threats    attacked enemy pieces that are loose (geometry.loose_map)
      restriction      enemy non-pawn pieces currently attacked (must-respond load)

  LINE    ((fen, pvs) contract — caller-supplied lines, never rolls):
      forcing_frac     fraction of the side's own moves in the eval-equal PVs
                       that are checks/captures — "does best play keep forcing"
      only_move_gap    the eval cliff best->2nd (how conditional the position is)

The combined per-side score is bounded 0..1. Component weights are PRIOR-tier
(not corpus-fitted); the VALIDATED claim is discriminative: on 1,275 real GM
material-deficit positions, the underdog's initiative differential separates
compensation-held from compensation-failed (see
research/experiments/studies/imbalance_benchmark/validate_initiative.py).
"""
from __future__ import annotations

import math

import chess

from lucena_core.geometry import loose_map, passers as _passers
from lucena_core.see import _see_move

_PVAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
         chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 99}
W_PASSER7 = 2.6      # a safe passer one square from queening
W_PASSER6 = 1.0      # ...two squares from queening
LEASH = 0.9          # how much an enemy's live passer constrains YOU


def _promotion(bb: chess.Board, side: bool) -> dict:
    """Promotion threat = the third classic forcing element (check, capture,
    THREAT) that our resources missed. A passed pawn near queening is
    initiative for its owner — but ONLY if it is SAFE (owner 2026-07-25: "it's
    not initiative if it is getting captured the next move"): if the enemy wins
    it clean (SEE >= 0), it confers nothing. `leash` is the constraint it puts
    on the ENEMY (whose pieces must babysit the queening square)."""
    units = 0.0
    leash = 0.0
    why: list[str] = []
    for p in _passers(bb, side):
        rel = (chess.square_rank(p) if side == chess.WHITE
               else 7 - chess.square_rank(p))
        if rel < 5:                      # only 6th/7th-rank passers threaten now
            continue
        att = bb.attackers(not side, p)
        if att:                          # SAFETY GATE — can the enemy win it?
            lv = min(att, key=lambda s: _PVAL[bb.piece_at(s).piece_type])
            try:
                winnable = _see_move(bb, lv, p) >= 0
            except Exception:
                winnable = len(att) > len(bb.attackers(side, p))
            if winnable:
                continue                 # the passer falls — no initiative
        w = W_PASSER7 if rel == 6 else W_PASSER6
        units += w
        leash += LEASH * (1.0 if rel == 6 else 0.4)
        why.append(f"{chess.square_name(p)} passer "
                   f"({'one' if rel == 6 else 'two'} from queening, safe)")
    return {"units": round(units, 2), "leash": round(leash, 2), "why": why}

# static component weights (prior-tier; units ~ "forcing resources")
W_CHECK = 1.2
W_CAPTURE = 1.0
W_LOOSE = 0.8
W_RESTRICT = 0.3
TEMPO = 1.0          # side to move executes its threats first...
OFF_TEMPO = 0.6      # ...the other side's threats may never land
# bounded mapping: units -> 0..1 (soft saturation around ~6 units)
_SCALE = 4.0

FORCING_PLIES = 10   # how deep into each PV the forcing-fraction looks
EQUAL_BAND = 60      # PVs within this cp of the best are "eval-equal" lines
_FORCED_CLIFF = 150   # drop to the mover's first losing move = it is forced
_SAC_CP = 140         # constrained mover behind by THIS much = attacker (owns it);
                      # otherwise (even imbalance / ahead) it is defending. Sits
                      # BELOW the deficit-validation floor (|naive|>=150, all
                      # sacrifices) and ABOVE a near-even imbalance (~100), so it
                      # preserves the validated deficit behaviour and still calls
                      # the 2R-vs-Q defender correctly.
_LEAD_MAG = 0.20      # below this magnitude: genuinely balanced (no leader)
_CLEAR_MAG = 0.50     # at/above AND geometry-explained: name a side; else "unclear"
_STRONG_GEO = 2.0     # holder resources this high => name it even at moderate mag


def _static_units(b: chess.Board, side: bool) -> dict:
    """Forcing resources for `side` AS IF it were side's turn (null-move view
    when it is not — a threat you could execute next move is still a threat)."""
    bb = b.copy(stack=False)
    if bb.turn != side:
        # null-move view; illegal while in check -> no resources (you're the
        # one responding, the very definition of not having the initiative)
        if bb.is_check():
            return {"safe_checks": 0, "good_captures": 0,
                    "loose_threats": 0, "restriction": 0, "units": 0.0}
        bb.turn = side
        bb.ep_square = None
    lm = loose_map(bb)
    checks: list[str] = []
    caps: list[str] = []
    for m in bb.legal_moves:
        try:
            sound = _see_move(bb, m.from_square, m.to_square) >= 0
        except Exception:
            sound = False
        if bb.gives_check(m) and sound:
            checks.append(bb.san(m))
        elif bb.is_capture(m) and sound:
            caps.append(bb.san(m))
    loose: list[str] = []
    restrict: list[str] = []
    for sq in chess.SQUARES:
        p = bb.piece_at(sq)
        if p is None or p.color == side:
            continue
        if bb.is_attacked_by(side, sq):
            name = f"{chess.piece_name(p.piece_type).capitalize()} on {chess.square_name(sq)}"
            if p.piece_type != chess.PAWN:
                restrict.append(name)
            if lm.get(sq, 0.0) > 0:
                loose.append(name)
    units = (W_CHECK * len(checks) + W_CAPTURE * len(caps)
             + W_LOOSE * len(loose) + W_RESTRICT * len(restrict))
    # counts drive the score; the NAMED evidence is the "why" (owner
    # 2026-07-25: "White has initiative, why?" — every unit is a citable
    # board fact: a check that stands, a sound capture, a loose piece)
    return {"safe_checks": len(checks), "good_captures": len(caps),
            "loose_threats": len(loose), "restriction": len(restrict),
            "units": round(units, 2),
            "why": {"checks": sorted(checks), "captures": sorted(caps),
                    "loose": sorted(loose), "attacked": sorted(restrict)}}


def _forcing_frac(fen: str, pvs, side: bool) -> tuple[float | None, int]:
    """Of `side`'s own moves across the eval-equal PVs (first FORCING_PLIES
    plies each), the fraction that are checks or captures."""
    if not pvs or not pvs[0].get("ucis"):
        return None, 0, []
    best = pvs[0].get("cp") or 0
    forcing = total = 0
    named: list[str] = []
    for pv in pvs:
        if abs((pv.get("cp") or 0) - best) > EQUAL_BAND:
            continue
        b = chess.Board(fen)
        for u in (pv.get("ucis") or [])[:FORCING_PLIES]:
            try:
                m = chess.Move.from_uci(u)
                if b.turn == side:
                    total += 1
                    if b.gives_check(m) or b.is_capture(m):
                        forcing += 1
                        s = b.san(m)
                        if s not in named:
                            named.append(s)
                b.push(m)
            except Exception:
                break
    return (forcing / total if total else None), total, named


def _only_move_gap(fen: str, pvs) -> int | None:
    if not pvs or len(pvs) < 2:
        return None
    c0, c1 = pvs[0].get("cp"), pvs[1].get("cp")
    if c0 is None or c1 is None:
        return None
    return (c0 - c1) if fen.split()[1] == "w" else (c1 - c0)


def _bound(units: float) -> float:
    return round(math.tanh(units / _SCALE), 3)


def initiative(fen: str, pvs: list | None = None) -> dict:
    """The initiative read (rebuilt 2026-07-25 on the owner's MultiPV-spread
    insight). The VERDICT — who has the initiative and how much — comes from
    the ENGINE: the side-to-move's MultiPV spread measures how much it is on a
    tightrope, and the sign of material says which way that cuts (a constrained
    mover BEHIND on material is the attacker who owns the initiative, 93% case;
    a constrained mover AHEAD is a fortress defender tied down, so the NON-mover
    owns it — P121 vs P087). Validated: AUC 0.766 held-vs-failed, beating the
    old geometry score (0.674) with no hand rules. The GEOMETRY (checks,
    captures, loose pieces, the passer term, king pressure) is kept — but as
    the WHY the engine's holder is dictating, never as the score. Without pvs
    we fall back to the geometry prior (engine-free, weaker, honest about it)."""
    b = chess.Board(fen)
    promo = {chess.WHITE: _promotion(b, chess.WHITE),
             chess.BLACK: _promotion(b, chess.BLACK)}
    out: dict = {}
    for side, name in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        st = _static_units(b, side)
        pr, enemy_pr = promo[side], promo[not side]
        st["promotion"] = pr["units"]
        st["leashed"] = enemy_pr["leash"]
        if pr["why"]:
            st["why"]["promotion"] = pr["why"]
        units = max(0.0, st["units"] + pr["units"] - enemy_pr["leash"])
        st["units"] = round(units, 2)
        entry = {"static": st, "why": st["why"], "resources": units,
                 "prior_score": _bound(units)}
        if pvs:
            frac, _n, named = _forcing_frac(fen, pvs, side)
            entry["forcing_frac"] = None if frac is None else round(frac, 2)
            entry["forcing_moves"] = named
        out[name] = entry

    gap = _only_move_gap(fen, pvs) if pvs else None
    out["only_move_gap"] = gap
    out["forced"] = _mover_forced(fen, pvs) if pvs else None

    mp = _mover_penalty(fen, pvs) if pvs else None
    if mp is not None:
        out["basis"] = "engine-spread"
        out["mover_penalty_cp"] = round(mp)
        mover = "white" if b.turn else "black"
        out["constrained"] = mover.capitalize()
        mat = _naive_material(b)                       # +White cp
        mover_mat = mat if b.turn else -mat
        # Direction: the constrained mover OWNS the initiative only when it is
        # a real material SACRIFICE (clearly behind) — the attacker threading
        # the win. If material is roughly even (an imbalance like 2R+2B vs
        # Q+N+B) or the mover is ahead, a heavily-constrained mover is
        # DEFENDING, so the NON-mover dictates (owner's 2R-vs-Q example).
        holder = (mover if mover_mat < -_SAC_CP
                  else ("black" if mover == "white" else "white"))
        mag = _bound_pen(mp)                           # 0..1
        out["magnitude"] = round(mag, 3)
        for name in ("white", "black"):
            out[name]["score"] = round(0.5 + (mag / 2 if name == holder
                                              else -mag / 2), 3)
        out["diff"] = round(out["white"]["score"] - out["black"]["score"], 3)
        out["holder"] = holder.capitalize()            # raw engine attribution
        # honesty flag: does our geometry explain the engine's holder?
        out["explained"] = out[holder]["resources"] > 0.3
        # VERDICT (owner 2026-07-25: "we just say unclear" — how a human reads
        # an engine line they don't understand). We name a side ONLY when the
        # signal is STRONG and our geometry can say WHY; a weak signal, or a
        # strong one we can't explain (a tactic we don't name yet), is honestly
        # "unclear" — never a confident story we can't back.
        out["resolves"] = None
        # name a side when the engine signal is strong, OR moderate but the
        # holder has STRONG clean geometry (an attacker with several good moves
        # has a moderate mover-penalty yet clear initiative — P119: White down a
        # queen but 4 sound captures + dominant knights + a dead enemy bishop).
        # Geometry only CONFIRMS the engine's holder here, never picks it, so
        # this cannot resurrect the P087 defensive-check error.
        strong_geo = out[holder]["resources"] >= _STRONG_GEO
        if mag < _LEAD_MAG:
            out["leader"] = None                       # genuinely balanced
        elif (mag >= _CLEAR_MAG or strong_geo) and out["explained"]:
            out["leader"] = holder.capitalize()        # strong or clearly-backed
        else:
            # would be "unclear" — but if the top line EQUALIZES the material
            # within a few plies, it is NOT unclear: we know the imbalance just
            # evens out (owner 2026-07-25). That is understood, not mysterious.
            eq = _material_equalizes(fen, pvs)
            if eq:
                out["leader"] = None
                out["resolves"] = eq                   # "material even by ply N"
            else:
                out["leader"] = "unclear"
    else:
        # engine-free fallback — the geometry prior (weaker, labelled honestly)
        out["basis"] = "geometry-prior"
        for name, side in (("white", chess.WHITE), ("black", chess.BLACK)):
            tempo = TEMPO if b.turn == side else OFF_TEMPO
            out[name]["score"] = _bound(out[name]["resources"] * tempo)
        out["diff"] = round(out["white"]["score"] - out["black"]["score"], 3)
        out["leader"] = ("White" if out["diff"] >= 0.15 else
                         "Black" if out["diff"] <= -0.15 else None)
    _fuse_development(fen, b, out)
    return out


def _fuse_development(fen: str, b: chess.Board, out: dict) -> None:
    """THE SECOND FACE (owner 2026-07-25, canonical-positions test): initiative
    is tactical forcing-pressure ⊕ a DEVELOPMENTAL/activity lead. The engine
    spread caught the sharp face (P121, the 2R-vs-Q invasion) but called every
    textbook gambit 'balanced' (Danish/Evans/Marshall: the defender has many
    playable moves — no tightrope YET); the material-neutral activity leader
    caught exactly those three and stayed silent on the controls. Fusion rules:

      * The SCORE stays the validated engine-spread number untouched (AUC
        0.744) — activity fuses at the VERDICT/mechanism level only.
      * Tactical verdict outranks: a named engine-spread leader keeps the
        crown; activity can only CONFIRM it (mechanism gains 'development').
      * When the tactical face is quiet (balanced/unclear, no resolves), the
        activity leader takes the verdict with mechanism 'development' — the
        gambit case. Magnitude stays the engine's (honestly small).
      * Both faces quiet + material still imbalanced -> deferred:
        'slow-positional' (the Benko/minority-attack kind — a per-family
        plans-layer job, finding 9's slow horizons — NOT stretched to fit).

    `mechanism` names which face(s) carry the verdict: attack/threats/passer
    from the geometry why, 'development' from the activity face."""
    try:
        from lucena_core.positional import analyze_positional
        from lucena_core.board import Board as _LB
        f = analyze_positional(_LB(fen))["terms"]["activity"]["features"]
    except Exception:
        out["development"] = None
        return
    aw, ab = f.get("activity_white", 0.0), f.get("activity_black", 0.0)
    dev_leader = f.get("leader")                  # gap-gated, material-neutral
    out["development"] = {"white": aw, "black": ab, "leader": dev_leader}

    # name the mechanism(s) behind whichever side ends up with the verdict
    def _mechs(side: str) -> list[str]:
        why = out[side]["why"]
        m = []
        if why.get("checks") or why.get("captures") or why.get("attacked"):
            m.append("threats")
        if why.get("promotion"):
            m.append("passer")
        if dev_leader and dev_leader.lower() == side:
            m.append("development")
        return m

    tactical_named = out["leader"] in ("White", "Black")
    if tactical_named:
        out["mechanism"] = _mechs(out["leader"].lower()) or ["forcing"]
        out["deferred"] = None
        return
    # PHASE GATE (falsified-then-fixed 2026-07-25): the developmental face may
    # take the verdict ONLY in the OPENING. 5,300 Maia-2600 self-play games
    # over the 53 middlegame dev-flips scored the flipped verdict 0.475 — and
    # 0.430 when it crowned the material-up side — the bare activity lead does
    # NOT convert in middlegames (the original P008 lesson). Gambit initiative
    # is a development-TEMPO differential while the opponent is unbuilt
    # (Danish/Evans/Marshall, all opening positions); in a settled middlegame
    # an activity edge is placement, not initiative.
    in_opening = False
    try:
        from lucena_core.reads import game_phase
        in_opening = game_phase(fen)["phase"] == "opening"
    except Exception:
        pass
    if dev_leader and in_opening and not out.get("resolves"):
        # gambit case: tactical face quiet, developmental lead speaks —
        # and cites the OPPONENT's concrete development debt (which pieces
        # are still home, castling), never just the bare activity number.
        out["leader"] = dev_leader
        out["mechanism"] = ["development"]
        out["basis"] = out.get("basis", "") + "+development"
        out["deferred"] = None
        lagger = chess.BLACK if dev_leader == "White" else chess.WHITE
        # ONE definition of a development debt for the whole stack
        # (lucena_core.reads.development_debts) — the same geometry the phase
        # classifier and the COMPLETE DEVELOPMENT plan read, so the tells
        # can't drift from the gate that let them speak.
        from lucena_core.reads import development_debts as _dd
        dd = _dd(b, lagger)
        tells = [f"{m} still home" for m in dd["minors"]]
        if dd["uncastled"]:
            tells.append("king uncastled")
        out[dev_leader.lower()]["why"]["development"] = tells
        return
    out["mechanism"] = []
    # both faces quiet: an imbalance still on the board may be SLOW initiative
    # (Benko-like) — defer to the plans layer rather than stretch a face. The
    # gate is a full pawn: a pawn sac is the smallest real gambit investment.
    out["deferred"] = ("slow-positional"
                       if (not out.get("resolves")
                           and abs(_naive_material(b)) >= 100) else None)


def _mover_penalty(fen: str, pvs) -> float | None:
    """Mean drop from the side-to-move's best move to its MultiPV alternatives
    (mover-favourable cp) — how much it is punished for imperfection, i.e. how
    much it is on a tightrope. Mates clamped so one #-line can't dominate."""
    if not pvs or len(pvs) < 2:
        return None
    white = fen.split()[1] == "w"
    cps = [max(-2000, min(2000, (p["cp"] if white else -p["cp"])))
           for p in pvs if p.get("cp") is not None]
    if len(cps) < 2:
        return None
    return sum(cps[0] - c for c in cps[1:]) / (len(cps) - 1)


def _naive_material(b: chess.Board) -> int:
    """White - Black material in cp (naive; the sign is all we need)."""
    return sum(_PVAL.get(p.piece_type, 0) * 100 * (1 if p.color else -1)
               for p in b.piece_map().values())


def _bound_pen(mp: float) -> float:
    return math.tanh(mp / 300.0)


def _material_equalizes(fen: str, pvs, plies: int = 6) -> str | None:
    """Walk the top engine line: if a material imbalance (>=150cp naive at the
    root) shrinks to near-even (<=120cp) within `plies`, return a note saying
    by which ply — the imbalance is understood to resolve, so the position is
    NOT 'unclear'. Returns None if there is no imbalance or it does not close."""
    if not pvs or not pvs[0].get("ucis"):
        return None
    b = chess.Board(fen)
    if abs(_naive_material(b)) < 150:
        return None
    for i, u in enumerate(pvs[0]["ucis"][:plies], 1):
        try:
            b.push(chess.Move.from_uci(u))
        except Exception:
            break
        if abs(_naive_material(b)) <= 120:
            return f"material even by ply {i} of the main line"
    return None


def _mover_forced(fen: str, pvs) -> dict | None:
    """How constrained is the SIDE TO MOVE — the cliff to its first LOSING
    move, wherever it sits (P121 is forced to two moves, so the cliff is at
    the 3rd, not the 2nd). Returns {holds: k, cliff_cp} when the mover has
    <= 2 holding moves before a >= _FORCED_CLIFF drop, else None. A forced
    mover is spending its move responding — evidence the OPPONENT dictates."""
    if not pvs or len(pvs) < 2:
        return None
    white = fen.split()[1] == "w"
    cps = [(p.get("cp") if white else -p.get("cp")) for p in pvs
           if p.get("cp") is not None]          # mover-favourable
    if len(cps) < 2:
        return None
    best = cps[0]
    for i in range(1, len(cps)):
        if best - cps[i] >= _FORCED_CLIFF:       # first losing move
            return {"holds": i, "cliff_cp": round(best - cps[i])} if i <= 2 else None
    return None


