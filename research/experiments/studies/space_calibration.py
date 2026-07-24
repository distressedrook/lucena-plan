"""space_calibration — percentile grids for the per-region space score
(2026-07-23 owner ruling: "normalize the space scores. Black and White
needn't add up to one. Both sides may not have any space. 1, 2 means
nothing.").

Space is TERRITORY, not a share — each side's regional space is an
independent count, so it gets an independent 0-1 percentile (unlike the
control shares, which are zero-sum by construction). Distributions are
color-symmetric (White's kingside space ~ Black's kingside space), so each
region pools BOTH sides (Black mirrored trivially — the count already uses
side-relative ranks). Middlegame samples only (real phase classifier +
hysteresis); space in the opening is just the pawns not yet moved.

Emits _SPACE_QUANTILES for embedding in metrics.py.
Run: .venv/python research/experiments/studies/space_calibration.py [--games N]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core import metrics as met
from lucena_core.reads import game_phase

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
RANK = {"opening": 0, "middlegame": 1, "endgame": 2}
MAX_PLY = 80
STEP = 4
WORKERS = 8
QSTEP = 5
REGIONS = ("queenside", "center", "kingside")


def chunk(offsets):
    vals = defaultdict(list)
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
                    if ply < 8 or ply % STEP:
                        continue
                    rank = max(rank, RANK[game_phase(b.fen())["phase"]])
                    if rank != 1:
                        continue
                    sp = met.space_report(b.fen())
                    for region in REGIONS:
                        vals[region].append(sp[region]["white"]["raw"])
                        vals[region].append(sp[region]["black"]["raw"])
            except Exception:
                continue
    return dict(vals)


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
    merged = defaultdict(list)
    with Pool(WORKERS) as pool:
        for part in pool.imap_unordered(chunk, chunks):
            for k, v in part.items():
                merged[k].extend(v)
    print(f"# {len(offsets)} games; { {k: len(v) for k, v in merged.items()} }")
    # discrete, tie-heavy (space is small ints, mostly 0) -> emit the
    # empirical CDF as a value->MIDRANK-percentile map (fraction strictly
    # below + half the ties): a raw count maps to "more space than X% of
    # GM regional-space observations", ties handled honestly.
    print("_SPACE_CDF = {")
    for region in REGIONS:
        v = sorted(merged[region])
        n = len(v)
        from collections import Counter
        cnt = Counter(v)
        cum = 0
        row = {}
        for val in sorted(cnt):
            below = cum
            row[val] = round((below + cnt[val] / 2) / n, 3)
            cum += cnt[val]
        print(f'    "{region}": {row},')
    print("}")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
