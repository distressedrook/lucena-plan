"""keep_king_uncastled_audit — three-leg audit of the NEW keep_king_uncastled
family (2026-07-23 user request: "Surface a new plan - KEEP_KING_UNCASTLED
... the center is locked ... the rule is, king isn't castled in the next 6
moves." → "Let's lift.").

The family is the vocabulary's first NEGATIVE-event plan: it is verified by
the ABSENCE of castling. That inverts the usual audit logic — random legal
lines rarely castle, so the naive lift (P(hold|GM)/P(hold|random)) is
expected to hug 1 from BELOW; the decision-relevant evidence is the OUTCOME
split (does the side that holds score better than the side that castles
anyway, given the locked-center trigger?), the SIMPLIFY/AVOID-TRADES
dose-response precedent.

Trigger (suggest.py): closed_v0.center_locked (>= 2 central rams, zero
central tension) AND the side has not castled AND still holds a castling
right (no right = holding is forced, not a plan — those anchors are
excluded so the measurement is about a real choice).
Hold rule (verify.py): the side does not castle within 12 plies (6 moves).

Leg 1  CORPUS HOLD-RATE (actual vs seeded random, GM corpus).
Leg 2  OUTCOME (triggered anchors: side score when HELD vs CASTLED-ANYWAY;
       the plan's price).
Leg 3  ENGINE LINES (banked eng_shards + benchmark_v1; ZERO new engine
       calls): at triggered benchmark positions, does EVERY eval-equal PV
       hold (the verify contract) — and does the actual GM continuation?

Run: .venv/python research/experiments/studies/keep_king_uncastled_audit.py \
         [--corpus-games N]
"""
from __future__ import annotations

import json
import os
import random
import sys
from multiprocessing import Pool

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
from closed_v0 import center_locked

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
BENCH = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/benchmark_v1.jsonl"
ENG = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/eng_shards"
ANCHORS = (20, 30, 40, 50)
HOLD_PLIES = 12          # the rule: not castled in the next 6 moves
EQUAL_BAND = 50
WORKERS = 8

SCORE = {"1-0": {"W": 1.0, "B": 0.0}, "0-1": {"W": 0.0, "B": 1.0},
         "1/2-1/2": {"W": 0.5, "B": 0.5}}


def _castles_within(b, moves, white, plies):
    b0 = b.copy()
    for mv in moves[:plies]:
        if b0.turn == white and b0.is_castling(mv):
            return True
        b0.push(mv)
    return False


def _triggered_sides(b, castled):
    """Sides for which the plan candidate would fire at this anchor, with
    the real-choice gate (right still held)."""
    if not center_locked(b):
        return []
    out = []
    if not castled["W"] and b.has_castling_rights(chess.WHITE):
        out.append("W")
    if not castled["B"] and b.has_castling_rights(chess.BLACK):
        out.append("B")
    return out


# ---------------------------------------------------------------- legs 1+2

def corpus_chunk(args):
    offsets, seed_base = args
    rows = []
    with open(PGN, encoding="latin-1") as f:
        for n, off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                result = game.headers.get("Result", "*")
                if result not in SCORE:
                    continue
                moves = list(game.mainline_moves())
            except Exception:
                continue
            b = game.board()
            castled = {"W": False, "B": False}
            for a, mv in enumerate(moves):
                if a in ANCHORS and len(moves) >= a + HOLD_PLIES:
                    for t in _triggered_sides(b, castled):
                        white = t == "W"
                        held_a = not _castles_within(b, moves[a:], white,
                                                     HOLD_PLIES)
                        rng = random.Random(seed_base + n * 1000 + a
                                            + (0 if white else 1))
                        cur, rnd = b.copy(), []
                        for _ in range(HOLD_PLIES):
                            lg = list(cur.legal_moves)
                            if not lg:
                                break
                            m = rng.choice(lg)
                            rnd.append(m)
                            cur.push(m)
                        held_r = not _castles_within(b, rnd, white,
                                                     HOLD_PLIES)
                        rows.append({"side": t, "held_a": held_a,
                                     "held_r": held_r,
                                     "score": SCORE[result][t]})
                if b.is_castling(mv):
                    castled["W" if b.turn == chess.WHITE else "B"] = True
                b.push(mv)
    return rows


