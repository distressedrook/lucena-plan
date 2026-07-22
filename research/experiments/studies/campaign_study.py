"""campaign_study — is the CAMPAIGN the true unit of reliability?

Full-game parse of the GM corpus (33,769 games) -> compose() -> per
(game, side, campaign) the composition state:
  absent    no member family of the campaign fired for that side
  fragment  member(s) fired but NO instance formed (core missing, or a
            singleton) — the "created but never linked" cell
  partial   an instance (core + 1 member)
  full      an instance with core AND (a finish role OR >= 3 members)

Predictions (pre-registered, from finding 7's harvest-gating):
  score(full) > score(partial) > score(absent) ~ baseline > score(fragment)
The fragment cell is the campaign-level stall penalty: firing pieces of a
campaign without composing them should be NEGATIVE, like unharvested
weaknesses and advanced-no-lever minority attacks.

Output: campaign_study.jsonl (instances w/ spans, for witness mining) +
the per-campaign cell table on stdout. Deterministic; ~2 min on 8 cores.
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from multiprocessing import Pool

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans/src")
from plan_diff import parse_line
from hierarchy import CAMPAIGNS, compose

PGN = "/Users/avismara/Development/lucena/lucena-plans/research/data/gm_classical.pgn"
OUT = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/campaign_study.jsonl"
WORKERS = 8
MIN_PLIES = 40

FAM2CAMPS = collections.defaultdict(set)
for c, mem in CAMPAIGNS.items():
    for f in mem:
        FAM2CAMPS[f].add(c)


def process(chunk):
    """chunk = list of (game_number, byte_offset)."""
    rows = []
    with open(PGN, encoding="latin-1") as f:
        for n, off in chunk:
            f.seek(off)
            try:
                game = chess.pgn.read_game(f)
                res = game.headers.get("Result", "*")
                if res not in ("1-0", "0-1", "1/2-1/2"):
                    continue
                moves = list(game.mainline_moves())
                if len(moves) < MIN_PLIES:
                    continue
                parsed = parse_line(game.board(), moves,
                                    horizon=len(moves), tail=6)
            except Exception:
                continue
            insts = compose(parsed)
            # material balance (campaign side's perspective) at each
            # instance's start ply — the reverse-causality control:
            # a campaign launched from EQUAL material cannot be a symptom
            # of an already-won game
            VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                   chess.ROOK: 5, chess.QUEEN: 9}
            b2 = game.board()
            mat_at = {}
            want = sorted({i["span"][0] for i in insts})
            wi = 0
            for pi, mv in enumerate(moves):
                while wi < len(want) and want[wi] == pi:
                    w = sum(len(b2.pieces(pt, chess.WHITE)) * v
                            for pt, v in VAL.items())
                    bl = sum(len(b2.pieces(pt, chess.BLACK)) * v
                             for pt, v in VAL.items())
                    mat_at[pi] = w - bl
                    wi += 1
                b2.push(mv)
            for i in insts:
                d = mat_at.get(i["span"][0], 0)
                i["mat0"] = d if i["side"] == "W" else -d
            fired = {("W", c) for p in parsed for c in FAM2CAMPS[p["name"]]
                     if p["side"] == "W"} | \
                    {("B", c) for p in parsed for c in FAM2CAMPS[p["name"]]
                     if p["side"] == "B"}
            state = {}
            for side in ("W", "B"):
                for c in CAMPAIGNS:
                    key = (side, c)
                    mine = [i for i in insts
                            if i["side"] == side and i["campaign"] == c]
                    if mine:
                        best = max(mine, key=lambda i: len(i["members"]))
                        roles = {m["role"] for m in best["members"]}
                        full = "finish" in roles or len(best["members"]) >= 3
                        state[key] = "full" if full else "partial"
                    elif key in fired:
                        state[key] = "fragment"
                    else:
                        state[key] = "absent"
            rows.append({"n": n, "result": res,
                         "plies": len(moves),
                         "state": {f"{s}:{c}": v for (s, c), v in state.items()},
                         "instances": insts})
    return rows


def index_games():
    out = []
    n = 0
    with open(PGN, "rb") as f:
        off = f.tell()
        for line in iter(f.readline, b""):
            if line.startswith(b"[Event "):
                n += 1
                out.append((n, off))
            off = f.tell()
    return out


if __name__ == "__main__":
    idx = index_games()
    print(f"indexed {len(idx)} games", flush=True)
    chunks = [idx[i::WORKERS * 4] for i in range(WORKERS * 4)]
    rows = []
    with Pool(WORKERS) as pool:
        for part in pool.imap_unordered(process, chunks):
            rows.extend(part)
            print(f"  {len(rows)} games parsed", flush=True)
    with open(OUT, "w") as g:
        for r in rows:
            g.write(json.dumps(r, separators=(",", ":")) + "\n")

    SCORE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}
    print(f"\n{len(rows)} games | cells: absent / fragment / partial / full")
    print(f"{'campaign':>28} | {'absent':>13} | {'fragment':>13} | "
          f"{'partial':>13} | {'full':>13}")
    for c in CAMPAIGNS:
        cells = {k: [] for k in ("absent", "fragment", "partial", "full")}
        for r in rows:
            s = SCORE[r["result"]]
            for side, sc in (("W", s), ("B", 1.0 - s)):
                cells[r["state"][f"{side}:{c}"]].append(sc)
        parts = []
        for k in ("absent", "fragment", "partial", "full"):
            v = cells[k]
            parts.append(f"{statistics.mean(v):.3f} n={len(v):>6}"
                         if len(v) >= 30 else f"     - n={len(v):>6}")
        print(f"{c:>28} | " + " | ".join(parts))

    # ---- reverse-causality control: FULL instances by material at start
    print("\nfull-campaign score by MATERIAL AT CAMPAIGN START "
          "(equal = |diff| <= 1; the symptom test)")
    print(f"{'campaign':>28} | {'behind<=-2':>14} | {'equal':>14} | "
          f"{'ahead>=+2':>14}")
    for c in CAMPAIGNS:
        cells = {"behind": [], "equal": [], "ahead": []}
        for r in rows:
            s = SCORE[r["result"]]
            for i in r["instances"]:
                if i["campaign"] != c:
                    continue
                roles = {m["role"] for m in i["members"]}
                if not ("finish" in roles or len(i["members"]) >= 3):
                    continue
                sc = s if i["side"] == "W" else 1.0 - s
                d = i.get("mat0", 0)
                key = "equal" if abs(d) <= 1 else ("ahead" if d >= 2 else "behind")
                cells[key].append(sc)
        parts = []
        for k in ("behind", "equal", "ahead"):
            v = cells[k]
            parts.append(f"{statistics.mean(v):.3f} n={len(v):>6}"
                         if len(v) >= 30 else f"      - n={len(v):>6}")
        print(f"{c:>28} | " + " | ".join(parts))
