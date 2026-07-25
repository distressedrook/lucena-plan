#!/usr/bin/env python3
"""GENERAL material-imbalance benchmark from gm_classical.pgn.

The Q-for-two-minors run (80 positions) generalized: walk EVERY GM game, find
every position where the material is TRADED (a genuine imbalance — one side has
more of one piece type, the other more of another: exchange sacs, Q-for-pieces,
2-minors-vs-rook, piece-for-pawns, ...), engine-label them, DROP the ones the
engine calls decisive (those are just winning), and benchmark the compensation
read on the EQUALISH survivors — by imbalance type.

Pipeline (finding 22 infra: isolate each game's text so one corrupt game can't
desync a neighbor; parallel harvest + parallel engine label + per-position
watchdog):
  Phase 1  parallel, engine-free   -> first qualifying imbalance per game
  Phase 2  parallel, Stockfish     -> MultiPV=4 @1M nodes, real eval + lines
  Phase 3  main                    -> drop |eval|>EQ, run read, freeze benchmark

Output (frozen artifact):
  imbalance_benchmark.jsonl  one equalish position per line (fen, type,
                             naive_cp, engine_cp, top ucis, our read)
  report.txt                 per-type: n, %equalish, read-form split, magnitude
"""
import io, os, sys, json, random, multiprocessing as mp
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/Users/avismara/Development/lucena/lucena-plans"
sys.path.insert(0, os.path.join(ROOT, "src"))
import chess, chess.pgn, chess.engine

PGN = os.path.join(ROOT, "research/data/gm_classical.pgn")
SF = "/opt/homebrew/bin/stockfish"
NODES = 1_000_000
MAX_LABEL = 1200         # cap engine-labeled positions (sampled if more)
EQ = 100                 # |engine cp| <= EQ  ==  "equalish" (kept); else dropped
MIN_MOVE = 12
SEED = 17
VAL = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
       chess.ROOK: 500, chess.QUEEN: 900}


def diff_vec(b):
    """(dP,dN,dB,dR,dQ) = White - Black piece counts."""
    def c(pt, col): return len(b.pieces(pt, col))
    return tuple(c(pt, chess.WHITE) - c(pt, chess.BLACK)
                 for pt in (chess.PAWN, chess.KNIGHT, chess.BISHOP,
                            chess.ROOK, chess.QUEEN))


def is_imbalance(dv):
    """A TRADE imbalance: some type White has more of AND some type Black has
    more of (unlike-piece trade). Excludes clean surpluses and symmetry."""
    return any(x > 0 for x in dv) and any(x < 0 for x in dv)


def naive_cp(dv):
    dP, dN, dB, dR, dQ = dv
    return 100*dP + 300*(dN+dB) + 500*dR + 900*dQ


def keep_imbalance(dv):
    """Structural major-piece imbalances kept regardless of value; minor/pawn
    imbalances need >=100cp of value at stake (drops value-neutral B-vs-N)."""
    dP, dN, dB, dR, dQ = dv
    return dQ != 0 or dR != 0 or abs(naive_cp(dv)) >= 100


def itype(dv):
    dP, dN, dB, dR, dQ = dv
    m = dN + dB
    if dQ != 0:
        s = 1 if dQ > 0 else -1        # side with the extra queen
        dr, dm = -s*dR, -s*m           # rooks / minors the queen-side is DOWN
        if dr == 0 and dm == 2: return "Q_vs_2minors"
        if dr == 0 and dm == 3: return "Q_vs_3minors"
        if dr == 1 and dm == 1: return "Q_vs_R+minor"
        if dr == 2 and dm == 0: return "Q_vs_2rooks"
        if dr == 1 and dm == 2: return "Q_vs_R+2minors"
        return "Q_vs_mixed"
    if dR != 0:
        s = 1 if dR > 0 else -1        # side with the extra rook(s)
        dm, dp, ar = -s*m, -s*dP, abs(dR)
        if ar == 1 and dm == 1: return "exchange" if dp <= 0 else "exchange_for_pawns"
        if ar == 1 and dm == 2: return "2minors_vs_rook"
        if ar == 1 and dm == 0 and dp >= 2: return "rook_vs_pawns"
        if ar == 2 and dm == 2: return "double_exchange"
        return "rook_mixed"
    if m != 0:
        s = 1 if m > 0 else -1         # side with the extra minor(s)
        dp, am = -s*dP, abs(m)
        if am == 1 and dp >= 2: return "minor_vs_pawns"
        if am == 2 and dp >= 3: return "2minors_vs_pawns"
        return "minor_mixed"
    return "other"


