"""personal_sharpness — sharpness conditioned on WHO is playing.

Objective dynamism asks: if the next move is a mistake, how much does it
cost? This module asks the level-conditioned question: how much does the
position punish the move a player of rating L would ACTUALLY play?

    danger_L    = sum_m P_L(m) * loss(m)      expected cp loss at level L
    trap_mass_L = sum_m P_L(m) * 1[loss(m) >= TRAP_CP]
    trap_move   = the highest-probability losing move (the speakable one)

P_L comes from the Maia policy head (rating-conditioned); loss(m) from
engine child evals. As L rises the policy concentrates on engine-equal
moves and danger_L -> 0 except where the position is genuinely hard —
sharp-for-you IS the per-position gap between your policy and the engine.

Contract (the house rule): this module NEVER calls an engine or Maia. The
caller supplies the policy rows and the child evals; we only weigh them.
Buckets here are PROVISIONAL (prior thresholds, blunder bar at 100cp) —
the calibration leg (predicted trap_mass vs observed cohort blunder rate
in rating-banded human games) must run before any bucket is SPOKEN.

Note: no mirror-invariance is claimed or tested for this metric — Maia is
deliberately color-asymmetric (humans play White and Black differently).
"""
from __future__ import annotations

import chess

TRAP_CP = 100          # a trap move loses at least a clean pawn
LOSS_CLIP = 300        # beyond this, "how lost" stops mattering
SAFE_CP = 50           # a move within this of best is fine
MIN_COVER = 0.60       # min policy mass we must have child labels for


def personal_sharpness(fen: str, pvs: list | None, policy_rows: list,
                       child_cp: dict) -> dict | None:
    """Level-conditioned sharpness for ONE level's policy.

    policy_rows: [{"uci": str, "policy": float}, ...] from Maia at the
        level in question (top-n; renormalized here over labeled moves).
    child_cp: {uci: White-POV cp AFTER the move} engine labels; must also
        contain the root under key "" (or pass pvs and we use pvs[0].cp).
    Returns {danger, trap_mass, safe_mass, coverage, trap_move, rows}
    or None if coverage of the policy mass is too thin to say anything.
    """
    b = chess.Board(fen)
    stm = 1 if b.turn == chess.WHITE else -1
    # the reference point, mover POV: the best labeled child. Loss is
    # measured against the best move IN THE LABELED SET — if the engine's
    # true best move is outside Maia's top-n at every level, losses are
    # relative to the best human-visible move, which is the right frame
    # for a level-conditioned metric anyway. `pvs` is accepted for parity
    # with the (fen, pvs, rolls) contract but not required.
    best = max((stm * cp for u, cp in child_cp.items() if u), default=None)
    if best is None:
        return None

    rows, mass = [], 0.0
    for r in policy_rows:
        u, p = r["uci"], float(r.get("policy") or 0.0)
        if u not in child_cp or p <= 0:
            continue
        loss = max(0, min(best - stm * child_cp[u], LOSS_CLIP))
        rows.append({"uci": u, "policy": p, "loss": loss})
        mass += p
    total_mass = sum(float(r.get("policy") or 0.0) for r in policy_rows)
    coverage = mass / total_mass if total_mass > 0 else 0.0
    if not rows or coverage < MIN_COVER or mass <= 0:
        return None

    danger = sum(r["policy"] * r["loss"] for r in rows) / mass
    trap_mass = sum(r["policy"] for r in rows if r["loss"] >= TRAP_CP) / mass
    safe_mass = sum(r["policy"] for r in rows if r["loss"] <= SAFE_CP) / mass
    trap = max((r for r in rows if r["loss"] >= TRAP_CP),
               key=lambda r: r["policy"], default=None)

    if trap_mass >= 0.25:
        bucket = "TRAP"
    elif trap_mass >= 0.10 or danger >= 40:
        bucket = "SLIPPERY"
    else:
        bucket = "SAFE"
    out = {"danger": round(danger, 1), "trap_mass": round(trap_mass, 3),
           "safe_mass": round(safe_mass, 3),
           "coverage": round(coverage, 3), "bucket": bucket,
           "rows": sorted(rows, key=lambda r: -r["policy"])}
    if trap is not None:
        out["trap_move"] = {
            "uci": trap["uci"], "san": b.san(chess.Move.from_uci(trap["uci"])),
            "policy": round(trap["policy"] / mass, 3),
            "loss": trap["loss"]}
    return out


def sharpness_profile(fen: str, pvs: list | None,
                      policy_by_level: dict, child_cp: dict) -> dict:
    """personal_sharpness at each supplied level + the profile read:
    which levels the position is dangerous FOR. policy_by_level:
    {elo: policy_rows}."""
    levels = {}
    for elo, rows in sorted(policy_by_level.items()):
        r = personal_sharpness(fen, pvs, rows, child_cp)
        if r is not None:
            levels[elo] = r
    prof = {"levels": levels}
    if levels:
        dangerous = [e for e, r in levels.items()
                     if r["bucket"] in ("TRAP", "SLIPPERY")]
        prof["dangerous_for"] = dangerous
        elos = sorted(levels)
        prof["monotone_easing"] = all(
            levels[a]["danger"] >= levels[b]["danger"] - 5
            for a, b in zip(elos, elos[1:]))
    return prof
