"""export_benchmark — freeze benchmark_v1: 4,000 self-contained positions.

The positions are the BANKED argmax-leg rows (maia_shards/argmax_*.jsonl) —
NOT a load_anchors() re-derivation, which is grammar-dependent (the v5
structure additions reshuffled the structure-balanced pick and broke the
k-study overlap: 150/300). The banked rows are what the existing Maia
results were computed on; the k-study anchors (ksample_*.jsonl) are
included and flagged with "kstudy": true.

Each row is SELF-CONTAINED (no PGN, no engine needed downstream):
  id            "n<gamenum>_a<anchorply>" — stable forever
  fen           the position
  anchor, result, structures, plies_total
  actual_ucis   the next 25 plies as played (the GM leg)
  random_ucis   the seeded random control (random.Random(n*1000+anchor))

FROZEN: never regenerate over new shards — benchmark_v1 is an eval set.
Run once; the file plus its manifest is the artifact.
"""
from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys

import glob

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/research/experiments")
from overnight_lift import PGN, index_games

MAIA_SHARDS = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/maia_shards"


def banked_anchors():
    """The rows the Maia results were actually computed on."""
    rows, seen = [], set()
    kstudy = set()
    for p in sorted(glob.glob(f"{MAIA_SHARDS}/ksample_[0-9]*.jsonl")):
        with open(p) as f:
            for l in f:
                if l.strip():
                    e = json.loads(l)
                    kstudy.add((e["n"], e["anchor"]))
    for p in sorted(glob.glob(f"{MAIA_SHARDS}/argmax_*.jsonl")):
        with open(p) as f:
            for l in f:
                if not l.strip():
                    continue
                e = json.loads(l)
                key = (e["n"], e["anchor"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"n": e["n"], "anchor": e["anchor"],
                             "result": e["result"],
                             "structures": e["structures"],
                             "kstudy": key in kstudy})
    return rows

OUT = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/benchmark_v1.jsonl"
MANIFEST = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/benchmark_v1.manifest.json"
HORIZON = 25

if __name__ == "__main__":
    offsets = {n: off for n, off in index_games()}
    anchors = banked_anchors()
    print(f"{len(anchors)} banked anchor rows "
          f"({sum(1 for a in anchors if a['kstudy'])} k-study)", flush=True)
    rows = []
    with open(PGN, encoding="latin-1") as f:
        for r in anchors:
            n, a = r["n"], r["anchor"]
            f.seek(offsets[n])
            game = chess.pgn.read_game(f)
            moves = list(game.mainline_moves())
            if len(moves) < a + HORIZON:
                continue
            b = game.board()
            for mv in moves[:a]:
                b.push(mv)
            rng = random.Random(n * 1000 + a)
            cur = b.copy()
            rnd = []
            for _ in range(HORIZON):
                lg = list(cur.legal_moves)
                if not lg:
                    break
                m = rng.choice(lg)
                rnd.append(m.uci())
                cur.push(m)
            rows.append({
                "id": f"n{n}_a{a}",
                "fen": b.fen(),
                "anchor": a,
                "result": r["result"],
                "structures": r["structures"],
                "kstudy": r["kstudy"],
                "plies_total": len(moves),
                "actual_ucis": [m.uci() for m in moves[a:a + HORIZON]],
                "random_ucis": rnd,
            })
    with open(OUT, "w") as g:
        for row in rows:
            g.write(json.dumps(row, separators=(",", ":")) + "\n")
    sha = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    commit = subprocess.run(
        ["git", "-C", "/Users/avismara/Development/lucena/lucena-plans/src",
         "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    manifest = {
        "name": "benchmark_v1", "positions": len(rows),
        "horizon": HORIZON, "source": "gm_classical.pgn (TWIC 1497-1653)",
        "anchor_scheme": "banked argmax-leg rows (maia_shards/argmax_*), "
                         "plies 20/30/40/50",
        "kstudy_rows": sum(1 for r in rows if r["kstudy"]),
        "random_seed_scheme": "random.Random(n*1000+anchor)",
        "sha256": sha, "exported_at_commit": commit or "uncommitted",
    }
    json.dump(manifest, open(MANIFEST, "w"), indent=2)
    print(f"wrote {len(rows)} positions -> {OUT}")
    print(f"sha256 {sha[:16]}...  manifest -> {MANIFEST}")
