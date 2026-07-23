"""attack_viability_validation — does the PROSPECTIVE attack-viability
score (lucena_core.positional.attack_viability, 2026-07-23) actually
predict the attack infrastructure getting BUILT?

The claim under test: at a position where the enemy king is NOT yet in
danger (danger < 100 — nothing built), a high viability score for the
attacker predicts the danger term firing within the next 20 plies (the
infrastructure arrives), and downstream, the defender collapsing (mate or
>= 3 pts relative material loss within 30 plies).

Anchors: sampled plies 8..60 step 4, per attacking side, enemy danger
< 100 at anchor (hindsight-free: the score sees only the anchor position).
Buckets by viability norm. Random floor is implicit in the low buckets.

Output: printed table + research/experiments/reports/attack_viability_validation.png
Run: .venv/python research/experiments/studies/attack_viability_validation.py [--games N]
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core.board import Board as LBoard
from lucena_core import positional

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
OUT = ("/Users/avismara/Development/lucena/lucena-plans/research/experiments/"
       "reports/attack_viability_validation.png")
ANCHOR_MAX = 60
STEP = 4
DANGER_WIN = 20
COLLAPSE_WIN = 30
COLLAPSE_PTS = 3
WORKERS = 8
PTS = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5,
       chess.QUEEN: 9}
BUCKETS = ((0.0, 0.15), (0.15, 0.3), (0.3, 0.45), (0.45, 1.01))


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
                if game.headers.get("Result", "*") not in ("1-0", "0-1",
                                                           "1/2-1/2"):
                    continue
                b = game.board()
                per_ply = []      # (danger_w, danger_b, relW, relB) per ply
                via = {}          # anchor ply -> (viaW, viaB)
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    w, blk = _mat(b, chess.WHITE), _mat(b, chess.BLACK)
                    fen = b.fen()
                    d = positional.analyze_positional(LBoard(fen))
                    ft = d["terms"]["king_safety"]["features"]
                    dw = ft.get("white", {}).get("danger", 0)
                    db = ft.get("black", {}).get("danger", 0)
                    per_ply.append((dw, db, w - blk, blk - w))
                    if 8 <= ply <= ANCHOR_MAX and not ply % STEP:
                        v = positional.attack_viability(fen)
                        via[ply] = (v["white"]["norm"], v["black"]["norm"])
                    if ply > ANCHOR_MAX + max(DANGER_WIN, COLLAPSE_WIN):
                        break
                mated = ("white" if b.turn == chess.WHITE else "black") \
                    if b.is_checkmate() else None
                for p, (vw, vb) in via.items():
                    for atk, vnorm, di, ri in (("white", vw, 1, 3),
                                               ("black", vb, 0, 2)):
                        # enemy danger index di, enemy rel-material index ri
                        if per_ply[p - 1][di] >= 100:
                            continue          # already built — not viability
                        end_d = min(p + DANGER_WIN, len(per_ply))
                        built = any(per_ply[t][di] >= 100
                                    for t in range(p, end_d))
                        end_c = min(p - 1 + COLLAPSE_WIN, len(per_ply) - 1)
                        defender = "black" if atk == "white" else "white"
                        collapsed = (per_ply[end_c][ri] - per_ply[p - 1][ri]
                                     <= -COLLAPSE_PTS) or \
                            (mated == defender
                             and len(per_ply) <= p + COLLAPSE_WIN)
                        rows.append((vnorm, built, collapsed))
            except Exception:
                continue
    return rows


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
    print(f"anchors (enemy danger < 100): {len(rows)}")

    print(f"\n  viability      P(danger>=100     P(defender collapses"
          f"\n  bucket          in {DANGER_WIN} plies)      in {COLLAPSE_WIN} plies)")
    names, built_r, coll_r = [], [], []
    for lo, hi in BUCKETS:
        sel = [r for r in rows if lo <= r[0] < hi]
        if not sel:
            continue
        pb = sum(r[1] for r in sel) / len(sel)
        pc = sum(r[2] for r in sel) / len(sel)
        label = f"{lo:.2f}-{hi:.2f}"
        names.append(label)
        built_r.append(pb)
        coll_r.append(pc)
        print(f"  {label:>9}       {pb:6.1%}            {pc:6.1%}"
              f"        (n={len(sel)})")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, vals, title in ((axes[0], built_r,
                             f"P(danger >= 100 within {DANGER_WIN} plies)"),
                            (axes[1], coll_r,
                             f"P(defender collapses within {COLLAPSE_WIN} plies)")):
        ax.bar(names, [v * 100 for v in vals], color="#1E4E7A")
        ax.set_title(title)
        ax.set_xlabel("attack-viability norm bucket")
        ax.set_ylabel("%")
    fig.suptitle(f"attack viability -> infrastructure built (GM corpus, "
                 f"{len(rows)} anchors)")
    fig.tight_layout()
    fig.savefig(OUT, dpi=110)
    print(f"\nplot -> {OUT}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