def legs12(max_games):
    offsets = []
    with open(PGN, encoding="latin-1") as f:
        n = 0
        while True:
            off = f.tell()
            line = f.readline()
            if not line:
                break
            if line.startswith("[Event "):
                offsets.append((n, off))
                n += 1
                if max_games and n >= max_games:
                    break
    chunks = [offsets[i::WORKERS] for i in range(WORKERS)]
    rows = []
    with Pool(WORKERS) as pool:
        for part in pool.imap_unordered(corpus_chunk,
                                        [(c, 777) for c in chunks]):
            rows.extend(part)

    print(f"\n== LEG 1: CORPUS HOLD-RATE (triggered anchors: {len(rows)}) ==")
    na = sum(r["held_a"] for r in rows)
    nr = sum(r["held_r"] for r in rows)
    pa = na / len(rows) if rows else 0.0
    pr = nr / len(rows) if rows else 0.0
    print(f"  GM holds {HOLD_PLIES}p:     {na} ({pa:.1%})")
    print(f"  random holds {HOLD_PLIES}p: {nr} ({pr:.1%})")
    print(f"  LIFT {pa / pr:.2f}" if pr else "  LIFT inf")
    print("  (negative event — random not-castling is cheap; read the "
          "OUTCOME leg for the decision evidence)")

    print("\n== LEG 2: OUTCOME (the plan's price, dose-response) ==")
    for label, sel in (("HELD (kept uncastled 6 moves)",
                        [r for r in rows if r["held_a"]]),
                       ("CASTLED ANYWAY",
                        [r for r in rows if not r["held_a"]])):
        if sel:
            sc = sum(r["score"] for r in sel) / len(sel)
            print(f"  {label:<32} n={len(sel):>5}  score {sc:.3f}")
    for t in ("W", "B"):
        held = [r for r in rows if r["side"] == t and r["held_a"]]
        cast = [r for r in rows if r["side"] == t and not r["held_a"]]
        if held and cast:
            sh = sum(r["score"] for r in held) / len(held)
            sc = sum(r["score"] for r in cast) / len(cast)
            print(f"    {t}: held {sh:.3f} (n={len(held)}) vs "
                  f"castled {sc:.3f} (n={len(cast)})  Δ{sh - sc:+.3f}")
    return rows


# ---------------------------------------------------------------- leg 3

def leg3():
    bench = {}
    with open(BENCH) as f:
        for line in f:
            r = json.loads(line)
            bench[r["id"]] = r
    n_trig = eng_hold = eng_pos = act_hold = act_n = 0
    for fn in sorted(os.listdir(ENG)):
        if not fn.endswith(".jsonl"):
            continue
        with open(os.path.join(ENG, fn)) as f:
            for line in f:
                r = json.loads(line)
                bm = bench.get(r["id"])
                if bm is None or not r.get("pvs"):
                    continue
                b = chess.Board(bm["fen"])
                # benchmark rows are bare FENs: castling rights stand in for
                # the not-yet-castled state (a castled king has no rights)
                trig = []
                if center_locked(b):
                    if b.has_castling_rights(chess.WHITE):
                        trig.append(True)
                    if b.has_castling_rights(chess.BLACK):
                        trig.append(False)
                if not trig:
                    continue
                n_trig += 1
                cp1 = r["pvs"][0]["cp"]
                equal = [p for p in r["pvs"]
                         if abs(p["cp"] - cp1) <= EQUAL_BAND]
                for white in trig:
                    if equal:
                        eng_pos += 1
                        try:
                            if all(not _castles_within(
                                    b, [chess.Move.from_uci(u)
                                        for u in pv["ucis"]],
                                    white, HOLD_PLIES) for pv in equal):
                                eng_hold += 1
                        except Exception:
                            eng_pos -= 1
                    act = bm.get("actual_ucis") or []
                    if len(act) >= HOLD_PLIES:
                        act_n += 1
                        try:
                            if not _castles_within(
                                    b, [chess.Move.from_uci(u) for u in act],
                                    white, HOLD_PLIES):
                                act_hold += 1
                        except Exception:
                            act_n -= 1
    print("\n== LEG 3: ENGINE LINES (banked shards, no new calls) ==")
    print(f"  benchmark positions with the trigger: {n_trig}")
    if eng_pos:
        print(f"  EVERY eval-equal PV holds (the verify contract): "
              f"{eng_hold}/{eng_pos} ({eng_hold / eng_pos:.1%})")
    if act_n:
        print(f"  actual GM continuation holds:                    "
              f"{act_hold}/{act_n} ({act_hold / act_n:.1%})")


if __name__ == "__main__":
    max_games = 0
    if "--corpus-games" in sys.argv:
        max_games = int(sys.argv[sys.argv.index("--corpus-games") + 1])
    legs12(max_games)
    leg3()
