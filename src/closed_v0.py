"""Closed-position detector, v0 — pure pawn-skeleton geometry.

closedness ingredients per position:
  rams          — pawn pairs directly blocking each other (Kmoch)
  central rams  — rams on files c..f (the ones that seal plans in)
  tension       — pawn pairs where one can capture the other (openable!)
  open files    — files with no pawns of either color

CLOSED predicate: >= 2 central rams, >= 4 total rams, tension <= 1, no open
file. A game "goes closed" when the predicate holds PERSIST consecutive plies.

Sanity check: detected games should be dominated by King's Indian / French /
advance-structure ECO codes, with an elevated draw rate NOT expected (closed
middlegames are fighting chess — the check is structural, via ECO).
"""
from __future__ import annotations

import collections

import chess
import chess.pgn

PERSIST = 12
CENTRAL_FILES = {2, 3, 4, 5}


def skeleton(b: chess.Board):
    wp = b.pieces(chess.PAWN, chess.WHITE)
    bp = b.pieces(chess.PAWN, chess.BLACK)
    rams = central = tension = 0
    for sq in wp:
        if sq + 8 < 64 and (sq + 8) in bp:
            rams += 1
            if chess.square_file(sq) in CENTRAL_FILES:
                central += 1
        f, r = chess.square_file(sq), chess.square_rank(sq)
        for df in (-1, 1):
            if 0 <= f + df <= 7 and r + 1 <= 7:
                if chess.square(f + df, r + 1) in bp:
                    tension += 1
    files_with_pawns = {chess.square_file(s) for s in wp} | \
                       {chess.square_file(s) for s in bp}
    open_files = 8 - len(files_with_pawns)
    return rams, central, tension, open_files


def center_locked(b: chess.Board) -> bool:
    """Moved verbatim to lucena-core (2026-07-23 consolidation) —
    re-exported for the KEEP_KING_UNCASTLED trigger and callers."""
    from lucena_core.geometry import center_locked as _cl
    return _cl(b)


def is_closed(b: chess.Board) -> bool:
    rams, central, tension, open_files = skeleton(b)
    return central >= 2 and rams >= 4 and tension <= 1 and open_files == 0


def detect_closed(game):
    """Returns (onset_ply, plies_closed_total) or None."""
    b = game.board()
    run = 0
    onset = None
    total = 0
    n = 0
    for i, mv in enumerate(game.mainline_moves()):
        b.push(mv)
        n = i + 1
        if is_closed(b):
            run += 1
            total += 1
            if run == PERSIST and onset is None:
                onset = i - PERSIST + 1
        else:
            run = 0
    if onset is None:
        return None
    return {"onset": onset, "plies_closed": total, "game_plies": n}


if __name__ == "__main__":
    import statistics
    n = hits = 0
    onsets, ecos, results = [], collections.Counter(), collections.Counter()
    open_results = collections.Counter()
    samples = []
    with open("/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn",
              encoding="latin-1") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            n += 1
            if n % 10000 == 0:
                print(f"scanned {n}, closed {hits}", flush=True)
            try:
                det = detect_closed(game)
            except Exception:
                continue
            res = game.headers.get("Result", "*")
            if det is None:
                open_results[res] += 1
                continue
            hits += 1
            onsets.append(det["onset"])
            ecos[game.headers.get("ECO", "?")] += 1
            results[res] += 1
            if len(samples) < 8:
                samples.append(f'{game.headers.get("White","?")} - '
                               f'{game.headers.get("Black","?")} '
                               f'({game.headers.get("ECO","?")}) onset ply {det["onset"]}')
    print(f"\nclosed games: {hits}/{n} ({100*hits/n:.1f}%), "
          f"median onset ply {statistics.median(onsets):.0f}")
    print(f"closed results: {dict(results)}")
    print(f"other results:  {dict(open_results)}")
    dr_c = results["1/2-1/2"] / max(1, sum(results.values()))
    dr_o = open_results["1/2-1/2"] / max(1, sum(open_results.values()))
    print(f"draw rate closed {100*dr_c:.1f}% vs rest {100*dr_o:.1f}%")
    print("\ntop ECO codes in closed games:")
    for eco, k in ecos.most_common(12):
        print(f"  {eco}: {k}")
    print("\nsamples:")
    for s in samples:
        print(" ", s)
