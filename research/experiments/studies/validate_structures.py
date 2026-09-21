"""Corpus validation of structures.py: for each structure, how many GM games
hold it >= MIN_PLIES, the owner's score, and the ECO fingerprint (top-5).
A wrong definition shows up immediately as a wrong ECO list."""
from __future__ import annotations

import collections
import statistics
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-plans/src")
from structures import classify

MIN_PLIES = 10

if __name__ == "__main__":
    stats = collections.defaultdict(lambda: {"n": 0, "scores": [],
                                             "ecos": collections.Counter()})
    n = 0
    with open("/Users/avismara/Projects/active/lucena/lucena-plans/research/data/gm_classical.pgn",
              encoding="latin-1") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            n += 1
            if n % 5000 == 0:
                print(f"scanned {n}", flush=True)
            res = game.headers.get("Result", "*")
            if res not in ("1-0", "0-1", "1/2-1/2"):
                continue
            sw = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[res]
            eco = game.headers.get("ECO", "?")
            counts = collections.Counter()
            b = game.board()
            try:
                for mv in game.mainline_moves():
                    b.push(mv)
                    for key in classify(b):
                        counts[key] += 1
            except Exception:
                continue
            for (name, owner), c in counts.items():
                if c < MIN_PLIES:
                    continue
                s = stats[(name, "W" if owner else "B")]
                s["n"] += 1
                s["scores"].append(sw if owner == chess.WHITE else 1.0 - sw)
                s["ecos"][eco] += 1

    print(f"\n{'structure':>18} {'owner':>5} | {'games':>6} | {'freq':>6} | "
          f"{'owner score':>11} | top ECOs")
    for (name, owner), s in sorted(stats.items(), key=lambda kv: -kv[1]["n"]):
        ecos = " ".join(f"{e}:{k}" for e, k in s["ecos"].most_common(5))
        print(f"{name:>18} {owner:>5} | {s['n']:>6} | {100*s['n']/n:>5.2f}% | "
              f"{statistics.mean(s['scores']):>11.3f} | {ecos}")