def harvest(block):
    """First position of EACH imbalance type the game passes through (a game
    can contribute to several types over its course) — this multiplies the
    rare sharp types vs one-per-game, feeding the stratified sampler."""
    out = {}
    try:
        g = chess.pgn.read_game(io.StringIO(block))
        if g is None:
            return []
        b = g.board()
        for mv in g.mainline_moves():
            b.push(mv)
            if b.fullmove_number < MIN_MOVE or b.is_check():
                continue
            dv = diff_vec(b)
            if is_imbalance(dv) and keep_imbalance(dv):
                t = itype(dv)
                if t not in out:
                    out[t] = {"fen": b.fen(), "type": t, "naive_cp": naive_cp(dv)}
    except Exception:
        pass
    return list(out.values())


_ENG = None
def _engine():
    global _ENG
    if _ENG is None:
        _ENG = chess.engine.SimpleEngine.popen_uci(SF)
        _ENG.configure({"Threads": 1, "Hash": 128})
    return _ENG


def label(rec):
    try:
        b = chess.Board(rec["fen"])
        info = _engine().analyse(b, chess.engine.Limit(nodes=NODES), multipv=4)
        pvs = [{"cp": pv["score"].white().score(mate_score=100000),
                "ucis": [m.uci() for m in pv["pv"]], "pv": [], "san": []}
               for pv in info]
        rec = dict(rec)
        rec["cp"] = pvs[0]["cp"]
        rec["pvs"] = pvs
        return rec
    except Exception as e:
        return {**rec, "err": str(e)}


def split_blocks(path):
    blocks, cur = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("[Event ") and cur:
                blocks.append("".join(cur)); cur = []
            cur.append(line)
    if cur:
        blocks.append("".join(cur))
    return blocks


CACHE = os.path.join(HERE, "labeled_cache.jsonl")
SAMPLE = os.path.join(HERE, "sample_fens.json")   # PINNED benchmark set (stable ids)
CAP_PER_TYPE = 150       # stratified: at most this many labeled per imbalance type


def _load_cache():
    if not os.path.exists(CACHE):
        return {}
    with open(CACHE) as f:
        return {r["fen"]: r for r in (json.loads(l) for l in f)}


