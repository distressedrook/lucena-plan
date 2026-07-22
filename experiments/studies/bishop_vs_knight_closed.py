"""Bishops vs knights as a function of position closedness — GM corpus test of
'knights beat bishops in closed positions'.

Imbalance: a run >= MIN_RUN plies where one side has net more bishops and the
other net more knights (signs of dB = wB-bB and dN = wN-bN opposite).
Closedness: fraction of plies (from ply 20 on) that are 'closed-ish'
(>= 2 central rams, no open files, tension <= 2) — a relaxation of
closed_v0's hermetic predicate so the buckets have statistics.
Buckets: closed >= 0.5, semi 0.2..0.5, open < 0.2.
"""
from __future__ import annotations

import collections
import statistics
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/experiments")
from closed_v0 import skeleton

MIN_RUN = 20
MIDGAME_FROM = 20


def sq_color(sq: int) -> bool:
    return bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[sq])


def side_rank(sq: int, side: bool) -> int:
    r = chess.square_rank(sq)
    return r if side == chess.WHITE else 7 - r


def bishops_entombed(b: chess.Board, side: bool) -> bool:
    """True iff the side HAS a bishop and every bishop it has is entombed
    (>=3 own pawns on its color, >=2 rammed, bishop behind the ram wall)."""
    bs = list(b.pieces(chess.BISHOP, side))
    if not bs:
        return False
    ahead = 8 if side == chess.WHITE else -8
    for sq in bs:
        c = sq_color(sq)
        total = fixed = 0
        ram_rank = -1
        for p in b.pieces(chess.PAWN, side):
            if sq_color(p) != c:
                continue
            total += 1
            front = p + ahead
            if 0 <= front < 64:
                pc = b.piece_at(front)
                if pc and pc.piece_type == chess.PAWN and pc.color != side:
                    fixed += 1
                    ram_rank = max(ram_rank, side_rank(p, side))
        if not (total >= 3 and fixed >= 2 and side_rank(sq, side) < ram_rank):
            return False
    return True


def study(game):
    b = game.board()
    closed_ish, open_ish = [], []
    imbalance = []            # per ply: +1 white is bishop side, -1 black, 0 none
    configs = []
    ent = {chess.WHITE: [], chess.BLACK: []}
    for i, mv in enumerate(game.mainline_moves()):
        b.push(mv)
        for sd in (chess.WHITE, chess.BLACK):
            ent[sd].append(bishops_entombed(b, sd))
        rams, central, tension, open_files = skeleton(b)
        if i >= MIDGAME_FROM:
            closed_ish.append(central >= 2 and open_files == 0 and tension <= 2)
            open_ish.append(open_files >= 2 and rams <= 1)
        wB, wN = len(b.pieces(chess.BISHOP, chess.WHITE)), len(b.pieces(chess.KNIGHT, chess.WHITE))
        bB, bN = len(b.pieces(chess.BISHOP, chess.BLACK)), len(b.pieces(chess.KNIGHT, chess.BLACK))
        dB, dN = wB - bB, wN - bN
        if dB > 0 and dN < 0:
            imbalance.append(1)
        elif dB < 0 and dN > 0:
            imbalance.append(-1)
        else:
            imbalance.append(0)
        configs.append((wB, wN, bB, bN))
    n = len(imbalance)
    if n < MIDGAME_FROM + MIN_RUN or not closed_ish:
        return None
    # longest same-sign imbalance run
    best_side, best_len, best_at = 0, 0, 0
    k = 0
    while k < n:
        if imbalance[k] == 0:
            k += 1
            continue
        j = k
        while j + 1 < n and imbalance[j + 1] == imbalance[k]:
            j += 1
        if j - k + 1 > best_len:
            best_side, best_len, best_at = imbalance[k], j - k + 1, k
        k = j + 1
    if best_len < MIN_RUN:
        return None
    mode = collections.Counter(configs[best_at:best_at + best_len]).most_common(1)[0][0]
    frac = sum(closed_ish) / len(closed_ish)
    bside = chess.WHITE if best_side > 0 else chess.BLACK
    ent_frac = statistics.mean(ent[bside][best_at:best_at + best_len])
    res = game.headers.get("Result", "*")
    if res not in ("1-0", "0-1", "1/2-1/2"):
        return None
    score_white = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[res]
    bishop_score = score_white if best_side > 0 else 1.0 - score_white
    return {"closedness": frac, "openness": sum(open_ish) / len(open_ish),
            "bishop_score": bishop_score,
            "run": best_len, "mode": mode, "entombed": ent_frac >= 0.3}


