"""activity_calibration2 — the second-generation activity calibration
(2026-07-23 owner rulings):

  A. PHASE-CONDITIONED percentile grids: a middlegame rook is judged
     against middlegame rooks ("rooks and queens always lose in the
     middlegame" — the flat grids pooled endgame rooks, which own the
     distribution's top, so no middlegame rook could score well).
  B. SIDE-CONDITIONED development baselines, plies 8-20: mean norm per
     (side, type, ply). Black trails White by a tempo BY CONSTRUCTION, so
     development lag must judge Black against the Black baseline or every
     Black position "lags".

Emits both tables as python literals for embedding in positional.py.
Run: .venv/python research/experiments/studies/activity_calibration2.py [--games N]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-core/python")
from lucena_core.board import Board as LBoard
from lucena_core import positional
from lucena_core.reads import game_phase

PGN = "/Users/avismara/Projects/active/lucena/lucena-plans/research/data/gm_classical.pgn"
START_PLY = 8
EVERY = 4
MAX_PLY = 100
BASE_MAX_PLY = 20
WORKERS = 8
QSTEP = 5
RANK = {"opening": 0, "middlegame": 1, "endgame": 2}
PHASES = ("opening", "middlegame", "endgame")


def chunk(offsets):
    scores = defaultdict(list)           # (phase, type) -> raw scores
    base = defaultdict(lambda: [0.0, 0])  # (side, type, ply) -> [sum_raw, n]
    with open(PGN, encoding="latin-1") as f:
        for off in offsets:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                b = game.board()
                rank = 0
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    if ply > MAX_PLY:
                        break
                    dev_ply = START_PLY <= ply <= BASE_MAX_PLY
                    if ply < START_PLY or ((ply - START_PLY) % EVERY
                                           and not dev_ply):
                        continue
                    fen = b.fen()
                    rank = max(rank, RANK[game_phase(fen)["phase"]])
                    phase = PHASES[rank]
                    d = positional.analyze_positional(LBoard(fen))
                    ft = d["terms"]["activity"]["features"]
                    for color in ("white", "black"):
                        for e in ft.get(f"pieces_{color}", []):
                            if not ((ply - START_PLY) % EVERY):
                                scores[(phase, e["piece"])].append(e["score"])
                            if dev_ply:
                                c = base[(color, e["piece"], ply)]
                                c[0] += e["score"]
                                c[1] += 1
            except Exception:
                continue
    return dict(scores), {k: tuple(v) for k, v in base.items()}


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
    scores = defaultdict(list)
    base = defaultdict(lambda: [0.0, 0])
    with Pool(WORKERS) as pool:
        for sc, bs in pool.imap_unordered(chunk, chunks):
            for k, v in sc.items():
                scores[k].extend(v)
            for k, (s, n) in bs.items():
                base[k][0] += s
                base[k][1] += n

    print(f"# {len(offsets)} games; observations per (phase,type):")
    print("#", {f"{p}:{t}": len(scores[(p, t)])
                for p in PHASES for t in "NBRQ" if (p, t) in scores})
    print("_ACT_QUANTILES = {")
    for phase in PHASES:
        print(f'    "{phase}": {{')
        for pc in ("N", "B", "R", "Q"):
            v = sorted(scores.get((phase, pc), []))
            if not v:
                continue
            qs = [v[min(len(v) - 1, round(q / 100 * (len(v) - 1)))]
                  for q in range(0, 101, QSTEP)]
            print(f'        "{pc}": {[round(x, 1) for x in qs]},')
        print("    },")
    print("}")
    print("# development baseline: RAW mean activity score per (side, type,")
    print("# ply), plies 8-20 — lag is computed against the SAME side's curve")
    print("_DEV_BASELINE = {")
    for side in ("white", "black"):
        print(f'    "{side}": {{')
        for pc in ("N", "B", "R", "Q"):
            row = {}
            for ply in range(START_PLY, BASE_MAX_PLY + 1):
                s, n = base.get((side, pc, ply), (0.0, 0))
                if n:
                    row[ply] = round(s / n, 1)
            print(f'        "{pc}": {row},')
        print("    },")
    print("}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