def main():
    random.seed(SEED)
    stratify = os.environ.get("STRATIFY") == "1"
    cache = _load_cache()

    # Fast path for phase-3 iteration: reuse the cache as-is unless STRATIFY=1
    # forces a fresh stratified harvest + (cache-aware) labeling.
    if cache and not stratify:
        # use the PINNED sample (stable ids) if present, else the whole cache
        if os.path.exists(SAMPLE):
            fens = json.load(open(SAMPLE))
            ok = [cache[f] for f in fens if f in cache]
        else:
            ok = list(cache.values())
        print(f"loaded {len(ok)} labeled positions from cache", flush=True)
    else:
        print("split PGN ...", flush=True)
        blocks = split_blocks(PGN)
        print(f"  {len(blocks)} games", flush=True)

        print("phase 1: parallel harvest (first-per-type-per-game) ...", flush=True)
        with mp.Pool(10) as pool:
            found = [r for lst in pool.imap_unordered(harvest, blocks, chunksize=64)
                     for r in lst]
        by_type = defaultdict(list)
        seen = set()
        for r in found:
            if r["fen"] in seen:
                continue
            seen.add(r["fen"]); by_type[r["type"]].append(r)
        print(f"  {len(seen)} imbalance positions, by type:",
              {t: len(v) for t, v in sorted(by_type.items(), key=lambda kv: -len(kv[1]))},
              flush=True)

        # STRATIFIED sample: cap common types, take ALL of the rare sharp types
        sample = []
        for t, v in by_type.items():
            sample += v if len(v) <= CAP_PER_TYPE else random.sample(v, CAP_PER_TYPE)
        with open(SAMPLE, "w") as f:          # PIN it — stable ids across re-runs
            json.dump([r["fen"] for r in sample], f)
        print(f"phase 2: stratified sample {len(sample)} "
              f"(cap {CAP_PER_TYPE}/type)", flush=True)

        to_label = [r for r in sample if r["fen"] not in cache]
        print(f"  {len(sample)-len(to_label)} already cached, "
              f"labeling {len(to_label)} new @ {NODES} nodes ...", flush=True)
        with mp.Pool(9) as pool:
            newly = [r for r in pool.imap_unordered(label, to_label, chunksize=1)
                     if "err" not in r]
        for r in newly:                       # grow the cache (union by fen)
            cache[r["fen"]] = r
        with open(CACHE, "w") as f:
            for r in cache.values():
                f.write(json.dumps(r) + "\n")
        ok = [cache[r["fen"]] for r in sample if r["fen"] in cache]
        print(f"  labeled set {len(ok)} (cache now {len(cache)})", flush=True)

    print("phase 3: drop non-equal, read + freeze equalish ...", flush=True)
    import fact_sheet as F
    equalish, dropped, read_err = [], 0, 0
    concrete_kinds = Counter()
    per_type = defaultdict(lambda: {"n": 0, "eq": 0, "forms": Counter(),
                                    "mags": Counter()})
    for r in ok:
        t = r["type"]; per_type[t]["n"] += 1
        if abs(r["cp"]) > EQ:
            dropped += 1
            continue
        per_type[t]["eq"] += 1
        try:
            out = F.post_verify_json(r["fen"], r["pvs"], None)
        except Exception:
            # a handful of corpus FENs have inconsistent castling rights that
            # python-chess tolerates but lucena_core.board rejects — skip.
            read_err += 1
            per_type[t]["eq"] -= 1
            continue
        c = out.get("compensation")
        prim = (c or {}).get("primary", "null")
        per_type[t]["forms"][prim] += 1
        if c:
            per_type[t]["mags"][c["magnitude"]] += 1
            if prim == "concrete":
                concrete_kinds[c.get("concrete_kind") or "?"] += 1
        equalish.append({
            "fen": r["fen"], "type": t, "naive_cp": r["naive_cp"],
            "engine_cp": r["cp"], "top_ucis": [p["ucis"][0] if p["ucis"] else None
                                               for p in r["pvs"]],
            # sharpness = dynamism bucket (DEAD/QUIET/DYNAMIC/SHARP/RAZOR)
            "sharpness": (out["assessment"].get("character") or {}).get("bucket"),
            # the SHEET'S OWN evidence-carrying blocks (owner 2026-07-25:
            # "wire these explanations in and verify") — the review page
            # displays these verbatim, so what gets verified is the product.
            "initiative": out["assessment"].get("initiative"),
            "king_why": {s: {"danger": (kb or {}).get("danger_bounded"),
                             "why": (kb or {}).get("why") or []}
                         for s, kb in
                         (out["assessment"].get("king_risk") or {}).items()
                         if isinstance(kb, dict)},
            "read": None if c is None else {
                "primary": c["primary"], "forms": c["forms"],
                "concrete_kind": c.get("concrete_kind"),
                "evidence": c.get("evidence") or [],
                "only_move": c.get("only_move"),
                "magnitude": c["magnitude"], "side": c["side"],
                "deficit_cp": c["deficit_cp"], "comp_cp": c["comp_cp"],
                "summary": c["summary"]},
        })

    outdir = HERE
    bpath = os.path.join(outdir, "imbalance_benchmark.jsonl")
    with open(bpath, "w") as f:
        for e in equalish:
            f.write(json.dumps(e) + "\n")

    # ---- report ----
    lines = []
    def pr(s=""):
        lines.append(s); print(s, flush=True)
    pr("\n===== IMBALANCE BENCHMARK =====")
    pr(f"labeled {len(ok)} | equalish(|cp|<={EQ}) {len(equalish)} | "
       f"dropped(decisive) {dropped} | read_err {read_err}")
    tot_forms = Counter(); tot_mags = Counter()
    pr(f"\n{'type':18} {'n':>4} {'eq':>4} {'eq%':>4}   forms(equalish)")
    for t, d in sorted(per_type.items(), key=lambda kv: -kv[1]["n"]):
        tot_forms += d["forms"]; tot_mags += d["mags"]
        eqp = round(100*d["eq"]/d["n"]) if d["n"] else 0
        fs = " ".join(f"{k}:{v}" for k, v in d["forms"].most_common())
        pr(f"{t:18} {d['n']:>4} {d['eq']:>4} {eqp:>3}%   {fs}")
    pr(f"\nALL equalish read forms: {dict(tot_forms.most_common())}")
    fired = sum(v for k, v in tot_forms.items() if k != 'null')
    static = tot_forms['attack'] + tot_forms['activity'] + tot_forms['space']
    pr(f"  fired {fired}/{len(equalish)}  "
       f"(static-explained {static}, concrete {tot_forms['concrete']}, "
       f"null {tot_forms['null']})")
    pr(f"concrete resolved by line-walk: {dict(concrete_kinds.most_common())}")
    pr(f"magnitude when fired: {dict(tot_mags.most_common())}")
    pr(f"\nfrozen -> {bpath}")
    with open(os.path.join(outdir, "report.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
