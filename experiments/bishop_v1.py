"""Good-bishop-vs-bad-bishop theorem, v1.

v1 over v0: the bad bishop must be ENTOMBED — standing BEHIND its own most
advanced rammed same-color pawn — not merely have pawns fixed on its color.
The escape study (bad_bishop_escape.py) showed the outside-the-chain case
costs a GM nothing (score ~0.50); the entombed case is the real patient.

Shape (unchanged): creation -> sustained differential >= MIN_SPAN plies ->
infiltration harvest on the weak complex.
"""
from __future__ import annotations

import chess
import chess.pgn

MIN_SPAN = 24        # plies the differential must hold
BAD_PAWNS = 3        # own pawns on bishop color to call it bad...
BAD_FIXED = 2        # ...of which at least this many are rammed
GOOD_PAWNS_MAX = 1   # good bishop: at most this many own pawns on its color


def sq_color(sq: int) -> bool:
    return bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[sq])


def side_rank(sq: int, side: bool) -> int:
    r = chess.square_rank(sq)
    return r if side == chess.WHITE else 7 - r


def pawn_facts(b: chess.Board, side: bool, color: bool) -> tuple[int, int, int]:
    """(own pawns on this color complex, of which rammed, max side-relative
    rank among the rammed ones; -1 if none)."""
    total = fixed = 0
    ram_rank = -1
    ahead = 8 if side == chess.WHITE else -8
    for sq in b.pieces(chess.PAWN, side):
        if sq_color(sq) != color:
            continue
        total += 1
        front = sq + ahead
        if 0 <= front < 64:
            p = b.piece_at(front)
            if p and p.piece_type == chess.PAWN and p.color != side:
                fixed += 1
                ram_rank = max(ram_rank, side_rank(sq, side))
    return total, fixed, ram_rank


def differential(b: chess.Board):
    """Returns (good_side, complex_color) if one same-complex bishop is good
    and the other bad, else None."""
    wb = list(b.pieces(chess.BISHOP, chess.WHITE))
    bb = list(b.pieces(chess.BISHOP, chess.BLACK))
    if len(wb) != 1 or len(bb) != 1 or sq_color(wb[0]) != sq_color(bb[0]):
        return None
    c = sq_color(wb[0])
    wt, wf, wr = pawn_facts(b, chess.WHITE, c)
    bt, bf, br = pawn_facts(b, chess.BLACK, c)
    w_bad = wt >= BAD_PAWNS and wf >= BAD_FIXED and side_rank(wb[0], chess.WHITE) < wr
    b_bad = bt >= BAD_PAWNS and bf >= BAD_FIXED and side_rank(bb[0], chess.BLACK) < br
    w_good = wt <= GOOD_PAWNS_MAX
    b_good = bt <= GOOD_PAWNS_MAX
    if b_bad and w_good and not w_bad:
        return chess.WHITE, c
    if w_bad and b_good and not b_bad:
        return chess.BLACK, c
    return None


def detect_bad_bishop(game):
    """First qualifying span: differential held MIN_SPAN plies with a harvest."""
    b = game.board()
    span_start = None
    state = None                      # (good_side, complex)
    harvests = []
    fixing_ply = None
    prev_fixed = 0
    for i, mv in enumerate(game.mainline_moves()):
        san = b.san(mv)
        mover = b.turn
        b.push(mv)
        d = differential(b)
        if d is not None and d == state:
            # inside a running span: look for harvest by the good side
            good, c = state
            if mover == good:
                pc = b.piece_at(mv.to_square)
                enemy_half = (chess.square_rank(mv.to_square) >= 4) == (good == chess.WHITE)
                if pc and pc.piece_type != chess.BISHOP and pc.piece_type != chess.PAWN \
                        and sq_color(mv.to_square) == c and enemy_half:
                    # infiltration: non-bishop piece to a c-colored square in enemy half,
                    # not attacked by an enemy pawn there
                    them = not good
                    if not any(b.piece_at(a) and b.piece_at(a).piece_type == chess.PAWN
                               and b.piece_at(a).color == them
                               for a in b.attackers(them, mv.to_square)):
                        harvests.append((i, san))
        elif d is not None:
            state, span_start, harvests = d, i, []
            # was this span opened by a fixing pawn ram just now?
            _, f, _ = pawn_facts(b, not d[0], d[1])
            fixing_ply = i if f > prev_fixed else None
        else:
            if state and span_start is not None and i - span_start >= MIN_SPAN and harvests:
                return _result(state, span_start, i - 1, harvests, fixing_ply, game)
            state, span_start, harvests = None, None, []
        if state:
            prev_fixed = pawn_facts(b, not state[0], state[1])[1]
    if state and span_start is not None:
        n = sum(1 for _ in game.mainline_moves())
        if n - span_start >= MIN_SPAN and harvests:
            return _result(state, span_start, n - 1, harvests, fixing_ply, game)
    return None


def _result(state, p0, p1, harvests, fixing_ply, game):
    good, c = state
    return {"plan": "good_vs_bad_bishop",
            "good_side": "white" if good == chess.WHITE else "black",
            "complex": "light" if c else "dark",
            "span": (p0, p1),
            "fixing_ply": fixing_ply,
            "harvests": harvests[:5],
            "result": game.headers.get("Result", "?")}


if __name__ == "__main__":
    import sys
    hits = n = 0
    good_wins = draws = 0
    examples = []
    with open("/Users/avismara/Development/chess-plans/data/gm_classical.pgn",
              encoding="latin-1") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            n += 1
            if n % 10000 == 0:
                print(f"scanned {n}, hits {hits}", flush=True)
            try:
                det = detect_bad_bishop(game)
            except Exception:
                continue
            if det is None:
                continue
            hits += 1
            exp = {"white": "1-0", "black": "0-1"}[det["good_side"]]
            if det["result"] == exp:
                good_wins += 1
            elif det["result"] == "1/2-1/2":
                draws += 1
            if len(examples) < 12:
                examples.append(
                    f'{game.headers.get("White","?")} - {game.headers.get("Black","?")} '
                    f'({game.headers.get("Event","?")}) {det["result"]} | good={det["good_side"]} '
                    f'{det["complex"]} span={det["span"]} harvests={[h[1] for h in det["harvests"]]}')
    print(f"\nhits: {hits}/{n} games")
    print(f"good-bishop side: won {good_wins}, drew {draws}, lost {hits - good_wins - draws}")
    print("\nsamples:")
    for e in examples:
        print(" ", e)
