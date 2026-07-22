"""Launch-conditioned storm trial (see 2026-07-22 session): among anchors
with the STORM PRECONDITION, measure deterrence, refutation, and outcomes
by the victim's center state at the anchor."""
import glob, json, statistics, chess, chess.pgn
from multiprocessing import Pool

PGN = '/Users/avismara/Development/lucena/lucena-plans/data/gm_classical.pgn'
SH = '/Users/avismara/Development/lucena/lucena-plans/experiments/lift_shards'


def central_levers(b, side):
    ahead = 8 if side == chess.WHITE else -8
    own = b.pieces(chess.PAWN, side); enemy = b.pieces(chess.PAWN, not side)
    for p in own:
        for df in (-1, 1):
            t2 = p + ahead + df
            if 0 <= t2 < 64 and abs(chess.square_file(t2)-chess.square_file(p)) == 1 \
                    and t2 in enemy and 2 <= chess.square_file(t2) <= 5:
                return True
        home = chess.square_rank(p) == (1 if side == chess.WHITE else 6)
        blocked = False
        for adv in [p+ahead] + ([p+2*ahead] if home else []):
            if not (0 <= adv < 64) or b.piece_at(adv) or blocked:
                blocked = True; continue
            if not 2 <= chess.square_file(adv) <= 5:
                continue
            for df in (-1, 1):
                t2 = adv + ahead + df
                if 0 <= t2 < 64 and abs(chess.square_file(t2)-chess.square_file(adv)) == 1 and t2 in enemy:
                    return True
    return False


def index_offsets():
    offsets = {}
    n = 0
    with open(PGN, 'rb') as f:
        off = f.tell()
        for line in iter(f.readline, b''):
            if line.startswith(b'[Event '):
                n += 1
                offsets[n] = off
            off = f.tell()
    return offsets


OFFSETS = None


def work(chunk):
    global OFFSETS
    if OFFSETS is None:
        OFFSETS = index_offsets()
    out = []
    f = open(PGN, encoding='latin-1')
    for r in chunk:
        try:
            f.seek(OFFSETS[r['n']])
            g = chess.pgn.read_game(f)
            b = g.board()
            for i, mv in enumerate(g.mainline_moves()):
                if i >= r['anchor']:
                    break
                b.push(mv)
        except Exception:
            continue
        for st, sc_side in (('W', chess.WHITE), ('B', chess.BLACK)):
            k = b.king(sc_side); vk = b.king(not sc_side)
            if k is None or vk is None:
                continue
            skf, vkf = chess.square_file(k), chess.square_file(vk)
            wing_files = range(5, 8) if vkf >= 5 else (range(0, 3) if vkf <= 2 else None)
            if wing_files is None:
                continue
            if not ((vkf >= 5 and skf <= 4) or (vkf <= 2 and skf >= 3)):
                continue
            wp = sum(1 for q in b.pieces(chess.PAWN, sc_side)
                     if chess.square_file(q) in wing_files)
            if wp < 2:
                continue
            live = central_levers(b, not sc_side)
            labs = set(r['as'])
            launched = any(l.startswith(f'{st}:storm_launch') for l in labs)
            completed = f'{st}:pawn_storm' in labs
            res = {'1-0': 1.0, '0-1': 0.0, '1/2-1/2': 0.5}[r['result']]
            ssc = res if st == 'W' else 1.0 - res
            out.append((live, launched, completed, ssc))
    return out


if __name__ == '__main__':
    rows = []
    for p in sorted(glob.glob(f'{SH}/shard_*.jsonl')):
        with open(p) as fh:
            rows.extend(json.loads(l) for l in fh)
    chunks = [rows[i::8] for i in range(8)]
    with Pool(8) as pool:
        results = [x for c in pool.map(work, chunks) for x in c]
    print(f'storm-precondition anchors: {len(results)}')
    for label, cond in (('victim center LIVE  ', True), ('victim center SEALED', False)):
        sub = [x for x in results if x[0] == cond]
        if not sub:
            continue
        ln = [x for x in sub if x[1]]
        cp = [x for x in ln if x[2]]
        print(f'{label}: n={len(sub):>6} | launch {100*len(ln)/len(sub):5.1f}% | '
              f'complete|launch {100*len(cp)/max(1,len(ln)):5.1f}% | '
              f'stormer score|launch '
              f'{statistics.mean([x[3] for x in ln]) if ln else 0:.3f}'
              f' | score|no-launch '
              f'{statistics.mean([x[3] for x in sub if not x[1]]) if len(sub)>len(ln) else 0:.3f}')
