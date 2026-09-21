#!/usr/bin/env python3
"""100x Maia3@2600-vs-2600 (Temperature 1.0 = true policy sampling)
continuations for the 53 development-flipped positions. Checkpointed per
position; cap-adjudicated by Stockfish eval."""
import os, sys, json, multiprocessing as mp
ROOT = "/Users/avismara/Projects/active/lucena"
SRC = f"{ROOT}/lucena-plans/src"
STUDY = f"{ROOT}/lucena-plans/research/experiments/studies/imbalance_benchmark"
sys.path.insert(0, SRC)
import chess, chess.engine
from initiative import initiative, _LEAD_MAG, _CLEAR_MAG, _STRONG_GEO

MAIA = [f"{ROOT}/.venv-maia/bin/python", f"{ROOT}/engine/scripts/maia_policy_uci.py"]
SF = "/opt/homebrew/bin/stockfish"
GAMES = 100
PLYCAP = 250
OUT = os.path.join(STUDY, "maia2600_flipped.jsonl")


def flipped_positions():
    idx = json.load(open(os.path.join(STUDY, "review_index.json")))
    rows = {r["fen"]: r for r in (json.loads(l) for l in
            open(os.path.join(STUDY, "imbalance_benchmark.jsonl")))}
    cache = {r["fen"]: r for r in (json.loads(l) for l in
             open(os.path.join(STUDY, "labeled_cache.jsonl")))}

    def tactical_only(iv):
        if iv.get("basis", "").startswith("geometry"):
            return iv["leader"]
        mag = iv["magnitude"]; holder = iv["holder"]
        res = iv[holder.lower()]["resources"]
        if mag < _LEAD_MAG:
            return "balanced"
        if (mag >= _CLEAR_MAG or res >= _STRONG_GEO) and iv["explained"]:
            return holder
        return "resolves" if iv.get("resolves") else "unclear"

    out = []
    for r in idx:
        iv = initiative(r["fen"], cache[r["fen"]]["pvs"])
        old = tactical_only(iv); new = iv["leader"]
        if new in ("White", "Black") and old not in ("White", "Black"):
            out.append({"id": r["id"], "fen": r["fen"], "verdict": new,
                        "comp_side": rows[r["fen"]]["read"]["side"],
                        "engine_cp": rows[r["fen"]]["engine_cp"]})
    return out


_M = _S = None
def _engines():
    global _M, _S
    if _M is None:
        _M = chess.engine.SimpleEngine.popen_uci(MAIA, timeout=120)
        _M.configure({"SelfElo": 2600, "OppoElo": 2600, "Temperature": "1.0"})
        _S = chess.engine.SimpleEngine.popen_uci(SF)
        _S.configure({"Threads": 1, "Hash": 64})
    return _M, _S


def run_position(rec):
    maia, sf = _engines()
    w = d = l = 0
    for _ in range(GAMES):
        b = chess.Board(rec["fen"]); plies = 0
        while not b.is_game_over(claim_draw=True) and plies < PLYCAP:
            b.push(maia.play(b, chess.engine.Limit(time=1.0)).move)
            plies += 1
        res = b.result(claim_draw=True)
        if res == "*":
            sc = sf.analyse(b, chess.engine.Limit(depth=10))["score"] \
                   .white().score(mate_score=100000) or 0
            res = "1-0" if sc > 150 else "0-1" if sc < -150 else "1/2-1/2"
        if res == "1-0": w += 1
        elif res == "0-1": l += 1
        else: d += 1
    return {**rec, "white_wins": w, "draws": d, "black_wins": l}


def main():
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(x)["id"] for x in open(OUT)}
    todo = [r for r in flipped_positions() if r["id"] not in done]
    print(f"positions: {len(todo)} to run ({len(done)} done)", flush=True)
    with mp.Pool(8) as pool:
        for res in pool.imap_unordered(run_position, todo):
            with open(OUT, "a") as f:
                f.write(json.dumps(res) + "\n")
            print(f"  {res['id']}: W {res['white_wins']} D {res['draws']} "
                  f"B {res['black_wins']}  (verdict {res['verdict']}, "
                  f"comp {res['comp_side']}, eval {res['engine_cp']:+})", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
