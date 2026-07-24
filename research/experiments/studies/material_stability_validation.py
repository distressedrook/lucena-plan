"""material_stability_validation — does a 'soft' material edge actually
decay? (2026-07-23.) At anchors where one side is up >= ~a pawn of static
material, does material_stability.soft predict the edge SHRINKING over the
next 12 plies, vs a 'stable' edge holding?

Prediction: soft edges regress toward parity; stable edges persist.
Anchor: plies 8-70 step 3, |raw material| in [100, 400] (edge, not a rout).
Measure: |material| now vs |material| 12 plies later, from the leader's POV
(signed toward the leader — negative = the edge shrank).
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core.metrics import material_stability, _static_material

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
STEP = 3
HORIZON = 12
WORKERS = 8


def chunk(offsets):
    rows = []
    with open(PGN, encoding="latin-1") as f:
        for off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                moves = list(game.mainline_moves())
                b = game.board()
                boards = [b.copy()]
                for mv in moves:
                    b.push(mv)
                    boards.append(b.copy())
                for i in range(8, min(len(boards), 71), STEP):
                    if i + HORIZON >= len(boards):
                        break
                    bi = boards[i]
                    raw = _static_material(bi)
                    if not (100 <= abs(raw) <= 400):
                        continue
                    ms = material_stability(bi.fen())
                    if ms["leader"] is None:
                        continue
                    sign = 1 if ms["leader"] == "White" else -1
                    later = _static_material(boards[i + HORIZON]) * sign
                    now = raw * sign
                    rows.append((ms["soft"], now, later))
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
    print(f"anchors (leader up 100-400cp static): {len(rows)}\n")
    for label, sel in (("SOFT edge", [r for r in rows if r[0]]),
                       ("STABLE edge", [r for r in rows if not r[0]])):
        if not sel:
            continue
        now = sum(r[1] for r in sel) / len(sel)
        later = sum(r[2] for r in sel) / len(sel)
        held = sum(1 for r in sel if r[2] >= r[1] - 50) / len(sel)
        gone = sum(1 for r in sel if r[2] <= 40) / len(sel)
        print(f"  {label:<12} n={len(sel):>6}  edge now {now:+.0f}cp -> "
              f"+{HORIZON}p {later:+.0f}cp  (held {held:.0%}, "
              f"gone-to-parity {gone:.0%})")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
