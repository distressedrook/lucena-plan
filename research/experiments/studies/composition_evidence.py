"""composition_evidence — which families NEST inside which, empirically.

For same-side family pairs within the same actual-future window (v6 lift
shards, slow regime), compute co-occurrence lift:
    colift(A, B) = P(A & B) / (P(A) * P(B))
restricted to the ACTUAL leg (GM futures). High colift between a retired
"mechanism" and a production plan = evidence the mechanism is a COMPONENT
of that plan (the rook_lift verdict, generalized). The same matrix in the
RANDOM leg is the floor: composition that survives the ratio
colift_actual / colift_random is chess, not co-frequency.

Output: for each retired/candidate family, its top production-plan hosts.
"""
from __future__ import annotations

import collections
import glob
import json

SHARDS = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/lift_shards"

MECHANISMS = {"rook_lift", "pair_acquisition", "storm_launch",
              "fix_then_attack", "wing_expansion", "majority_roll",
              "bind_squeeze", "entomb", "open_king", "deny_castling",
              "seventh_invasion", "minority_attack_general"}
PLANS = {"weakness_harvest", "outpost_occupation", "rook_activation",
         "prepared_break", "chain_base_attack", "heavy_battery",
         "trade_into_endgame", "remove_defender", "alternation",
         "simplification", "blockade", "passer_creation", "passer_push",
         "pawn_storm", "king_march", "center_break_vs_king",
         "seal_to_entomb", "bad_bishop_escape", "minority_attack"}


def fams_side(leg):
    """(side, family) pairs, stage-stripped."""
    out = set()
    for l in leg:
        side, rest = l.split(":", 1)
        out.add((side, rest.split(":")[0]))
    return out


if __name__ == "__main__":
    rows = []
    for p in sorted(glob.glob(f"{SHARDS}/shard_*.jsonl")):
        with open(p) as f:
            rows.extend(json.loads(l) for l in f)
    N = len(rows) * 2                       # each row = two (side, window) obs
    print(f"anchors: {len(rows)} ({N} side-windows)")

    for legname, key in (("ACTUAL", "as"), ("RANDOM", "rs")):
        single = collections.Counter()
        pair = collections.Counter()
        for r in rows:
            fs = fams_side(r[key])
            for t in ("W", "B"):
                mine = {f for s, f in fs if s == t}
                for f in mine:
                    single[f] += 1
                for m in mine & MECHANISMS:
                    for pl in mine & PLANS:
                        pair[(m, pl)] += 1
        if legname == "ACTUAL":
            a_single, a_pair = single, pair
        else:
            r_single, r_pair = single, pair

    print(f"\n{'mechanism':>24} -> top plan hosts "
          f"(colift_actual, vs random-leg colift)")
    for m in sorted(MECHANISMS):
        if a_single[m] < 30:
            continue
        scored = []
        for pl in PLANS:
            k = a_pair[(m, pl)]
            if k < 15:
                continue
            co_a = (k / N) / ((a_single[m] / N) * (a_single[pl] / N))
            kr = r_pair[(m, pl)]
            co_r = ((kr / N) / ((r_single[m] / N) * (r_single[pl] / N))
                    if kr >= 5 and r_single[m] and r_single[pl] else None)
            ratio = co_a / co_r if co_r else float("inf")
            scored.append((co_a, ratio, pl, k))
        scored.sort(reverse=True)
        tops = ", ".join(
            f"{pl} x{co:.1f}({'inf' if ratio == float('inf') else f'{ratio:.1f}'}r, n={k})"
            for co, ratio, pl, k in scored[:4])
        print(f"{m:>24} [{a_single[m]:>5}] -> {tops}")
