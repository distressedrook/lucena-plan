#!/usr/bin/env python3
"""Residual-attribution study, stage 3: models + faithfulness numbers.

Two models, two jobs (protocol 2026-07-24):
  CEILING  unconstrained GBDT (interactions on) — how much of R the
           feature set can explain at all. Never speaks.
  SPEAKER  additive GBDT (interaction_cst = singletons) with monotone
           constraints (every differential oriented so + favors White) —
           attribution is structural: pred = const + sum_i f_i(x_i),
           and "+20cp from the passer" is literally f_passer(x).

Splits are GROUPED BY SEED (interiors of one seed never straddle
train/test). Reported per bucket: quiet vs tense, and per phase.

Outputs: model_report.json + printed summary + example decompositions.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import numpy as np
from scipy import stats as sstats  # noqa: F401  (spearman via numpy fallback)
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_error

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "dataset.jsonl")
OUT = os.path.join(HERE, "model_report.json")

FEATURES = [
    "stm", "king_safety_cp", "activity_cp", "pawns_cp", "center_cp",
    "king_danger", "king_center", "attack_viability",
    "activity_mean", "passive_pieces",
    "center_share", "kingside_share", "queenside_share",
    "outposts", "open_files_held", "space",
    "passer_count", "passer_best", "passer_running",
    "isolated", "doubled", "islands",
    "weak_complex", "bishop_pair",
    "trapped", "restricted", "breaks_playable",
]


def load():
    rows = [json.loads(l) for l in open(DATA)]
    X = np.array([[r["feats"][f] for f in FEATURES] for r in rows],
                 dtype=np.float64)
    y = np.array([r["r"] for r in rows], dtype=np.float64)
    quiet = np.array([r["quiet"] for r in rows], dtype=bool)
    phase = np.array([r["phase"] for r in rows])
    seeds = np.array([r["seed"] for r in rows])
    return rows, X, y, quiet, phase, seeds


def group_split(seeds, test_frac=0.2, salt=13):
    uniq = sorted(set(seeds))
    rng = np.random.RandomState(salt)
    rng.shuffle(uniq)
    ntest = int(len(uniq) * test_frac)
    test_ids = set(uniq[:ntest])
    te = np.array([s in test_ids for s in seeds])
    return ~te, te


def spearman_clusters(X):
    rk = np.apply_along_axis(lambda c: np.argsort(np.argsort(c)), 0, X)
    C = np.corrcoef(rk.T)
    pairs = []
    for i in range(len(FEATURES)):
        for j in range(i + 1, len(FEATURES)):
            if abs(C[i, j]) >= 0.8:
                pairs.append((FEATURES[i], FEATURES[j], round(C[i, j], 3)))
    return pairs


def fit_ceiling(Xtr, ytr):
    m = HistGradientBoostingRegressor(
        max_iter=500, learning_rate=0.07, max_leaf_nodes=31,
        min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    m.fit(Xtr, ytr)
    return m


def fit_speaker(Xtr, ytr):
    m = HistGradientBoostingRegressor(
        max_iter=500, learning_rate=0.07, max_leaf_nodes=8,
        min_samples_leaf=40, l2_regularization=1.0, random_state=0,
        interaction_cst=[[i] for i in range(len(FEATURES))],
        monotonic_cst=[1] * len(FEATURES))
    m.fit(Xtr, ytr)
    return m


def shape_functions(model, Xtr):
    """Per-feature lookup f_i (centered on the training mean) for the
    additive model, computed exactly: vary one column over its unique
    values with all rows fixed, average predictions. For an additive
    model this recovers g_i up to a constant."""
    base = model.predict(Xtr).mean()
    shapes = []
    ref = Xtr.copy()
    for i in range(Xtr.shape[1]):
        vals = np.unique(Xtr[:, i])
        if len(vals) > 64:
            vals = np.quantile(Xtr[:, i], np.linspace(0, 1, 65))
            vals = np.unique(vals)
        means = []
        sub = ref[np.random.RandomState(1).choice(len(ref),
                                                  min(len(ref), 512),
                                                  replace=False)]
        for v in vals:
            Z = sub.copy()
            Z[:, i] = v
            means.append(model.predict(Z).mean())
        means = np.array(means)
        shapes.append((vals, means - means.mean()))
    return base, shapes


def attribute(shapes, x):
    out = []
    for i, (vals, f) in enumerate(shapes):
        j = np.searchsorted(vals, x[i])
        j = min(max(j, 0), len(vals) - 1)
        out.append(f[j])
    return np.array(out)


def bucket_scores(name, ytest, pred, mask):
    if mask.sum() < 50:
        return None
    return {"bucket": name, "n": int(mask.sum()),
            "r2": round(float(r2_score(ytest[mask], pred[mask])), 3),
            "mae": round(float(mean_absolute_error(ytest[mask],
                                                   pred[mask])), 1),
            "var": round(float(ytest[mask].std()), 1)}


def main():
    rows, X, y, quiet, phase, seeds = load()
    print(f"{len(rows)} rows; R: mean {y.mean():+.1f} sd {y.std():.1f}; "
          f"quiet {quiet.mean():.0%}")

    print("\ncollinear pairs (|spearman| >= 0.8):")
    pairs = spearman_clusters(X)
    for a, b, c in pairs:
        print(f"  {a} ~ {b}: {c}")
    if not pairs:
        print("  none")

    tr, te = group_split(seeds)
    Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]

    report = {"n": len(rows), "collinear": pairs, "buckets": []}

    ceiling = fit_ceiling(Xtr, ytr)
    speaker = fit_speaker(Xtr, ytr)
    ridge = Ridge(alpha=10.0).fit(Xtr, ytr)

    preds = {"ceiling": ceiling.predict(Xte),
             "speaker": speaker.predict(Xte),
             "linear": ridge.predict(Xte)}

    masks = {"all": np.ones(te.sum(), bool),
             "quiet": quiet[te], "tense": ~quiet[te]}
    for ph in ("middlegame", "endgame", "opening"):
        masks[f"quiet+{ph}"] = quiet[te] & (phase[te] == ph)

    print(f"\n{'bucket':<18}{'n':>6} {'sd(R)':>6} | "
          f"{'lin':>6} {'add':>6} {'gbdt':>6}   (held-out R^2)")
    for name, mask in masks.items():
        row = {}
        for mname, p in preds.items():
            s = bucket_scores(name, yte, p, mask)
            if s is None:
                row = None
                break
            row[mname] = s
        if row is None:
            continue
        print(f"{name:<18}{row['ceiling']['n']:>6} "
              f"{row['ceiling']['var']:>6} | "
              f"{row['linear']['r2']:>6} {row['speaker']['r2']:>6} "
              f"{row['ceiling']['r2']:>6}")
        report["buckets"].append({"bucket": name, **{
            m: {k: v for k, v in row[m].items() if k in ("r2", "mae")}
            for m in preds}, "n": row["ceiling"]["n"],
            "sd": row["ceiling"]["var"]})

    # residual-vs-tension: is what we can't explain concentrated where
    # the position is tactically unsettled?
    resid = np.abs(yte - preds["speaker"])
    print(f"\nmean |unexplained R|: quiet {resid[quiet[te]].mean():.1f}  "
          f"tense {resid[~quiet[te]].mean():.1f}")
    report["resid_quiet"] = round(float(resid[quiet[te]].mean()), 1)
    report["resid_tense"] = round(float(resid[~quiet[te]].mean()), 1)

    # ablations on the speaker (quiet bucket): drop feature, refit, dR2
    qm = quiet[te]
    base_r2 = r2_score(yte[qm], preds["speaker"][qm])
    print("\nablations (speaker, quiet bucket, dR2 when dropped):")
    abl = {}
    for i, f in enumerate(FEATURES):
        keep = [j for j in range(len(FEATURES)) if j != i]
        m = HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.07, max_leaf_nodes=8,
            min_samples_leaf=40, l2_regularization=1.0, random_state=0,
            interaction_cst=[[k] for k in range(len(keep))],
            monotonic_cst=[1] * len(keep))
        m.fit(Xtr[:, keep], ytr)
        d = base_r2 - r2_score(yte[qm], m.predict(Xte[:, keep])[qm])
        abl[f] = round(float(d), 4)
    for f, d in sorted(abl.items(), key=lambda kv: -kv[1]):
        print(f"  {f:<18}{d:+.4f}")
    report["ablation_dr2"] = abl

    # additivity + example decompositions on held-out quiet positions
    base, shapes = shape_functions(speaker, Xtr)
    idx = np.where(te)[0]
    q_idx = [k for k, m in zip(idx, quiet[te] &
                               (np.abs(yte - base) > 40)) if m]
    print(f"\nexample decompositions (held-out, quiet, |R| large); "
          f"intercept {base:+.1f}cp:")
    examples = []
    for k in q_idx[:6]:
        r = rows[k]
        x = np.array([r["feats"][f] for f in FEATURES])
        contrib = attribute(shapes, x)
        pred = base + contrib.sum()
        top = sorted(zip(FEATURES, contrib), key=lambda t: -abs(t[1]))[:4]
        line = ", ".join(f"{f} {c:+.0f}" for f, c in top if abs(c) >= 5)
        print(f"  {r['fen']}")
        print(f"    R={r['r']:+d}  pred={pred:+.0f}  [{line}]")
        examples.append({"fen": r["fen"], "r": r["r"],
                         "pred": round(float(pred), 1),
                         "top": [(f, round(float(c), 1)) for f, c in top]})
    report["examples"] = examples

    json.dump(report, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
