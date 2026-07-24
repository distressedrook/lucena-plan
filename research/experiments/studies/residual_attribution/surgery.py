#!/usr/bin/env python3
"""Residual-attribution study, stage 4: interventional faithfulness.

For a feature class, build minimal counterfactual boards (surgery), label
both versions with fresh fixed-node Stockfish, and compare the ENGINE's
delta to the MODEL's claimed delta. This is the gold-standard test that
an attribution is causal, not correlational. v0 surgeries:

  bishop_pair   the pair-holder's non-worse bishop becomes a knight on
                the same square (pair flag flips; count material ~even)
  passer        an enemy pawn from an adjacent file shifts onto the
                passer's file ahead of it (un-passes it; material even)

Both surgeries require the position AND its counterfactual to be quiet
(no pending SEE>0 grab, no check) so the engine delta prices the concept,
not a tactic the surgery created.
"""
from __future__ import annotations

import json
import os
import random

import chess
import chess.engine
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

import harvest_features as HF
from model_residual import FEATURES, load, group_split, fit_speaker

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "surgery_report.json")
STOCKFISH = "/opt/homebrew/bin/stockfish"
NODES = 200_000
N_PER_CLASS = 80


def surgery_bishop_pair(b: chess.Board) -> chess.Board | None:
    for color in (chess.WHITE, chess.BLACK):
        bs = list(b.pieces(chess.BISHOP, color))
        if len(bs) >= 2 and len(b.pieces(chess.BISHOP, not color)) < 2:
            b2 = b.copy(stack=False)
            sq = sorted(bs)[0]
            b2.set_piece_at(sq, chess.Piece(chess.KNIGHT, color))
            return b2
    return None


def surgery_unpass(b: chess.Board) -> chess.Board | None:
    """Un-pass a passer by importing an enemy pawn from a DISTANT file
    (>=2 files away — by definition no enemy pawn lives near a passer)
    onto the passer's file, two+ ranks ahead. Material-even; perturbs the
    donor file too, which is why the comparison is whole-model delta."""
    from lucena_core.geometry import passers
    for color in (chess.WHITE, chess.BLACK):
        enemy = not color
        for p in sorted(passers(b, color)):
            f, r = chess.square_file(p), chess.square_rank(p)
            ahead = (range(r + 2, 7) if color == chess.WHITE
                     else range(1, r - 1))
            for ep in sorted(b.pieces(chess.PAWN, enemy)):
                if abs(chess.square_file(ep) - f) < 2:
                    continue
                for er in ahead:
                    tgt = chess.square(f, er)
                    if b.piece_at(tgt) is not None:
                        continue
                    b2 = b.copy(stack=False)
                    b2.remove_piece_at(ep)
                    b2.set_piece_at(tgt, chess.Piece(chess.PAWN, enemy))
                    return b2
    return None


SURGERIES = {"bishop_pair": surgery_bishop_pair, "passer": surgery_unpass}


def ok(b: chess.Board) -> bool:
    if not b.is_valid():
        return False
    return HF.quietness(b)


def main():
    rows, X, y, quiet, phase, seeds = load()
    tr, te = group_split(seeds)
    speaker = fit_speaker(X[tr], y[tr])

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": 4, "Hash": 256})

    def label(b):
        info = engine.analyse(b, chess.engine.Limit(nodes=NODES))
        return info["score"].white().score(mate_score=10_000)

    rng = random.Random(29)
    idx = [i for i in np.where(te)[0] if rows[i]["quiet"]]
    rng.shuffle(idx)

    report = {}
    try:
        for name, surg in SURGERIES.items():
            eng_d, mod_d = [], []
            for i in idx:
                if len(eng_d) >= N_PER_CLASS:
                    break
                b = chess.Board(rows[i]["fen"])
                b.halfmove_clock = 0
                b2 = surg(b)
                if b2 is None or not ok(b2):
                    continue
                fv2 = HF.features(b2.fen())
                if fv2 is None:
                    continue
                e0, e1 = label(b), label(b2)
                if e0 is None or e1 is None or \
                        max(abs(e0), abs(e1)) > 500:
                    continue
                x0 = np.array([[rows[i]["feats"][f] for f in FEATURES]])
                x1 = np.array([[fv2[f] for f in FEATURES]])
                # engine delta vs the model's TOTAL predicted delta —
                # surgery moves neighbors too (activity, complexes), so
                # the honest comparison is whole-model vs engine, plus
                # how much the targeted feature carries.
                eng_d.append(e1 - e0)
                mod_d.append(float(speaker.predict(x1)[0]
                                   - speaker.predict(x0)[0]))
            eng_d, mod_d = np.array(eng_d), np.array(mod_d)
            if len(eng_d) < 15:
                print(f"{name}: only {len(eng_d)} valid surgeries — skip")
                continue
            corr = float(np.corrcoef(eng_d, mod_d)[0, 1]) \
                if eng_d.std() > 0 and mod_d.std() > 0 else float("nan")
            print(f"{name}: n={len(eng_d)}  engine d mean {eng_d.mean():+.1f}"
                  f" (sd {eng_d.std():.0f})  model d mean {mod_d.mean():+.1f}"
                  f" (sd {mod_d.std():.0f})  corr {corr:.2f}")
            report[name] = {
                "n": int(len(eng_d)),
                "engine_mean": round(float(eng_d.mean()), 1),
                "engine_sd": round(float(eng_d.std()), 1),
                "model_mean": round(float(mod_d.mean()), 1),
                "model_sd": round(float(mod_d.std()), 1),
                "corr": round(corr, 3),
            }
    finally:
        engine.quit()
    json.dump(report, open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
