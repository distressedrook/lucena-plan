"""king_safety_outcome — efficacy tests 1 + 3 for the king-safety danger
score (2026-07-23; the activity_outcome_phase instrument applied to
lucena_core.positional._king_safety_term's per-side `danger`).

TEST 1  OUTCOME DOSE-RESPONSE, phase-bucketed (real classifier +
        hysteresis): per game, the danger DIFFERENTIAL (black - white:
        positive = Black's king worse = good for White) averaged within
        each phase, vs White's score — Pearson r + decile curve.

TEST 3  COLLAPSE PREDICTION, ANCHORED: per game-side, does the danger
        reading predict the king falling WITHIN 20 PLIES OF THE READING?
        (First smoke run's "any -3 window anywhere in the game" fired on
        87%% of sides — endgame conversions and promotion races swing
        material constantly; unanchored windows measure who eventually
        loses, not whether the danger score warns.) Collapse at anchor p
        := the side is mated by p+20, or its RELATIVE material (own minus
        enemy, pawn=1 N/B=3 R=5 Q=9; even trades don't move it) drops >=
        3 points from p to p+20. Anchor = the ply of the side's PEAK
        danger reading; report P(collapse | peak bucket) — the
        calibration the coach's "in danger" sentence rests on — plus the
        warning stat: P(collapse within 20 plies of the FIRST >=100
        reading).

One corpus pass feeds both. Output: printed tables +
research/experiments/reports/king_safety_outcome.png.
Run: .venv/python research/experiments/studies/king_safety_outcome.py [--games N]
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core.board import Board as LBoard
from lucena_core import positional
from lucena_core.reads import game_phase

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
OUT = ("/Users/avismara/Development/lucena/lucena-plans/research/experiments/"
       "reports/king_safety_outcome.png")
PHASES = ("opening", "middlegame", "endgame")
RANK = {p: i for i, p in enumerate(PHASES)}
SAMPLE_MAX = 80
STEP = 2
COLLAPSE_WIN = 20
COLLAPSE_PTS = 3
WORKERS = 8
WSCORE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}
PTS = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5,
       chess.QUEEN: 9}
BUCKETS = ((0, 40, "<40"), (40, 100, "40-99"), (100, 10 ** 9, ">=100"))


def _mat(b, color):
    return sum(v * len(b.pieces(pt, color)) for pt, v in PTS.items())


def chunk(offsets):
    rows = []
    with open(PGN, encoding="latin-1") as f:
        for off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                result = game.headers.get("Result", "*")
                if result not in WSCORE:
                    continue
                b = game.board()
                reldiff = {"white": [], "black": []}   # per ply, own - enemy
                danger = {"white": {}, "black": {}}    # sampled ply -> danger
                dsum = {p: [0.0, 0] for p in PHASES}
                rank = 0
                mated = None
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    w, blk = _mat(b, chess.WHITE), _mat(b, chess.BLACK)
                    reldiff["white"].append(w - blk)
                    reldiff["black"].append(blk - w)
                    if ply >= 8 and ply <= SAMPLE_MAX and not ply % STEP:
                        fen = b.fen()
                        d = positional.analyze_positional(LBoard(fen))
                        ft = d["terms"]["king_safety"]["features"]
                        if "white" in ft and "black" in ft:
                            dw = ft["white"]["danger"]
                            db = ft["black"]["danger"]
                            danger["white"][ply] = dw
                            danger["black"][ply] = db
                            rank = max(rank, RANK[game_phase(fen)["phase"]])
                            s = dsum[PHASES[rank]]
                            s[0] += db - dw
                            s[1] += 1
                if b.is_checkmate():
                    mated = "white" if b.turn == chess.WHITE else "black"
                row = {"score": WSCORE[result]}
                for p, (s, n) in dsum.items():
                    row[p] = s / n if n else None
                # collapse per side, ANCHORED at a reading ply p: mated by
                # p+COLLAPSE_WIN, or relative material drops >= COLLAPSE_PTS
                # from p to p+COLLAPSE_WIN
                def _collapses_at(side, p):
                    rd = reldiff[side]
                    end = min(p - 1 + COLLAPSE_WIN, len(rd) - 1)
                    if mated == side and len(rd) <= p + COLLAPSE_WIN:
                        return True
                    return rd[end] - rd[p - 1] <= -COLLAPSE_PTS

                row["sides"] = {}
                for side in ("white", "black"):
                    peaks = danger[side]
                    if not peaks:
                        continue
                    peak = max(peaks.values())
                    pply = min(p for p, v in peaks.items() if v == peak)
                    first100 = min((p for p, v in peaks.items() if v >= 100),
                                   default=None)
                    row["sides"][side] = {
                        "peak": peak,
                        "collapsed": _collapses_at(side, pply),
                        "warned": (_collapses_at(side, first100)
                                   if first100 is not None else None),
                    }
                rows.append(row)
            except Exception:
                continue
    return rows


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else 0.0


def main(max_games):
    offsets = []
    with open(PGN, encoding="latin-1") as f:
        while True:
            off = f.tell()
            line = f.readline()
            if not line:
                break
            if line.startswith("[Event "):
                offsets.append(off)
                if max_games and len(offsets) >= max_games:
                    break
    chunks = [offsets[i::WORKERS] for i in range(WORKERS)]
    rows = []
    with Pool(WORKERS) as pool:
        for part in pool.imap_unordered(chunk, chunks):
            rows.extend(part)
    print(f"games scored: {len(rows)}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(PHASES) + 1, figsize=(20, 5))

    # ---- TEST 1: dose-response per phase
    for ax, phase in zip(axes, PHASES):
        pts = [(r[phase], r["score"]) for r in rows if r[phase] is not None]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = pearson(xs, ys)
        print(f"\n== TEST 1 · {phase} (n={len(pts)}) ==")
        print(f"  Pearson r(danger diff B-W, White score) = {r:+.3f}")
        order = sorted(pts)
        dec = len(order) // 10
        centers, means = [], []
        for i in range(10):
            seg = order[i * dec:(i + 1) * dec] if i < 9 else order[9 * dec:]
            m = sum(p[1] for p in seg) / len(seg)
            centers.append(sum(p[0] for p in seg) / len(seg))
            means.append(m)
            print(f"    decile {i}  [{seg[0][0]:+7.1f} .. {seg[-1][0]:+7.1f}]"
                  f"   {m:.3f}")
        ax.plot(centers, means, marker="o")
        ax.axhline(0.5, color="gray", lw=0.8, ls="--")
        ax.axvline(0.0, color="gray", lw=0.8, ls="--")
        ax.set_title(f"{phase}\nr = {r:+.3f}")
        ax.set_xlabel("danger diff (B - W)")
    axes[0].set_ylabel("mean White score")

    # ---- TEST 3: collapse by peak-danger bucket
    print(f"\n== TEST 3 · COLLAPSE (mate or >= {COLLAPSE_PTS} pts relative "
          f"loss in {COLLAPSE_WIN} plies) ==")
    names, rates = [], []
    for lo, hi, label in BUCKETS:
        sel = [s for r in rows for s in r["sides"].values()
               if lo <= s["peak"] < hi]
        if not sel:
            continue
        rate = sum(s["collapsed"] for s in sel) / len(sel)
        names.append(label)
        rates.append(rate)
        print(f"  peak danger {label:>6}: collapse {rate:.1%}  (n={len(sel)})")
    warned = [s["warned"] for r in rows for s in r["sides"].values()
              if s["warned"] is not None]
    if warned:
        print(f"  first >=100 reading -> collapse within {COLLAPSE_WIN} "
              f"plies of THAT reading: "
              f"{sum(warned) / len(warned):.1%} (n={len(warned)})")
    ax = axes[-1]
    ax.bar(names, [r * 100 for r in rates], color="#1E4E7A")
    ax.set_title("P(collapse) by peak danger")
    ax.set_ylabel("%")
    fig.suptitle(f"king-safety danger efficacy (GM corpus, {len(rows)} games)")
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print(f"\nplot -> {OUT}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
