"""hierarchy — the pedagogical composition layer: mechanisms -> plans ->
campaigns, with every edge either corpus-audited (lift) or corpus-evidenced
(composition colift vs the random floor; experiments/composition_evidence.py).

Three levels, each with its own epistemic contract:
  MECHANISM  a detectable event/state with NO population reliability claim.
             Taught as vocabulary; appears in traces as annotation only.
             (rook_lift: "the rook arrived via f1-f4" — a route, not a plan.)
  PLAN       an event-anchored family that PASSED the random audit (lift,
             CI clear). Carries its reliability line and witnesses. The unit
             of suggestion.
  CAMPAIGN   a composition of plans + mechanisms of one side, linked by span
             proximity. Carries the composition evidence. The unit of
             teaching a whole game phase.

Role tags inside a campaign:
  core     defines the campaign (>= 1 core member must fire)
  stage    an earlier phase of a core member (storm_launch -> pawn_storm)
  setup    prepares a core member (deny_castling before the center break)
  support  co-occurring amplifier (heavy_battery on the file)
  finish   the conversion step (weakness_harvest after the minority lever)

compose(parsed) groups parse_line output into campaign instances.
curriculum() emits the teaching order: mechanisms first (vocabulary), then
plans ranked by lift, then campaigns (compositions of mastered plans).
"""
from __future__ import annotations

MECHANISMS = {
    "rook_lift":        "route: rook rises to rank 3/4 and swings along it",
    "pair_acquisition": "state: winning the two bishops (a multiplier, not a plan)",
    "storm_launch":     "stage: >= 2 ranks of wing-pawn progress at the king",
    "wing_expansion":   "state: space-gaining crab on a kingless wing",
    "fix_then_attack":  "setup: freeze the weak pawn by controlling its advance",
    "majority_roll":    "state: mobilizing a wing majority",
    "open_king":        "state: lanes opened around the enemy king",
    "deny_castling":    "event: rights stripped under compulsion",
    "seventh_invasion": "event: rook lands on the 7th and holds",
    "entomb":           "state: their bishop buried behind fixed pawns",
    "minority_attack_general": "campaign-fragment: 2v3 queenside advance",
}

# family -> (lift_fast, lift_slow) from the current calibration
PLAN_LIFT = {
    "trade_into_endgame": (339.5, 33.5), "simplification": (8.92, None),
    "remove_defender": (7.11, 5.36), "chain_base_attack": (4.30, 2.88),
    "prepared_break": (3.39, None), "center_break_vs_king": (3.15, 2.07),
    "alternation": (3.00, 4.52), "weakness_harvest": (2.74, None),
    "rook_activation": (2.58, None), "outpost_occupation": (2.52, 2.32),
    "king_march": (1.63, 2.27), "heavy_battery": (1.93, 2.35),
    "pawn_storm": (2.04, None), "blockade": (2.02, 1.98),
    "passer_push": (1.75, None), "passer_creation": (1.64, None),
    "seal_to_entomb": (1.22, None), "bad_bishop_escape": (1.23, 1.22),
    "minority_attack": (1.20, 1.22),
}

# campaign -> {family: role}. Composition edges marked (r) carry corpus
# colift-vs-random evidence >= 1.3 (composition_evidence.py); unmarked edges
# are literature-derived and awaiting evidence.
CAMPAIGNS = {
    "KING HUNT (uncastled king)": {
        "deny_castling": "setup",          # x14.9 colift, 2.3r
        "center_break_vs_king": "core",
        "open_king": "support",
        "remove_defender": "support",
    },
    "KING ATTACK (castled king)": {
        "storm_launch": "stage",           # x28.4 colift, 1.5r
        "pawn_storm": "core",
        "piece_attack": "core",            # the piece-route into the same camp
        "heavy_battery": "support",
        "open_king": "support",
        "remove_defender": "setup",
        "rook_lift": "support",            # mechanism annotation only
    },
    "STRANGULATION": {
        "seal_to_entomb": "core",          # entomb x1.7-2.1r cluster
        "entomb": "stage",
        "chain_base_attack": "core",       # entomb x2.0, 1.9r
        "blockade": "support",
        "outpost_occupation": "support",
    },
    "MINORITY CAMPAIGN": {
        "minority_attack": "core",
        "minority_attack_general": "stage",
        "heavy_battery": "support",
        "weakness_harvest": "finish",
        "fix_then_attack": "setup",
    },
    "CONVERSION (two weaknesses)": {
        "weakness_harvest": "core",
        "alternation": "core",
        "seventh_invasion": "support",     # king_march x2.4 1.5r, push x1.9 1.9r
        "fix_then_attack": "setup",
        "king_march": "support",
        "trade_into_endgame": "finish",
    },
    "PROMOTION": {
        "passer_creation": "core",
        "majority_roll": "stage",
        "passer_push": "core",
        "seventh_invasion": "support",
        "king_march": "support",
    },
    "LIBERATION (defense)": {
        "bad_bishop_escape": "core",
        "simplification": "core",
        "prepared_break": "support",
        "blockade": "support",
        "minority_block": "core",
    },
}

SPAN_GAP = 30       # plies: members further apart than this are separate
                    # campaign instances


def compose(parsed: list[dict]) -> list[dict]:
    """Group parse_line output into campaign instances per side.

    A campaign instance = same-side members of one campaign whose plies
    chain with gaps <= SPAN_GAP and which include >= 1 'core' member.
    Members may belong to several campaigns; each campaign groups its own.
    """
    out = []
    for camp, members in CAMPAIGNS.items():
        for side in ("W", "B"):
            hits = sorted((p for p in parsed
                           if p["side"] == side and p["name"] in members),
                          key=lambda p: p["ply"])
            cluster: list[dict] = []
            for p in hits + [None]:
                if p is not None and (not cluster
                                      or p["ply"] - cluster[-1]["ply"] <= SPAN_GAP):
                    cluster.append(p)
                    continue
                if cluster and any(members[q["name"]] == "core"
                                   for q in cluster) and len(cluster) >= 2:
                    out.append({
                        "campaign": camp, "side": side,
                        "span": (cluster[0]["ply"], cluster[-1]["ply"]),
                        "members": [
                            {"name": q["name"], "ply": q["ply"],
                             "stage": q["stage"], "role": members[q["name"]]}
                            for q in cluster],
                    })
                cluster = [p] if p is not None else []
    out.sort(key=lambda c: c["span"][0])
    return out


def curriculum() -> list[str]:
    """The teaching order the three levels imply."""
    L = ["== CURRICULUM =="]
    L.append("-- level 0: mechanisms (vocabulary; no reliability claims) --")
    for m, d in MECHANISMS.items():
        L.append(f"   {m}: {d}")
    L.append("-- level 1: plans (by corpus lift; each with witnesses) --")
    for f, (lf, ls) in sorted(PLAN_LIFT.items(),
                              key=lambda kv: -(kv[1][0] or 0)):
        s = f", slow {ls}" if ls else ""
        L.append(f"   {f}: lift {lf}{s}")
    L.append("-- level 2: campaigns (compositions; teach after members) --")
    for c, mem in CAMPAIGNS.items():
        core = [f for f, r in mem.items() if r == "core"]
        rest = [f"{f}({r})" for f, r in mem.items() if r != "core"]
        L.append(f"   {c}: core={'/'.join(core)}; {', '.join(rest)}")
    return L


if __name__ == "__main__":
    print("\n".join(curriculum()))
