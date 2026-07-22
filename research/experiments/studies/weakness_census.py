"""Two-weaknesses test with the FULL weakness taxonomy (see weaknesses.py).

For each detected minority-attack game, post-lever, per ply, census the
DEFENDER's camp: weak pawns, entombed bishops, occupied outposts, exposed
king. Report attacker score by:
  achieved census   — max level held >= HOLD consecutive plies
  created           — cumulative distinct weaknesses ever seen
  harvested         — weak pawns actually captured
  per-type presence — which weakness types predict conversion
"""
from __future__ import annotations

import glob
import statistics
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
from weaknesses import census

HOLD = 8
TYPES = ["weak_pawns", "entombed_bishops", "occupied_outposts", "exposed_king"]


def achieved_level(series: list[int], hold: int = HOLD) -> int:
    best = 0
    for c in range(1, max(series, default=0) + 1):
        run = 0
        for v in series:
            run = run + 1 if v >= c else 0
            if run >= hold:
                best = c
                break
    return best


if __name__ == "__main__":
    DIRS = ["/Users/avismara/Development/lucena/lucena-plans/minority-attack",
            "/Users/avismara/Development/lucena/lucena-plans/minority-attack-gm"]
    rows = []
    for d in DIRS:
        corpus = "gm" if d.endswith("gm") else "lichess"
        for path in glob.glob(d + "/[0-9]*.pgn"):
            game = chess.pgn.read_game(open(path))
            h = game.headers
            side = chess.WHITE if h["PlanSide"] == "white" else chess.BLACK
            lever = int(h["PlanSpan"].split("-")[1])
            res = h.get("Result", "*")
            if res not in ("1-0", "0-1", "1/2-1/2"):
                continue
            sc = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[res]
            if side == chess.BLACK:
                sc = 1.0 - sc
            b = game.board()
            series = []
            type_plies = {t: 0 for t in TYPES}
            seen_files = set()
            seen_flags = set()
            harvested = 0
            prev_weak = set()
            for i, mv in enumerate(game.mainline_moves()):
                mover = b.turn
                is_cap = b.is_capture(mv)
                b.push(mv)
                if i <= lever:
                    continue
                if mover == side and is_cap and mv.to_square in prev_weak:
                    harvested += 1
                c = census(b, not side)
                prev_weak = set(c["weak_pawns"])
                series.append(c["total"])
                for t in TYPES:
                    v = c[t]
                    if (v if isinstance(v, bool) else len(v)):
                        type_plies[t] += 1
                seen_files |= {chess.square_file(s) for s in c["weak_pawns"]}
                if c["entombed_bishops"]:
                    seen_flags.add("eb")
                if c["occupied_outposts"]:
                    seen_flags.add("op")
                if c["exposed_king"]:
                    seen_flags.add("ek")
            if len(series) < HOLD:
                continue
            n = len(series)
            rows.append({"corpus": corpus, "score": sc,
                         "achieved": achieved_level(series),
                         "created": len(seen_files) + len(seen_flags),
                         "harvested": harvested,
                         **{t: type_plies[t] / n >= 0.25 for t in TYPES}})

    print(f"games: {len(rows)}")
    print(f"\n{'achieved':>9} | {'n':>4} | {'attacker score':>14} | {'win rate':>8}")
    for c in (0, 1, 2, 3):
        rs = [r for r in rows if (r["achieved"] == c if c < 3 else r["achieved"] >= 3)]
        if len(rs) < 5:
            continue
        wr = statistics.mean(1.0 if r["score"] == 1.0 else 0.0 for r in rs)
        print(f"{(str(c) if c < 3 else '3+'):>9} | {len(rs):>4} | "
              f"{statistics.mean(r['score'] for r in rs):>14.3f} | {100*wr:>7.1f}%")

    print(f"\n{'created':>8} | {'n':>4} | {'attacker score':>14}")
    for c in (0, 1, 2, 3):
        rs = [r for r in rows if (r["created"] == c if c < 3 else r["created"] >= 3)]
        if len(rs) < 5:
            continue
        print(f"{(str(c) if c < 3 else '3+'):>8} | {len(rs):>4} | "
              f"{statistics.mean(r['score'] for r in rs):>14.3f}")

    print(f"\n{'harvested':>10} | {'n':>4} | {'attacker score':>14} | {'win rate':>8}")
    for hv in (0, 1, 2):
        rs = [r for r in rows if (r["harvested"] == hv if hv < 2 else r["harvested"] >= 2)]
        if len(rs) < 5:
            continue
        wr = statistics.mean(1.0 if r["score"] == 1.0 else 0.0 for r in rs)
        print(f"{(str(hv) if hv < 2 else '2+'):>10} | {len(rs):>4} | "
              f"{statistics.mean(r['score'] for r in rs):>14.3f} | {100*wr:>7.1f}%")

    print("\nper-type (present >= 25% of post-lever plies vs absent), attacker score:")
    for t in TYPES:
        yes = [r for r in rows if r[t]]
        no = [r for r in rows if not r[t]]
        if len(yes) < 10:
            print(f"  {t:>18}: present n={len(yes)} (too few)")
            continue
        print(f"  {t:>18}: present {statistics.mean(r['score'] for r in yes):.3f} "
              f"(n={len(yes)}) | absent {statistics.mean(r['score'] for r in no):.3f} "
              f"(n={len(no)})")

    print("\nGM only, achieved census:")
    for c in (0, 1, 2):
        rs = [r for r in rows if r["corpus"] == "gm"
              and (r["achieved"] == c if c < 2 else r["achieved"] >= 2)]
        if len(rs) >= 3:
            print(f"  {('2+' if c == 2 else c)}: n={len(rs)}, "
                  f"score {statistics.mean(r['score'] for r in rs):.3f}")
