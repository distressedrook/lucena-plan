"""Positional trajectory extractor — pilot v0.

Scans elite PGNs for Carlsbad-structure games, computes the per-ply term
trajectory (static, engine-free, via lucena_engine.positional), and applies
naive change-point segmentation: an episode boundary is where the dominant
moving term changes. Output feeds the human segmentation audit.
"""
import sys, json, argparse
import chess, chess.pgn
sys.path.insert(0, '/Users/avismara/Projects/active/lucena/engine/python')
from lucena_core import positional
from lucena_core.board import Board as LBoard

TERMS = ['material', 'king_safety', 'activity', 'pawns', 'center']

def is_carlsbad(b: chess.Board) -> bool:
    """White: pawn d4, no c-pawn. Black: pawns c6+d5, no e-pawn."""
    wp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.WHITE)}
    bp = {chess.square_name(s) for s in b.pieces(chess.PAWN, chess.BLACK)}
    return ('d4' in wp and not any(sq[0] == 'c' for sq in wp)
            and 'c6' in bp and 'd5' in bp and not any(sq[0] == 'e' for sq in bp))

def term_vector(fen: str) -> dict:
    d = positional.analyze_positional(LBoard(fen))
    v = {t: d['terms'][t]['cp'] for t in TERMS}
    ks = d['terms']['king_safety']['features']
    v['w_attack_units'] = ks['black']['attack_units']   # white's attack ON black king
    v['b_attack_units'] = ks['white']['attack_units']
    pw = d['terms']['pawns']['features']
    v['w_passed'] = len(pw['white']['passed']); v['b_passed'] = len(pw['black']['passed'])
    return v

def trajectory(game) -> dict | None:
    b = game.board()
    fens, sans, carlsbad_span = [], [], []
    for i, mv in enumerate(game.mainline_moves()):
        sans.append(b.san(mv)); b.push(mv); fens.append(b.fen())
        if is_carlsbad(b): carlsbad_span.append(i)
    if len(carlsbad_span) < 10:                       # structure must persist
        return None
    lo, hi = carlsbad_span[0], min(carlsbad_span[-1] + 12, len(fens) - 1)
    traj = [term_vector(fens[k]) for k in range(lo, hi + 1)]
    return {'sans': sans[lo:hi + 1], 'fens': [fens[lo], fens[hi]],
            'start_ply': lo, 'traj': traj,
            'white': game.headers.get('White'), 'black': game.headers.get('Black'),
            'result': game.headers.get('Result'), 'opening': game.headers.get('Opening', '')}

def segment(traj, min_len=6, jump=20):
    """Naive change-point pass: dominant-moving-term per window; boundary on change."""
    events = []
    for k in range(1, len(traj)):
        deltas = {t: traj[k][t] - traj[k-1][t] for t in TERMS}
        dom, dv = max(deltas.items(), key=lambda kv: abs(kv[1]))
        if abs(dv) >= jump:
            events.append((k, dom, dv))
    # merge consecutive same-term events into episodes
    episodes = []
    for k, dom, dv in events:
        if episodes and episodes[-1]['term'] == dom and k - episodes[-1]['end'] <= min_len:
            episodes[-1]['end'] = k; episodes[-1]['net'] += dv
        else:
            episodes.append({'term': dom, 'start': k, 'end': k, 'net': dv})
    return [e for e in episodes if abs(e['net']) >= jump]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pgn', default='lichess_elite_2023-01.pgn')
    ap.add_argument('--max-games', type=int, default=5)
    ap.add_argument('--out', default=None)
    ap.add_argument('--show', action='store_true')
    args = ap.parse_args()

    found, scanned = [], 0
    with open(args.pgn) as f:
        while len(found) < args.max_games:
            game = chess.pgn.read_game(f)
            if game is None: break
            scanned += 1
            t = trajectory(game)
            if t:
                t['episodes'] = segment(t['traj'])
                found.append(t)
                print(f"[{len(found)}] {t['white']} vs {t['black']} {t['result']} "
                      f"({t['opening'][:40]}) span={len(t['sans'])} plies, "
                      f"{len(t['episodes'])} episodes", flush=True)
    print(f"scanned {scanned} games, {len(found)} Carlsbad")
    if args.out:
        json.dump(found, open(args.out, 'w'))
    if args.show and found:
        t = found[0]
        print(f"\n== {t['white']} vs {t['black']} — term trace (every 2 plies) ==")
        print("ply  move    " + "".join(f"{x:>10}" for x in TERMS) + "   wAtk bAtk")
        for k in range(0, len(t['traj']), 2):
            v = t['traj'][k]
            print(f"{t['start_ply']+k:>3}  {t['sans'][k]:<7}" +
                  "".join(f"{v[x]:>10}" for x in TERMS) +
                  f"   {v['w_attack_units']:>4} {v['b_attack_units']:>4}")
        print("\nepisodes:")
        for e in t['episodes']:
            mv = ' '.join(t['sans'][e['start']:min(e['end']+1, e['start']+6)])
            print(f"  plies {t['start_ply']+e['start']}-{t['start_ply']+e['end']} "
                  f"term={e['term']} net={e['net']:+d}cp  moves: {mv}")

if __name__ == '__main__':
    main()
