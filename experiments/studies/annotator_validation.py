"""EXTERNAL VALIDATION: do the machine's names match human annotators'?

For every annotator comment naming one of our concepts (23 annotated PGN
collections, ValdemarOrn/Chess), check whether the machine independently
finds the same concept:
  plan concepts  -> plan_diff.labels over the +-12-ply window around the
                    comment (slow regime)
  state concepts -> the state detectors at the commented position
Control: the same check against a window/position drawn from a DIFFERENT
randomly chosen game (concept base rates). Match above control = external
agreement with human annotators.
"""
from __future__ import annotations

import glob
import random
import re
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans")
from plan_diff import labels, snapshot
from weaknesses import weak_pawns, entombed_bishops

DIR = "/Users/avismara/Development/lucena/lucena-plans/data/annotated"

PLAN_CONCEPTS = {
    "minority attack": {"minority_attack", "minority_attack_general"},
    "blockad": {"blockade"},
    "outpost": {"outpost_occupation"},
    "passed pawn": {"passer_creation", "passer_push"},
    "seventh rank": {"seventh_invasion"}, "7th rank": {"seventh_invasion"},
    "open file": {"rook_activation"},
    "pawn storm": {"pawn_storm"},
}
STATE_CONCEPTS = {
    "bad bishop": lambda b: bool(entombed_bishops(b, chess.WHITE)
                                 or entombed_bishops(b, chess.BLACK)),
    "bishop pair": lambda b: (len(b.pieces(chess.BISHOP, chess.WHITE)) >= 2)
                             != (len(b.pieces(chess.BISHOP, chess.BLACK)) >= 2),
    "two bishops": lambda b: (len(b.pieces(chess.BISHOP, chess.WHITE)) >= 2)
                             != (len(b.pieces(chess.BISHOP, chess.BLACK)) >= 2),
    "weak pawn": lambda b: bool(weak_pawns(b, chess.WHITE)
                                or weak_pawns(b, chess.BLACK)),
}
WINDOW_BACK, WINDOW_FWD = 12, 13


def game_windows(game):
    """(boards, moves) along the mainline plus per-node comments."""
    boards, moves, comments = [], [], []
    b = game.board()
    node = game
    while node.variations:
        node = node.variation(0)
        moves.append(node.move)
        comments.append(node.comment or "")
        b.push(node.move)
        boards.append(b.copy(stack=False))
    return boards, moves, comments


def plan_match(boards, moves, ply, families):
    lo = max(0, ply - WINDOW_BACK)
    start = boards[lo - 1] if lo > 0 else None
    if start is None:
        return None
    seq = moves[lo:ply + WINDOW_FWD]
    ls = labels(start, seq, horizon=25, tail=6)
    return bool(families & {l.split(":")[1] for l in ls})


if __name__ == "__main__":
    games = []
    for path in sorted(glob.glob(f"{DIR}/*.pgn")):
        with open(path, encoding="latin-1") as f:
            while True:
                try:
                    g = chess.pgn.read_game(f)
                except Exception:
                    break
                if g is None:
                    break
                games.append(g)
    print(f"games parsed: {len(games)}")
    parsed = []
    for g in games:
        try:
            parsed.append(game_windows(g))
        except Exception:
            continue
    rng = random.Random(7)

    mentions = []              # (kind, concept, game_idx, ply)
    for gi, (boards, moves, comments) in enumerate(parsed):
        for ply, c in enumerate(comments):
            if not c:
                continue
            low = c.lower()
            for kw in PLAN_CONCEPTS:
                if kw in low:
                    mentions.append(("plan", kw, gi, ply))
            for kw in STATE_CONCEPTS:
                if kw in low:
                    mentions.append(("state", kw, gi, ply))
    print(f"concept mentions located: {len(mentions)}")

    results = {}
    for kind, kw, gi, ply in mentions:
        boards, moves, comments = parsed[gi]
        # control: same concept tested at a random other game/ply
        for attempt in range(20):
            gj = rng.randrange(len(parsed))
            bj, mj, _ = parsed[gj]
            if gj != gi and len(bj) > max(ply + 2, WINDOW_BACK + WINDOW_FWD + 2):
                # PHASE-MATCHED control: same ply in the other game
                pj = min(max(ply, WINDOW_BACK + 1), len(bj) - WINDOW_FWD - 1)
                break
        else:
            continue
        if kind == "plan":
            hit = plan_match(boards, moves, ply, PLAN_CONCEPTS[kw])
            ctl = plan_match(bj, mj, pj, PLAN_CONCEPTS[kw])
        else:
            test = STATE_CONCEPTS[kw]
            hit = test(boards[ply]) if ply < len(boards) else None
            ctl = test(bj[pj])
        if hit is None or ctl is None:
            continue
        r = results.setdefault(kw, [0, 0, 0, 0])   # hit, n, ctl_hit, ctl_n
        r[0] += hit; r[1] += 1; r[2] += ctl; r[3] += 1

    print(f"\n{'concept':>16} | {'n':>3} | {'machine agrees':>14} | {'control':>8} | verdict")
    for kw, (h, n, ch, cn) in sorted(results.items(), key=lambda kv: -kv[1][1]):
        if n < 3:
            continue
        agree, ctl = h / n, ch / cn
        verdict = ("STRONG" if agree > ctl * 1.8 and agree > 0.4
                   else "positive" if agree > ctl * 1.2
                   else "NO SIGNAL")
        print(f"{kw:>16} | {n:>3} | {100*agree:>13.0f}% | {100*ctl:>7.0f}% | {verdict}")
