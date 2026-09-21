#!/usr/bin/env python3
"""Residual-attribution study, stage 1: harvest + features.

R = engine_cp - adjusted_material_cp (both White-POV). This stage builds
the labeled table: positions with engine labels and the deterministic
feature differentials that will try to explain R.

Sampling fixes the GM material-balance selection bias by construction:
besides the 4,000 benchmark roots, we harvest INTERIOR positions along
the banked MultiPV lines (plies 2..10 into each of the 4 PVs). A position
on a PV inherits that line's root cp (minimax consistency of a principal
variation) — validated against fresh fixed-node relabels by
validate_labels.py before the labels are trusted. Interiors are where
material imbalance with compensation actually lives; GM argmax positions
never contain it.

Output: dataset.jsonl — one row per unique position:
  {id, seed, line, ply, fen, cp, quiet, phase, adjusted_cp, r, feats:{...}}

All features are White-minus-Black differentials (or signed flags), so the
color-mirror of a position negates the whole vector along with R.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = "/Users/avismara/Projects/active/lucena"
sys.path.insert(0, f"{ROOT}/engine/python")
sys.path.insert(0, f"{ROOT}/lucena-core/python")
sys.path.insert(0, f"{ROOT}/lucena-plans/src")

import chess

from lucena_core.board import Board
from lucena_core import metrics as M
from lucena_core.positional import (analyze_positional, attack_viability,
                                    region_control)
from lucena_core.reads import game_phase

BENCH = f"{ROOT}/lucena-plans/research/gpu_benchmark/benchmark_v1.jsonl"
ENG = f"{ROOT}/lucena-plans/research/experiments/eng_shards"
OUT = os.path.join(os.path.dirname(__file__), "dataset.jsonl")

PREFIXES = (2, 4, 6, 8, 10)     # interior sampling depths along each PV
CP_CLIP = 300                   # beyond this eval is win-distance, not R


def quietness(b: chess.Board) -> bool:
    """No pending SEE>0 grab for either side and not in check."""
    if b.is_check():
        return False
    if M._best_grab(b)[0] > 0:
        return False
    bn = b.copy(stack=False)
    bn.push(chess.Move.null())
    return M._best_grab(bn)[0] <= 0


def features(fen: str) -> dict | None:
    """The White-minus-Black differential feature vector."""
    b = chess.Board(fen)
    try:
        pos = analyze_positional(Board(fen))
    except ValueError:
        return None
    terms = pos["terms"]
    f: dict[str, float] = {}

    # --- tempo + the four non-material classical term cps (White-POV).
    # The percentile features below are the interpretable instruments;
    # these cps test whether PST-grade placement detail moves the ceiling.
    f["stm"] = 1 if b.turn == chess.WHITE else -1
    f["king_safety_cp"] = terms["king_safety"]["cp"]
    f["activity_cp"] = terms["activity"]["cp"]
    f["pawns_cp"] = terms["pawns"]["cp"]
    f["center_cp"] = terms["center"]["cp"]

    # --- king: standing danger + prospective viability
    ks = terms["king_safety"]["features"]
    dw = ks.get("white", {}).get("danger", 0)
    db = ks.get("black", {}).get("danger", 0)
    f["king_danger"] = db - dw                     # + = Black's king worse
    f["king_center"] = (int(ks.get("black", {}).get("centered_uncastled", 0))
                        - int(ks.get("white", {}).get("centered_uncastled", 0)))
    via = attack_viability(fen)
    f["attack_viability"] = via["white"]["norm"] - via["black"]["norm"]

    # --- activity (phase-conditioned GM percentiles)
    act = terms["activity"]["features"]
    for side in ("white", "black"):
        rows = act.get(f"pieces_{side}", [])
        act_mean = (sum(e["norm"] for e in rows) / len(rows)) if rows else 0.5
        passive = sum(1 for e in rows if e["norm"] <= 0.10)
        if side == "white":
            wm, wp = act_mean, passive
        else:
            bm, bp = act_mean, passive
    f["activity_mean"] = wm - bm
    f["passive_pieces"] = bp - wp                  # + = Black has more duds

    # --- regions
    rc = region_control(fen)
    f["center_share"] = rc["center"]["white"] - rc["center"]["black"]
    f["kingside_share"] = rc["kingside"]["white"] - rc["kingside"]["black"]
    f["queenside_share"] = (rc["queenside"]["white"]
                            - rc["queenside"]["black"])
    outp_w = sum(1 for h in rc["holes"]
                 if h["outpost"] and h["camp"] == "black")
    outp_b = sum(1 for h in rc["holes"]
                 if h["outpost"] and h["camp"] == "white")
    f["outposts"] = outp_w - outp_b
    open_w = sum(1 for r in rc["files"] if r["controller"] == "White")
    open_b = sum(1 for r in rc["files"] if r["controller"] == "Black")
    f["open_files_held"] = open_w - open_b

    # --- space (validated normalized scores, per region summed)
    sp = M.space_report(fen)
    f["space"] = sum(sp[reg]["white"]["score"] - sp[reg]["black"]["score"]
                     for reg in ("queenside", "center", "kingside"))

    # --- passers
    pr = M.passer_report(fen)
    pw, pb = pr["white"], pr["black"]
    f["passer_count"] = len(pw) - len(pb)
    best = lambda rows: max((r["score"] for r in rows), default=0.0)
    f["passer_best"] = best(pw) - best(pb)
    run = lambda rows: sum(1 for r in rows
                           if r["escorted"] and not r["blockaded"]
                           and r["path_clear"])
    f["passer_running"] = run(pw) - run(pb)

    # --- pawn structure counts (the raw ingredients, not the cp reweight)
    feats = terms["pawns"]["features"]
    f["isolated"] = (len(feats["black"]["isolated"])
                     - len(feats["white"]["isolated"]))
    f["doubled"] = (len(feats["black"]["doubled_files"])
                    - len(feats["white"]["doubled_files"]))
    f["islands"] = feats["black"]["islands"] - feats["white"]["islands"]

    # --- color complexes (validated flag) + bishop pair
    cc = M.color_complex(fen)
    flag = 0
    for tone in ("light", "dark"):
        if cc[tone]["weak_for"] == "Black":
            flag += 1
        elif cc[tone]["weak_for"] == "White":
            flag -= 1
    f["weak_complex"] = flag
    nb = lambda c: len(b.pieces(chess.BISHOP, c))
    f["bishop_pair"] = int(nb(chess.WHITE) >= 2) - int(nb(chess.BLACK) >= 2)

    # --- trapped / restricted
    tp = M.trapped_pieces(fen)
    cnt = lambda rows, st: sum(1 for r in rows if r["state"] == st)
    f["trapped"] = (cnt(tp["black"], "trapped") - cnt(tp["white"], "trapped"))
    f["restricted"] = (cnt(tp["black"], "restricted")
                       - cnt(tp["white"], "restricted"))

    # --- levers (data-only tier; kept to measure, not to speak)
    kb = M.pawn_breaks(fen)
    f["breaks_playable"] = (sum(1 for r in kb["white"] if r["playable"])
                            - sum(1 for r in kb["black"] if r["playable"]))
    return f


def main():
    shards = {}
    for name in sorted(os.listdir(ENG)):
        with open(os.path.join(ENG, name)) as fh:
            for line in fh:
                rec = json.loads(line)
                shards[rec["id"]] = rec["pvs"]

    seen: set[str] = set()
    n_in = n_out = 0
    with open(BENCH) as fh, open(OUT, "w") as out:
        for line in fh:
            seed = json.loads(line)
            pvs = shards.get(seed["id"])
            if not pvs:
                continue
            positions = [(seed["fen"], 0, 0, pvs[0]["cp"])]
            for li, pv in enumerate(pvs[:4]):
                b = chess.Board(seed["fen"])
                ok = True
                for i, u in enumerate(pv["ucis"][:max(PREFIXES)]):
                    m = chess.Move.from_uci(u)
                    if m not in b.legal_moves:
                        ok = False
                        break
                    b.push(m)
                    if (i + 1) in PREFIXES:
                        positions.append((b.fen(), li + 1, i + 1, pv["cp"]))
                del ok
            for fen, li, ply, cp in positions:
                n_in += 1
                key = " ".join(fen.split()[:4])
                if key in seen or abs(cp) > CP_CLIP:
                    continue
                seen.add(key)
                bb = chess.Board(fen)
                try:
                    ms = M.material_stability(fen)
                    ph = game_phase(fen)["phase"]
                    fv = features(fen)
                except Exception:
                    continue
                if fv is None:
                    continue
                out.write(json.dumps({
                    "id": f"{seed['id']}_l{li}_p{ply}",
                    "seed": seed["id"], "line": li, "ply": ply, "fen": fen,
                    "cp": cp, "quiet": quietness(bb), "phase": ph,
                    "adjusted_cp": ms["adjusted_cp"],
                    "r": cp - ms["adjusted_cp"], "feats": fv,
                }) + "\n")
                n_out += 1
    print(f"harvested {n_out} unique labeled positions "
          f"(of {n_in} candidates)")


if __name__ == "__main__":
    main()
