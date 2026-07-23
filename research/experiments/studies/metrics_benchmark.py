"""metrics_benchmark — do the batch-2 metrics hold up? (2026-07-23 owner
request.) One corpus pass; per game, middlegame samples (real phase
classifier + hysteresis, plies 8-80 step 4) reduce each new metric to a
per-game differential, tested against White's score (Pearson r + quartile
split). Special-case tests where a metric's DESIGN makes a sharper claim:

  space          diff (W-B total regional space) vs score — and the
                 owner's exploitability thesis: among space-edge games,
                 does an exploitable wake (holes the enemy eyes) eat the
                 edge?
  breaks         playable-break diff vs score; and the SPENT flag — a
                 side with no breaks at all through its middlegame.
  passers        momentum diff (max relative rank, +1 if path clear).
  color_complex  weak_for flag: score of the flagged side.
  trapped        burden diff (trapped + 0.5*restricted), enemy - own.
  development    notable-lag count diff over plies 8-20 (opening window;
                 the annoyance-gate threshold under test).

Run: .venv/python research/experiments/studies/metrics_benchmark.py [--games N]
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-core/python")
from lucena_core import metrics as met
from lucena_core import positional as pos
from lucena_core.reads import game_phase

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
RANK = {"opening": 0, "middlegame": 1, "endgame": 2}
MAX_PLY = 80
STEP = 4
WORKERS = 8
WSCORE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}


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
                acc = {k: [] for k in ("space", "wake_w", "wake_b",
                                       "breaks", "nobrk_w", "nobrk_b",
                                       "passer", "cc_w", "cc_b", "trap")}
                dev_w = dev_b = dev_n = 0
                rank = 0
                for i, mv in enumerate(game.mainline_moves()):
                    b.push(mv)
                    ply = i + 1
                    if ply > MAX_PLY:
                        break
                    if ply < 8 or ply % STEP:
                        continue
                    fen = b.fen()
                    rank = max(rank, RANK[game_phase(fen)["phase"]])
                    if rank == 0 and 8 <= ply <= 20:
                        d = pos.development_lag(fen)
                        dev_w += sum(e["notable"] for e in d["white"])
                        dev_b += sum(e["notable"] for e in d["black"])
                        dev_n += 1
                    if rank != 1:
                        continue
                    sp = met.space_report(fen)
                    acc["space"].append(sum(
                        sp[r]["white"]["space"] - sp[r]["black"]["space"]
                        for r in sp))
                    acc["wake_w"].append(sum(
                        len(sp[r]["white"]["exploitable"]) for r in sp))
                    acc["wake_b"].append(sum(
                        len(sp[r]["black"]["exploitable"]) for r in sp))
                    br = met.pawn_breaks(fen)
                    acc["breaks"].append(
                        sum(1 for x in br["white"] if x["playable"])
                        - sum(1 for x in br["black"] if x["playable"]))
                    acc["nobrk_w"].append(0 if br["white"] else 1)
                    acc["nobrk_b"].append(0 if br["black"] else 1)
                    pa = met.passer_report(fen)

                    def mom(side):
                        ps = pa[side]
                        return max((p["rank"] + (1 if p["path_clear"] else 0)
                                    for p in ps), default=0)
                    acc["passer"].append(mom("white") - mom("black"))
                    cc = met.color_complex(fen)
                    acc["cc_w"].append(sum(
                        1 for c in cc.values() if c["weak_for"] == "White"))
                    acc["cc_b"].append(sum(
                        1 for c in cc.values() if c["weak_for"] == "Black"))
                    tr = met.trapped_pieces(fen)

                    def burden(side):
                        return sum(1.0 if e["state"] == "trapped" else 0.5
                                   for e in tr[side])
                    acc["trap"].append(burden("black") - burden("white"))
                if len(acc["space"]) < 3:
                    continue
                mean = {k: sum(v) / len(v) if v else 0.0
                        for k, v in acc.items()}
                rows.append({"score": WSCORE[result], **mean,
                             "dev": ((dev_b - dev_w) / dev_n) if dev_n
                                    else None})
            except Exception:
                continue
    return rows


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else 0.0


def _r_and_quartiles(rows, key, label):
    pts = sorted((r[key], r["score"]) for r in rows if r[key] is not None)
    if len(pts) < 40:
        print(f"  {label:<28} n={len(pts)} — too few")
        return
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    q = len(pts) // 4
    lo = sum(p[1] for p in pts[:q]) / q
    hi = sum(p[1] for p in pts[-q:]) / q
    print(f"  {label:<28} r={pearson(xs, ys):+.3f}   "
          f"bottom-q {lo:.3f} -> top-q {hi:.3f}   (n={len(pts)})")


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
    print(f"games with a middlegame: {len(rows)}\n")
    print("== differentials vs White score (middlegame means) ==")
    _r_and_quartiles(rows, "space", "space diff (W-B)")
    _r_and_quartiles(rows, "breaks", "playable-break diff")
    _r_and_quartiles(rows, "passer", "passer momentum diff")
    _r_and_quartiles(rows, "trap", "trapped burden diff (B-W)")
    _r_and_quartiles(rows, "dev", "notable dev-lag diff (B-W)")

    print("\n== exploitability thesis: space edge, split by the wake ==")
    for side, skey, wkey in (("White", 1, "wake_w"), ("Black", -1, "wake_b")):
        edge = [r for r in rows if skey * r["space"] >= 3]
        clean = [r for r in edge if r[wkey] < 0.5]
        wake = [r for r in edge if r[wkey] >= 0.5]
        if clean and wake:
            sc = sum(r["score"] for r in clean) / len(clean)
            sw = sum(r["score"] for r in wake) / len(wake)
            if side == "Black":
                sc, sw = 1 - sc, 1 - sw
            print(f"  {side} space edge: clean wake {sc:.3f} (n={len(clean)})"
                  f"  vs exploitable wake {sw:.3f} (n={len(wake)})")

    print("\n== the SPENT flag: no breaks at all through the middlegame ==")
    for side, key in (("White", "nobrk_w"), ("Black", "nobrk_b")):
        spent = [r for r in rows if r[key] >= 0.8]
        rest = [r for r in rows if r[key] < 0.8]
        if spent:
            ss = sum(r["score"] for r in spent) / len(spent)
            sr = sum(r["score"] for r in rest) / len(rest)
            if side == "Black":
                ss, sr = 1 - ss, 1 - sr
            print(f"  {side} spent {ss:.3f} (n={len(spent)}) vs "
                  f"has-breaks {sr:.3f} (n={len(rest)})")

    print("\n== weak color complex: score of the flagged side ==")
    for side, key in (("White", "cc_w"), ("Black", "cc_b")):
        flag = [r for r in rows if r[key] >= 0.3]
        rest = [r for r in rows if r[key] < 0.3]
        if flag:
            sf = sum(r["score"] for r in flag) / len(flag)
            sr = sum(r["score"] for r in rest) / len(rest)
            if side == "Black":
                sf, sr = 1 - sf, 1 - sr
            print(f"  {side} flagged {sf:.3f} (n={len(flag)}) vs "
                  f"unflagged {sr:.3f} (n={len(rest)})")


if __name__ == "__main__":
    n = 0
    if "--games" in sys.argv:
        n = int(sys.argv[sys.argv.index("--games") + 1])
    main(n)
