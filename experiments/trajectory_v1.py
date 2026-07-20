"""Positional trajectory extractor v1 — plans, not events.

Fixes over v0, both diagnosed from v0's own first output:
  QUIESCENCE   sample only quiet plies (no capture/check just played or
               answered) so mid-exchange material spikes never enter a series
  DRIFT        plans are slopes over windows, not single-ply jumps — detect
               sustained per-term trends via rolling mean-difference, then
               merge into episodes with a minimum span and net change

Output: episodes.jsonl — one row per detected plan episode, carrying the term,
side, span, net change, the moves over the span, and the start FEN. These feed
the HUMAN AUDIT ("is this span one coherent thing?"), which gates clustering,
which gates naming, which gates the plan classifier NN.

Run:  ./.venv/bin/python experiments/trajectory_v1.py --max-games 300
"""
from __future__ import annotations

import argparse
import json
import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/engine/python")
from lucena_engine import positional  # noqa: E402
from lucena_engine.board import Board as LBoard  # noqa: E402

TERMS = ["material", "king_safety", "activity", "pawns", "center"]
EXTRA = ["w_attack", "b_attack"]          # attack units on each king — v0's best channel

WINDOW = 5          # quiet samples per trend window
SLOPE_MIN = 4.0     # cp per quiet sample to count as trending
NET_MIN = 45        # minimum net change over an episode (cp)
LEN_MIN = 6         # minimum quiet samples in an episode


def is_carlsbad(b: chess.Board) -> bool:
    wp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.WHITE)}
    bp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.BLACK)}
    return ("d4" in wp and not any(sq[0] == "c" for sq in wp)
            and "c6" in bp and "d5" in bp and not any(sq[0] == "e" for sq in bp))


def term_vector(fen: str) -> dict:
    d = positional.analyze_positional(LBoard(fen))
    v = {t: d["terms"][t]["cp"] for t in TERMS}
    ks = d["terms"]["king_safety"]["features"]
    v["w_attack"] = ks["black"]["attack_units"]   # White's attack on the black king
    v["b_attack"] = ks["white"]["attack_units"]
    return v


def quiet_samples(game) -> tuple[list[dict], list[int], list[str], str] | None:
    """Walk the game; return term samples at QUIET plies inside the Carlsbad span."""
    b = game.board()
    samples, plies, sans = [], [], []
    all_sans = []
    carlsbad_seen = 0
    prev_forcing = True                       # skip the very first position
    for i, mv in enumerate(game.mainline_moves()):
        san = b.san(mv)
        forcing = b.is_capture(mv) or b.gives_check(mv)
        b.push(mv)
        all_sans.append(san)
        in_struct = is_carlsbad(b)
        carlsbad_seen += in_struct
        # quiet = neither this move nor the previous was capture/check
        if in_struct and not forcing and not prev_forcing:
            samples.append(term_vector(b.fen()))
            plies.append(i)
            sans.append(san)
        prev_forcing = forcing
    if carlsbad_seen < 10 or len(samples) < LEN_MIN + WINDOW:
        return None
    url = game.headers.get("LichessURL") or game.headers.get("Site", "")
    return samples, plies, all_sans, url


def drift_episodes(samples: list[dict]) -> list[dict]:
    """Rolling-trend detection per term; merge sustained same-sign trends."""
    episodes = []
    for term in TERMS + EXTRA:
        series = [s[term] for s in samples]
        trends = []                            # +1 / -1 / 0 per index
        for k in range(len(series)):
            lo = max(0, k - WINDOW)
            if k - lo < 2:
                trends.append(0)
                continue
            slope = (series[k] - series[lo]) / (k - lo)
            trends.append(1 if slope >= SLOPE_MIN else (-1 if slope <= -SLOPE_MIN else 0))
        # maximal same-sign runs (tolerate single-sample dropouts)
        k = 0
        while k < len(trends):
            if trends[k] == 0:
                k += 1
                continue
            sign, start = trends[k], k
            end = k
            gap = 0
            while end + 1 < len(trends) and gap <= 1:
                if trends[end + 1] == sign:
                    end += 1
                    gap = 0
                elif trends[end + 1] == 0:
                    end += 1
                    gap += 1
                else:
                    break
            net = series[end] - series[max(0, start - WINDOW)]
            if end - start + 1 >= LEN_MIN and abs(net) >= NET_MIN and net * sign > 0:
                episodes.append({"term": term, "sign": sign,
                                 "i0": max(0, start - WINDOW), "i1": end,
                                 "net": int(net)})
            k = end + 1
    return episodes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", default="experiments/data/lichess_elite_2023-01.pgn")
    ap.add_argument("--max-games", type=int, default=300)
    ap.add_argument("--out", default="experiments/episodes.jsonl")
    args = ap.parse_args()

    found = scanned = 0
    with open(args.pgn) as f, open(args.out, "w") as out:
        while found < args.max_games:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            scanned += 1
            q = quiet_samples(game)
            if q is None:
                continue
            samples, plies, all_sans, site = q
            eps = drift_episodes(samples)
            if not eps:
                continue
            found += 1
            # reconstruct start FEN per episode
            b = game.board()
            fens = []
            for mv in game.mainline_moves():
                b.push(mv)
                fens.append(b.fen())
            for e in eps:
                p0, p1 = plies[e["i0"]], plies[e["i1"]]
                out.write(json.dumps({
                    "site": site, "term": e["term"],
                    "dir": "+" if e["sign"] > 0 else "-",
                    "net": e["net"], "ply0": p0, "ply1": p1,
                    "moves": " ".join(all_sans[p0:p1 + 1]),
                    "fen0": fens[p0 - 1] if p0 > 0 else game.board().fen(),
                }, separators=(",", ":")) + "\n")
            if found % 50 == 0:
                print(f"{found} games with episodes / {scanned} scanned", flush=True)
    print(f"DONE: {found} games, scanned {scanned}", flush=True)


if __name__ == "__main__":
    main()
