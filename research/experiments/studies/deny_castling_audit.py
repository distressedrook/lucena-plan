"""deny_castling_audit — does DENY CASTLING survive its own elimination gate?

RULING (2026-07-22): DENY CASTLING is offered by the fast/unverified SUGGEST
trigger whenever (own castled, opponent not castled, opponent has rights or
is central) — a pure state check, no reachability. It must NEVER reach the
user in that raw form. Elimination gate (uses lines we ALREADY have — no
new rolling): the candidate SURVIVES only if the opponent does NOT castle
within WINDOW plies (~5-6 of their own moves) in ANY of the rolled engine-
equal lines or Maia samples; it is ELIMINATED the instant any rolled line
shows them castling within that window (this is what happens on
n438_a20 — Black castles in all 4 engine lines within 1-3 of their own
moves; DENY CASTLING should never have been shown there).

This audits the claim at corpus scale using the ALREADY-BANKED benchmark
shards (eng_shards/, maia_shards/bench_*.jsonl) — no engine calls.
"""
from __future__ import annotations

import glob
import json
import sys

import chess

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-plans/src")
from plan_diff import snapshot

BENCH = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/benchmark_v1.jsonl"
ENG_DIR = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/eng_shards"
MAIA_DIR = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/maia_shards"
EQUAL_BAND = 50
WINDOW = 12          # ~5-6 of the opponent's own moves


def trigger_fires(fen: str) -> list[str]:
    """['W','B'] for whichever side(s) the DENY CASTLING trigger offers."""
    b = chess.Board(fen)
    s = snapshot(b)
    out = []
    for t, o in (("W", "B"), ("B", "W")):
        if s[f"{t}.castled"] and not s[f"{o}.castled"] \
                and (s[f"{o}.can_castle"] or s[f"{o}.king_central"]):
            out.append(t)
    return out


def opponent_castles_within(fen: str, opponent_side: bool,
                            ucis: list[str], window: int) -> bool:
    b = chess.Board(fen)
    for i, u in enumerate(ucis[:window]):
        mv = chess.Move.from_uci(u)
        is_castle = b.is_castling(mv)
        mover_is_opp = (b.turn == opponent_side)
        b.push(mv)
        if is_castle and mover_is_opp:
            return True
    return False


def load(dirpath, pattern):
    out = {}
    for p in sorted(glob.glob(f"{dirpath}/{pattern}")):
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                out[r["id"]] = r
    return out


if __name__ == "__main__":
    bench = {json.loads(l)["id"]: json.loads(l) for l in open(BENCH)}
    eng = load(ENG_DIR, "*.jsonl")
    maia = load(MAIA_DIR, "bench_*.jsonl")
    print(f"positions {len(bench)} | engine leg {len(eng)} | maia leg {len(maia)}")

    n_triggered = 0
    n_eliminated_eng = 0
    n_eliminated_maia = 0
    n_eliminated_either = 0
    n_survived = 0
    n_no_data = 0
    examples_survived = []
    examples_eliminated = []

    for _id, r in bench.items():
        fen = r["fen"]
        sides = trigger_fires(fen)
        if not sides:
            continue
        for t in sides:
            n_triggered += 1
            opp = chess.BLACK if t == "W" else chess.WHITE
            eng_row = eng.get(_id)
            maia_row = maia.get(_id)
            if not eng_row and not maia_row:
                n_no_data += 1
                continue

            elim_eng = False
            if eng_row:
                cp1 = eng_row["pvs"][0]["cp"] if eng_row["pvs"] else 0
                equal = [p for p in eng_row["pvs"]
                        if abs(p["cp"] - cp1) <= EQUAL_BAND]
                elim_eng = any(opponent_castles_within(fen, opp, p["ucis"], WINDOW)
                              for p in equal)

            elim_maia = False
            if maia_row:
                elim_maia = any(
                    opponent_castles_within(fen, opp, s, WINDOW)
                    for s in maia_row["samples"])

            if elim_eng:
                n_eliminated_eng += 1
            if elim_maia:
                n_eliminated_maia += 1
            if elim_eng or elim_maia:
                n_eliminated_either += 1
                if len(examples_eliminated) < 3:
                    examples_eliminated.append((_id, t, elim_eng, elim_maia))
            else:
                n_survived += 1
                if len(examples_survived) < 3:
                    examples_survived.append((_id, t))

    print(f"\nDENY CASTLING trigger fires: {n_triggered} (side, position) cases")
    print(f"  no rolled data available: {n_no_data}")
    print(f"  ELIMINATED (opponent castles within {WINDOW} plies "
          f"in >=1 rolled line): {n_eliminated_either} "
          f"({100*n_eliminated_either/max(n_triggered-n_no_data,1):.0f}% "
          f"of cases with data)")
    print(f"    - by engine equal-lines alone: {n_eliminated_eng}")
    print(f"    - by maia samples alone: {n_eliminated_maia}")
    print(f"  SURVIVED (opponent never castles within window, any rolled "
          f"line): {n_survived} "
          f"({100*n_survived/max(n_triggered-n_no_data,1):.0f}%)")
    print(f"\nexample SURVIVED cases (worth actually showing the user):")
    for _id, t in examples_survived:
        print(f"  {_id} ({t})")
    print(f"\nexample ELIMINATED cases (would have been a false candidate):")
    for _id, t, ee, em in examples_eliminated:
        print(f"  {_id} ({t}) eng_elim={ee} maia_elim={em}")
