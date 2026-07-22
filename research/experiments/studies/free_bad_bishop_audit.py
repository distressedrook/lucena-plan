"""free_bad_bishop_audit — three-leg audit of the NEW free_bad_bishop family
(2026-07-22 user request: "pushing the bad bishop to get rid of the
weakness — surface it and see if engine lines do it").

The rule (plan_diff.py): t pushes a pawn that stood in t's
bad_bishop set (non-capture), and t's backward count DROPS and
stays dropped to window end (dissolved or liquidated, not relocated).

Leg 1  CORPUS LIFT (actual vs seeded random, GM corpus, both regimes).
       Precondition-gated: only anchors where the side has a backward
       pawn count — both legs share the anchor, so the gate is fair.
Leg 2  ENGINE LINES (banked eng_shards + benchmark_v1; ZERO new engine
       calls). At benchmark positions with the precondition: does
       free_bad_bishop fire in an eval-equal engine PV (band 50cp, the
       reduce_agreement convention)? Compare vs the ACTUAL continuation
       at the same positions.

Run: python3 experiments/free_bad_bishop_audit.py [--corpus-games N]
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
from plan_diff import labels, snapshot
from weaknesses import bad_bishop

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
BENCH = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/benchmark_v1.jsonl"
ENG = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/eng_shards"
ANCHORS = (20, 30, 40, 50)
H_FAST, T_FAST = 12, 2
H_SLOW, T_SLOW = 25, 6
EQUAL_BAND = 50
WORKERS = 8


def fires(b, ucis_or_moves, h, t):
    if ucis_or_moves and isinstance(ucis_or_moves[0], str):
        mvs = [chess.Move.from_uci(u) for u in ucis_or_moves]
    else:
        mvs = ucis_or_moves
    return {lab.split(":")[0] for lab in labels(b, mvs, h, t)
            if lab.split(":")[1] == "free_bad_bishop"}


def _sides_with_badbishop(b):
    out = []
    if bad_bishop(b, chess.WHITE):
        out.append("W")
    if bad_bishop(b, chess.BLACK):
        out.append("B")
    return out


# ---------------------------------------------------------------- leg 1

def corpus_chunk(args):
    offsets, seed_base = args
    res_rows = []
    with open(PGN, encoding="latin-1") as f:
        for n, off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                if game.headers.get("Result", "*") not in ("1-0", "0-1",
                                                           "1/2-1/2"):
                    continue
                moves = list(game.mainline_moves())
            except Exception:
                continue
            for a in ANCHORS:
                if len(moves) < a + H_SLOW + 1:
                    continue
                b = game.board()
                for mv in moves[:a]:
                    b.push(mv)
                pre = _sides_with_badbishop(b)
                if not pre:
                    continue
                actual = moves[a:a + H_SLOW]
                rng = random.Random(seed_base + n * 1000 + a)
                cur = b.copy()
                rnd = []
                for _ in range(H_SLOW):
                    lg = list(cur.legal_moves)
                    if not lg:
                        break
                    m = rng.choice(lg)
                    rnd.append(m)
                    cur.push(m)
                row = {"pre": pre}
                for leg, mvs in (("a", actual), ("r", rnd)):
                    for reg, (h, tl) in (("f", (H_FAST, T_FAST)),
                                         ("s", (H_SLOW, T_SLOW))):
                        labs = labels(b, mvs, h, tl)
                        row[leg + reg] = sorted(
                            lab.split(":")[0] for lab in labs
                            if lab.split(":")[1] == "free_bad_bishop")
                res_rows.append(row)
    return res_rows


def leg1(max_games):
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
    print(f"\n== LEG 1: CORPUS LIFT (precondition anchors: {len(rows)}) ==")
    for reg in ("f", "s"):
        # a fire only counts if the firing SIDE had the precondition
        na = sum(1 for r in rows if set(r["a" + reg]) & set(r["pre"]))
        nr = sum(1 for r in rows if set(r["r" + reg]) & set(r["pre"]))
        pa = na / len(rows) if rows else 0.0
        pr = nr / len(rows) if rows else 0.0
        lift = pa / pr if pr else float("inf")
        print(f"  {'fast h12' if reg == 'f' else 'slow h25'}: "
              f"actual {na} ({pa:.2%})  random {nr} ({pr:.2%})  "
              f"LIFT {lift:.2f}")
    return rows


# ---------------------------------------------------------------- leg 2

def leg2():
    bench = {}
    with open(BENCH) as f:
        for line in f:
            r = json.loads(line)
            bench[r["id"]] = r
    n_pre = eng_fire = act_fire = eng_pos = 0
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
                pre = _sides_with_badbishop(b)
                if not pre:
                    continue
                n_pre += 1
                cp1 = r["pvs"][0]["cp"]
                equal = [p for p in r["pvs"]
                         if abs(p["cp"] - cp1) <= EQUAL_BAND]
                hit = False
                for pv in equal:
                    try:
                        if set(fires(b, pv["ucis"], H_SLOW, T_SLOW)) \
                                & set(pre):
                            hit = True
                            break
                    except Exception:
                        continue
                eng_pos += bool(equal)
                eng_fire += hit
                try:
                    act = bm.get("actual_ucis") or []
                    if set(fires(b, act[:H_SLOW], H_SLOW, T_SLOW)) \
                            & set(pre):
                        act_fire += 1
                except Exception:
                    pass
    print(f"\n== LEG 2: ENGINE LINES (banked shards, no new calls) ==")
    print(f"  benchmark positions with a bad bishop: {n_pre}")
    print(f"  free_bad_bishop fires in an eval-equal engine PV: "
          f"{eng_fire}/{eng_pos} ({eng_fire / eng_pos:.1%})"
          if eng_pos else "  (no engine rows)")
    print(f"  fires in the ACTUAL GM continuation:       "
          f"{act_fire}/{n_pre} ({act_fire / n_pre:.1%})" if n_pre else "")


if __name__ == "__main__":
    max_games = 0
    if "--corpus-games" in sys.argv:
        max_games = int(sys.argv[sys.argv.index("--corpus-games") + 1])
    leg1(max_games)
    leg2()