if __name__ == "__main__":
    n = 0
    rows = []
    with open("/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn",
              encoding="latin-1") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            n += 1
            if n % 10000 == 0:
                print(f"scanned {n}, imbalance games {len(rows)}", flush=True)
            try:
                r = study(game)
            except Exception:
                continue
            if r:
                rows.append(r)

    def bucket(f):
        return "closed" if f >= 0.5 else ("semi" if f >= 0.2 else "open")

    print(f"\ngames with sustained B-vs-N imbalance: {len(rows)}/{n}")
    print(f"{'bucket':>8} | {'n':>5} | {'bishop-side score':>17} | {'draw rate':>9}")
    for bk in ("open", "semi", "closed"):
        rs = [r for r in rows if bucket(r["closedness"]) == bk]
        if not rs:
            continue
        sc = statistics.mean(r["bishop_score"] for r in rs)
        dr = statistics.mean(1.0 if r["bishop_score"] == 0.5 else 0.0 for r in rs)
        print(f"{bk:>8} | {len(rs):>5} | {sc:>17.3f} | {100*dr:>8.1f}%")
    print("\nby TRUE openness (open files >= 2, rams <= 1):")
    print(f"{'bucket':>10} | {'n':>5} | {'bishop-side score':>17} | {'draw rate':>9}")
    for bk, lo, hi in (("pawn-full", -1, 0.2), ("semi-open", 0.2, 0.5),
                       ("open", 0.5, 2)):
        rs = [r for r in rows if lo <= r["openness"] < hi]
        if not rs:
            continue
        sc = statistics.mean(r["bishop_score"] for r in rs)
        dr = statistics.mean(1.0 if r["bishop_score"] == 0.5 else 0.0 for r in rs)
        print(f"{bk:>10} | {len(rs):>5} | {sc:>17.3f} | {100*dr:>8.1f}%")
    def cfg_label(m):
        wB, wN, bB, bN = m
        white_is_bishop = wB - bB > 0
        us = (wB, wN) if white_is_bishop else (bB, bN)
        them = (bB, bN) if white_is_bishop else (wB, wN)
        kind = "pair" if us[0] == 2 else "single"
        return f"{kind} {us[0]}B{us[1]}N vs {them[0]}B{them[1]}N " \
               f"({'W' if white_is_bishop else 'B'} has bishops)"

    print("\ntrue-open bucket by raw config (n >= 30):")
    ms_open = [r for r in rows if r["openness"] >= 0.5]
    for mode, k in collections.Counter(r["mode"] for r in ms_open).most_common(10):
        ms = [r for r in ms_open if r["mode"] == mode]
        if len(ms) < 30:
            continue
        print(f"  {cfg_label(mode):>34}: {statistics.mean(r['bishop_score'] for r in ms):.3f} "
              f"(n={len(ms)})")
    print("\nbishop PAIR vs single bishop, by true openness (bishop-side score):")
    for bk, lo, hi in (("pawn-full", -1, 0.2), ("semi-open", 0.2, 0.5), ("open", 0.5, 2)):
        for kind, test in (("pair", lambda m, w: (m[0] if w else m[2]) == 2),
                           ("single", lambda m, w: (m[0] if w else m[2]) == 1)):
            rs = [r for r in rows if lo <= r["openness"] < hi
                  and test(r["mode"], r["mode"][0] - r["mode"][2] > 0)]
            if len(rs) >= 20:
                print(f"  {bk:>10} {kind:>6} | n {len(rs):>5} | "
                      f"{statistics.mean(r['bishop_score'] for r in rs):.3f}")
    print("\nbishop-side score by closedness x bishop-entombment:")
    for bk in ("open", "semi", "closed"):
        for e in (False, True):
            rs = [r for r in rows if bucket(r["closedness"]) == bk and r["entombed"] == e]
            if len(rs) < 5:
                continue
            sc = statistics.mean(r["bishop_score"] for r in rs)
            print(f"  {bk:>6} {'entombed' if e else 'free    '} | n {len(rs):>5} | {sc:.3f}")
    print("\nby raw config (top, all buckets), bishop-side score not-closed vs closed:")
    for mode, k in collections.Counter(r["mode"] for r in rows).most_common(8):
        ms = [r for r in rows if r["mode"] == mode]
        o = [r["bishop_score"] for r in ms if bucket(r["closedness"]) == "open"]
        c = [r["bishop_score"] for r in ms if bucket(r["closedness"]) == "closed"]
        so = f"{statistics.mean(o):.3f} (n={len(o)})" if o else "—"
        sc = f"{statistics.mean(c):.3f} (n={len(c)})" if c else "—"
        print(f"  {cfg_label(mode):>34} ({k:>5}): not-closed {so} | closed {sc}")
