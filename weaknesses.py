"""Weakness detectors — the fixed-target vocabulary for plan conversion.

The two-weaknesses experiment (experiments/weakness_census.py) established
that CREATION of weaknesses is flat as a predictor and HARVEST is a strong
monotone gradient; a complete census needs the full classical taxonomy.

Implemented (each pure geometry, side = the side OWNING the weakness):
  weak_pawns        isolated/backward pawn on a file where the enemy has no
                    pawn (rook-attackable), unsupportable by own pawns, not
                    passed
  entombed_bishops  bishop behind its own most advanced rammed same-color
                    pawn (>= 3 own pawns on its color, >= 2 rammed)
  occupied_outposts hole in own camp (a square no own pawn can EVER attack,
                    own 3rd-5th rank) currently held by an enemy knight or
                    bishop that is supported by an enemy pawn
  exposed_king      >= 2 of the files (king's file and neighbors) have no own
                    pawn — open lanes to the king; counts as ONE weakness

2026-07-22 breadth pass — the four roadmap detectors landed:
  passive_rooks     rooks stuck on the back two ranks with no open or
                    semi-open file to work (structurally jobless)
  weak_color_complex >= 2 same-color holes in the castled king's zone with
                    no own bishop of that color left to cover them
  back_rank_weak    castled king on rank 1 with zero luft (all frontal
                    squares own-pawn-blocked) while enemy heavies exist
  overextended_pawns pawns advanced past the 4th that no own pawn can ever
                    support (permanently unsupportable spearheads)
Plus backward_half_open: the sub-tag of weak_pawns that names THE classic
harvest target (backward pawn on the enemy's half-open file).
"""
from __future__ import annotations

import chess


def side_rank(sq: int, side: bool) -> int:
    r = chess.square_rank(sq)
    return r if side == chess.WHITE else 7 - r


def sq_color(sq: int) -> bool:
    return bool(chess.BB_LIGHT_SQUARES & chess.BB_SQUARES[sq])


def weak_pawns(b: chess.Board, side: bool) -> list[int]:
    """Own pawns on enemy-pawn-free files, unsupportable, not passed."""
    own = b.pieces(chess.PAWN, side)
    enemy = b.pieces(chess.PAWN, not side)
    efiles = {chess.square_file(s) for s in enemy}
    out = []
    for sq in own:
        f = chess.square_file(sq)
        if f in efiles:
            continue
        r = side_rank(sq, side)
        if any(chess.square_file(s) in (f - 1, f + 1)
               and side_rank(s, side) <= r for s in own if s != sq):
            continue
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r for s in enemy):
            continue                       # passed pawn: strength, not weakness
        out.append(sq)
    return out


def bishop_activity(b: chess.Board, side: bool, sq: int) -> dict:
    """Free squares this bishop attacks, split by board half — activity is
    RANKED by penetration (2026-07-22 user ruling: 'mobility inside its
    own camp < mobility in the opponent's camp'). weighted = 0.5*own +
    1.0*enemy (user-set weights): four own-half squares are a shuffler's
    scope (weighted 2); four enemy-half squares are a strong piece
    (weighted 4)."""
    own_half = enemy_half = 0
    for q in b.attacks(sq) & ~chess.SquareSet(b.occupied_co[side]):
        if side_rank(q, side) >= 4:
            enemy_half += 1
        else:
            own_half += 1
    return {"own": own_half, "enemy": enemy_half,
            "weighted": 0.5 * own_half + 1.0 * enemy_half}


def entombed_bishops(b: chess.Board, side: bool,
                     max_weighted: float = 2.5) -> list[int]:
    """Bishops buried behind >= 2 rammed same-color own pawns — WITH a
    penetration-weighted activity gate (2026-07-22 user rulings: 'bad
    bishopness should also be calculated by its immediate activity', then
    'ranked on how much of that mobility is in the opponent's camp'). The
    ram geometry alone misfired on a REAL position: an h3 bishop 'behind'
    rammed d5/e4 by rank while eyeing the open h3-c8 diagonal (4
    enemy-camp squares, weighted 5.5) — rank-relative-to-rams says buried,
    the board says it's White's best piece. A genuinely entombed bishop
    scores weighted <= 2.5 (the study case: an e3 bishop whose only air
    is f4+g5/h6, weighted exactly 2.5 — buried but with the classic
    Bg5/Bh6 extraction still on)."""
    out = []
    ahead = 8 if side == chess.WHITE else -8
    for sq in b.pieces(chess.BISHOP, side):
        if bishop_activity(b, side, sq)["weighted"] > max_weighted:
            continue
        c = sq_color(sq)
        total = fixed = 0
        ram_rank = -1
        for p in b.pieces(chess.PAWN, side):
            if sq_color(p) != c:
                continue
            total += 1
            front = p + ahead
            if 0 <= front < 64:
                pc = b.piece_at(front)
                if pc and pc.piece_type == chess.PAWN and pc.color != side:
                    fixed += 1
                    ram_rank = max(ram_rank, side_rank(p, side))
        if total >= 3 and fixed >= 2 and side_rank(sq, side) < ram_rank:
            out.append(sq)
    return out


def bad_bishop(b: chess.Board, side: bool, max_mob: int = 4) -> list[int]:
    """The bad bishop (2026-07-22, v2): EVERY bishop is checked
    independently against its own same-color-pawn/mobility criteria —
    the true Kmoch/Silman definition is mobility-based (a majority of the
    side's pawns sit on the bishop's color AND the bishop can barely
    move), and that's a fact about ONE piece regardless of how many
    bishops the side has. Broader than entombed_bishops (which requires
    >= 2 head-on rams and misses the common case).

    v1 (fires only with exactly one bishop) reasoned that a pair exempts
    a low-mobility bishop because 'the other bishop covers the missing
    color.' User correction (2026-07-22): that's not actually true in
    general — a second bishop off on an unrelated diagonal (e.g.
    outposted deep in the opponent's camp) doesn't compensate for the
    first one being boxed in at all. Fixed: check both/all bishops
    independently; a pair only genuinely exempts a bishop when the OTHER
    bishop ALSO fails this same test (i.e. isn't itself choked)."""
    out = []
    own_pawns = b.pieces(chess.PAWN, side)
    n = len(own_pawns)
    for sq in b.pieces(chess.BISHOP, side):
        c = sq_color(sq)
        on_color = sum(1 for p in own_pawns if sq_color(p) == c)
        # penetration-weighted (2026-07-22 ruling): own-camp squares don't
        # redeem a bad bishop the way enemy-camp squares do
        act = bishop_activity(b, side, sq)["weighted"]
        if on_color >= 3 and on_color * 2 >= n and act <= 2.5:
            out.append(sq)
    return out


def bishop_inside_chain(b: chess.Board, side: bool, sq: int) -> bool:
    """Is the bishop on `sq` INSIDE its own pawn chain (behind its
    same-color pawns) vs OUTSIDE (in front of / level with them)? Finding
    4: entombed/inside bishops carry the whole bad-bishop penalty (0.470);
    OUTSIDE bishops cost ~nothing (0.517) — still worth exchanging, but
    not the 'you're lost' problem. Geometry: compare the bishop's advance
    against its most-advanced same-color own pawn — behind it = inside."""
    c = sq_color(sq)
    ranks = [side_rank(p, side) for p in b.pieces(chess.PAWN, side)
             if sq_color(p) == c]
    if not ranks:
        return False
    return side_rank(sq, side) < max(ranks)


def bishop_confinement(b: chess.Board, side: bool, sq: int) -> dict:
    """Wall-vs-door classification of what hems a bishop in (2026-07-22
    user ruling: the Carlsbad c1 bishop isn't 'choked' — it stands BETWEEN
    two pawn chains and b2-b3 opens it in one tempo; a blocking own pawn
    is only a WALL when it is FIXED). For each of the bishop's four
    diagonal directions, the FIRST blocker is classified:

      open  — no blocker: a clear diagonal all the way to the edge.
      door  — an own pawn that can safely advance one step (front square
              empty and not enemy-pawn-controlled): one non-committal
              tempo opens the diagonal (b2-b3 -> Bb2, the Carlsbad case).
      wall  — an enemy pawn, or an own pawn that is FIXED (front square
              occupied, or its advance square is enemy-pawn-controlled).
      piece — a non-pawn blocker, either colour: pieces move; neither
              wall nor door.

    Returns {"open": int, "doors": [(pawn_sq, to_sq)], "walls": [sq],
    "pieces": [sq]}. Verdict guidance for callers: a low-mobility bishop
    with zero open diagonals and zero doors is genuinely CHOKED (the
    finding-4 0.470 penalty case); one with a door is merely UNDEVELOPED
    BETWEEN CHAINS — name the door move instead of calling it buried."""
    ahead = 8 if side == chess.WHITE else -8
    enemy = not side
    out = {"open": 0, "doors": [], "walls": [], "pieces": []}
    f0, r0 = chess.square_file(sq), chess.square_rank(sq)
    for df, dr in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        f, r = f0 + df, r0 + dr
        if not (0 <= f <= 7 and 0 <= r <= 7):
            continue    # zero-length ray (corner/edge) — no direction here
        blocker = None
        while 0 <= f <= 7 and 0 <= r <= 7:
            q = chess.square(f, r)
            if b.piece_at(q) is not None:
                blocker = q
                break
            f, r = f + df, r + dr
        if blocker is None:
            out["open"] += 1
            continue
        pc = b.piece_at(blocker)
        if pc.piece_type != chess.PAWN:
            out["pieces"].append(blocker)
            continue
        if pc.color == enemy:
            out["walls"].append(blocker)
            continue
        front = blocker + ahead
        fixed = (not 0 <= front < 64) or b.piece_at(front) is not None \
            or any(b.piece_type_at(a) == chess.PAWN
                   for a in b.attackers(enemy, front))
        (out["walls"] if fixed else out["doors"]).append(
            blocker if fixed else (blocker, front))
    return out


def castle_feasibility(b: chess.Board, side: bool, kingside: bool) -> dict | None:
    """Everything needed to name the CASTLE plan (2026-07-22, user-defined):
    can `side` still castle this way, what's in the way, and is the king's
    path currently covered. Returns None if the right doesn't exist or
    `side` has already castled.

    'blockers': (square, is_enemy) for every occupied square between king
                and rook — an enemy piece sitting there is a materially
                different situation from your own undeveloped piece (user
                ruling: name blockers, flag enemy ones specifically).
    'attacked': king-path squares (king's current square through its
                landing square, inclusive) currently attacked by the
                enemy — the check-through-check rule, checkable even
                when blockers make castling not yet legal."""
    ksq = b.king(side)
    if ksq is None:
        return None
    if kingside and not b.has_kingside_castling_rights(side):
        return None
    if not kingside and not b.has_queenside_castling_rights(side):
        return None
    rank = chess.square_rank(ksq)
    kf = chess.square_file(ksq)
    if kf != 4:                      # king already moved off e-file: not
        return None                  # a real castling situation
    between_files = [5, 6] if kingside else [1, 2, 3]
    path_files = [4, 5, 6] if kingside else [4, 3, 2]
    enemy = not side
    blockers = []
    for f in between_files:
        sq = chess.square(f, rank)
        pc = b.piece_at(sq)
        if pc:
            blockers.append((sq, pc.color == enemy))
    attacked = [chess.square(f, rank) for f in path_files
               if b.is_attacked_by(enemy, chess.square(f, rank))]
    return {"blockers": blockers, "attacked": attacked}


def _king_shelter_files(b: chess.Board, side: bool) -> set[int]:
    """Files of `side`'s king-shelter pawns: the king's file and the two
    adjacent, but only when the king is actually castled on that wing
    (advancing a shelter pawn there is a real concession)."""
    ksq = b.king(side)
    if ksq is None or side_rank(ksq, side) != 0:
        return set()
    kf = chess.square_file(ksq)
    if 3 <= kf <= 4:               # king still central: no wing shelter
        return set()
    return {f for f in (kf - 1, kf, kf + 1) if 0 <= f <= 7}


def strong_squares(b: chess.Board, side: bool) -> list[int]:
    """STRONG SQUARES for `side` in the enemy camp (attacker ranks 4-5):
    not currently attacked by any enemy pawn, and the ONLY enemy pawn that
    could ever advance to challenge it is an enemy KING-SHELTER pawn — so
    the challenge itself concedes king safety (the Ruy Lopez f5 square).
    Broader than is_hole (permanent hole), tighter than 'any square': it
    is exactly the outpost a wing pawn can only contest by weakening the
    king. Permanent holes are EXCLUDED here (they are already outposts);
    this returns only the king-shelter-contested extras."""
    enemy = not side
    shelter = _king_shelter_files(b, enemy)
    if not shelter:
        return []
    fwd_e = 8 if enemy == chess.WHITE else -8   # enemy pawn advance dir
    out = []
    for sq in chess.SQUARES:
        occ = b.piece_at(sq)
        if occ and occ.color == enemy:
            continue
        if not 4 <= side_rank(sq, side) <= 5:   # attacker's 5th-6th rank
            continue
        if chess.square_file(sq) in (0, 7):     # rim outposts are worthless
            continue
        # currently attacked by an enemy pawn? then not (yet) an outpost
        if any(pc and pc.piece_type == chess.PAWN and pc.color == enemy
               for pc in (b.piece_at(a) for a in b.attackers(enemy, sq))):
            continue
        if is_hole(b, sq, enemy):
            continue        # permanent hole -> already a normal outpost
        # An enemy pawn sits on sq - fwd_e +/- 1 to attack sq. A pawn can
        # still REACH that square if it's on the same file at/behind it in
        # the enemy's advance (side_rank <= that square's side_rank); one
        # already past can never retreat to attack sq.
        challengers = []
        for as_ in (sq - fwd_e - 1, sq - fwd_e + 1):
            if not (0 <= as_ < 64):
                continue
            if abs(chess.square_file(as_) - chess.square_file(sq)) != 1:
                continue
            af, asr = chess.square_file(as_), side_rank(as_, enemy)
            challengers += [p for p in b.pieces(chess.PAWN, enemy)
                            if chess.square_file(p) == af
                            and side_rank(p, enemy) <= asr]
        if challengers and all(chess.square_file(p) in shelter
                               for p in challengers):
            out.append(sq)
    return out


def is_hole(b: chess.Board, sq: int, side: bool) -> bool:
    """No own pawn can EVER attack sq (own pawns attack toward higher
    side-relative ranks): no own pawn on an adjacent file strictly behind."""
    f, r = chess.square_file(sq), side_rank(sq, side)
    return not any(chess.square_file(p) in (f - 1, f + 1)
                   and side_rank(p, side) < r
                   for p in b.pieces(chess.PAWN, side))


def occupied_outposts(b: chess.Board, side: bool) -> list[int]:
    """Enemy minors sitting on pawn-supported holes in our 3rd-5th rank."""
    out = []
    for pt in (chess.KNIGHT, chess.BISHOP):
        for sq in b.pieces(pt, not side):
            if not (2 <= side_rank(sq, side) <= 4):
                continue
            if not is_hole(b, sq, side):
                continue
            support = any(p.piece_type == chess.PAWN and p.color != side
                          for p in (b.piece_at(a) for a in b.attackers(not side, sq))
                          if p)
            if support:
                out.append(sq)
    return out


def exposed_king(b: chess.Board, side: bool) -> bool:
    ksq = b.king(side)
    if ksq is None:
        return False
    kf = chess.square_file(ksq)
    own_files = {chess.square_file(s) for s in b.pieces(chess.PAWN, side)}
    lanes = sum(1 for f in (kf - 1, kf, kf + 1)
                if 0 <= f <= 7 and f not in own_files)
    return lanes >= 2


def bishop_escape_route(b: chess.Board, side: bool,
                        sq: int) -> list[int] | None:
    """Can the bishop on `sq` EVER get outside its pawn chain? BFS over
    diagonal motion with pawns of BOTH colors as permanent walls and all
    non-pawn pieces transparent (pieces move; rammed pawns don't). Returns
    the shortest square-path to a square that classifies the bishop as
    'outside' (side-relative rank >= its most advanced rammed same-color own
    pawn), or None: the bishop is PERMANENTLY entombed in this skeleton."""
    c = sq_color(sq)
    ahead = 8 if side == chess.WHITE else -8
    ram_rank = -1
    for p in b.pieces(chess.PAWN, side):
        if sq_color(p) != c:
            continue
        front = p + ahead
        if 0 <= front < 64:
            pc = b.piece_at(front)
            if pc and pc.piece_type == chess.PAWN and pc.color != side:
                ram_rank = max(ram_rank, side_rank(p, side))
    if ram_rank < 0 or side_rank(sq, side) >= ram_rank:
        return []                       # already outside (or nothing rammed)
    walls = b.pieces(chess.PAWN, chess.WHITE) | b.pieces(chess.PAWN, chess.BLACK)
    from collections import deque
    prev = {sq: None}
    q = deque([sq])
    goal = None
    while q and goal is None:
        cur = q.popleft()
        f0, r0 = chess.square_file(cur), chess.square_rank(cur)
        for df, dr in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            f, r = f0 + df, r0 + dr
            while 0 <= f <= 7 and 0 <= r <= 7:
                nxt = chess.square(f, r)
                if nxt in walls:
                    break
                if nxt not in prev:
                    prev[nxt] = cur
                    if side_rank(nxt, side) >= ram_rank:
                        goal = nxt
                        break
                    q.append(nxt)
                f, r = f + df, r + dr
            if goal is not None:
                break
    if goal is None:
        return None
    path = []
    n = goal
    while n is not None:
        path.append(n)
        n = prev[n]
    return list(reversed(path))


def passive_rooks(b: chess.Board, side: bool) -> list[int]:
    """Own rooks on the back two ranks whose file holds an own pawn AND with
    no open/semi-open file anywhere for rooks to go to — structurally
    jobless, not just temporarily undeployed."""
    own_files = {chess.square_file(s) for s in b.pieces(chess.PAWN, side)}
    if len(own_files) < 8:
        return []                        # a free file exists: rooks have work
    enemy_files = {chess.square_file(s)
                   for s in b.pieces(chess.PAWN, not side)}
    if len(enemy_files) == 8:
        return []                        # fully closed-for-both (opening /
                                         # mutual gridlock): not yet a weakness
    out = []
    for sq in b.pieces(chess.ROOK, side):
        if side_rank(sq, side) <= 1 and chess.square_file(sq) in own_files:
            out.append(sq)
    return out


def weak_color_complex(b: chess.Board, side: bool) -> list[int]:
    """>= 2 same-color holes within distance 2 of the castled king, with no
    own bishop of that color left to cover them. Returns the hole squares."""
    ksq = b.king(side)
    if ksq is None or side_rank(ksq, side) > 1:
        return []
    kf = chess.square_file(ksq)
    if 3 <= kf <= 4:
        return []                        # uncastled: not this weakness
    own_bishop_colors = {sq_color(s) for s in b.pieces(chess.BISHOP, side)}
    for color in (True, False):
        if color in own_bishop_colors:
            continue
        holes = [sq for sq in chess.SQUARES
                 if sq_color(sq) == color
                 and chess.square_distance(sq, ksq) <= 2
                 and side_rank(sq, side) >= 1
                 and not b.piece_at(sq)
                 and is_hole(b, sq, side)]
        if len(holes) >= 2:
            return holes
    return []


def back_rank_weak(b: chess.Board, side: bool) -> bool:
    """Castled king on its back rank with ZERO luft (every frontal square
    own-pawn-blocked) while the enemy still has heavy pieces."""
    ksq = b.king(side)
    if ksq is None or side_rank(ksq, side) != 0:
        return False
    kf = chess.square_file(ksq)
    if 3 <= kf <= 4:
        return False
    if not (b.pieces(chess.ROOK, not side) | b.pieces(chess.QUEEN, not side)):
        return False
    ahead = 8 if side == chess.WHITE else -8
    for f in (kf - 1, kf, kf + 1):
        if not 0 <= f <= 7:
            continue
        front = chess.square(f, chess.square_rank(ksq)) + ahead
        pc = b.piece_at(front)
        if not (pc and pc.piece_type == chess.PAWN and pc.color == side):
            return False                 # an escape/luft square exists
    return True


def overextended_pawns(b: chess.Board, side: bool) -> list[int]:
    """Own pawns past the 4th rank that no own pawn can EVER support (no own
    pawn on an adjacent file behind them) and that are not passed — advanced
    spearheads that have outrun their supply line."""
    own = b.pieces(chess.PAWN, side)
    enemy = b.pieces(chess.PAWN, not side)
    out = []
    for sq in own:
        f, r = chess.square_file(sq), side_rank(sq, side)
        if r < 4:
            continue
        if any(chess.square_file(p) in (f - 1, f + 1)
               and side_rank(p, side) < r for p in own if p != sq):
            continue                     # supportable
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r for s in enemy):
            continue                     # passed: strength, not weakness
        out.append(sq)
    return out


def backward_half_open(b: chess.Board, side: bool) -> list[int]:
    """The classic harvest target: own weak pawns that sit on a file where
    the ENEMY has no pawn (their heavies x-ray it) while being backward —
    behind both neighbors. A sub-tag of weak_pawns."""
    own = b.pieces(chess.PAWN, side)
    out = []
    for sq in weak_pawns(b, side):
        f, r = chess.square_file(sq), side_rank(sq, side)
        nbrs = [p for p in own
                if chess.square_file(p) in (f - 1, f + 1) and p != sq]
        if nbrs and all(side_rank(p, side) > r for p in nbrs):
            out.append(sq)
    return out


def isolated_pawns(b: chess.Board, side: bool) -> list[tuple[int, bool]]:
    """Own pawns with NO own pawn on either adjacent file, excluding
    passers (a passed isolani is a candidate, not a weakness). Returns
    (square, half_open) — half_open = the enemy has no pawn on the file,
    i.e. their heavies can x-ray it directly (the besiege precondition
    is weaker than for backward pawns: an isolani is attackable from the
    front and sides regardless, so half_open is annotation, not gate)."""
    own = b.pieces(chess.PAWN, side)
    enemy = b.pieces(chess.PAWN, not side)
    files = {chess.square_file(p) for p in own}
    efiles = {chess.square_file(s) for s in enemy}
    out = []
    for sq in own:
        f, r = chess.square_file(sq), side_rank(sq, side)
        if {f - 1, f + 1} & files:
            continue
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r for s in enemy):
            continue                     # passed: strength, not weakness
        out.append((sq, f not in efiles))
    return out


def backward_pawns(b: chess.Board, side: bool) -> list[tuple[int, bool]]:
    """The KMOCH backward pawn (2026-07-22 ruling — the literature
    definition, standalone from weak_pawns): every neighbor-file own pawn
    is STRICTLY ahead (a level neighbor would guard the stop-square, and
    that's the 'little center', not backward), the stop-square is
    controlled by an enemy PAWN (the advance is what's being prevented —
    without this the pawn can simply walk forward and the 'weakness'
    evaporates), and the pawn is not passed. Returns (square, half_open)
    where half_open = the enemy has no pawn on the file — the classic
    besiege target; closed-file backward pawns are cramped but not
    file-attackable."""
    own = b.pieces(chess.PAWN, side)
    enemy = b.pieces(chess.PAWN, not side)
    efiles = {chess.square_file(s) for s in enemy}
    ahead = 8 if side == chess.WHITE else -8
    out = []
    for sq in own:
        f, r = chess.square_file(sq), side_rank(sq, side)
        nbrs = [p for p in own if p != sq
                and chess.square_file(p) in (f - 1, f + 1)]
        if not nbrs or any(side_rank(p, side) <= r for p in nbrs):
            continue                     # isolated (no nbrs) or level nbr
        stop = sq + ahead
        if not 0 <= stop < 64:
            continue
        if not any(pc and pc.piece_type == chess.PAWN
                   for pc in (b.piece_at(a)
                              for a in b.attackers(not side, stop))):
            continue                     # advance not pawn-prevented
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r for s in enemy):
            continue                     # passed: strength, not weakness
        out.append((sq, f not in efiles))
    return out


def _pawn_control(b: chess.Board, side: bool) -> dict[int, list[int]]:
    """square -> list of `side`'s pawn squares controlling it."""
    out: dict[int, list[int]] = {}
    for p in b.pieces(chess.PAWN, side):
        f, r = chess.square_file(p), chess.square_rank(p)
        dr = 1 if side == chess.WHITE else -1
        for df in (-1, 1):
            if 0 <= f + df <= 7 and 0 <= r + dr <= 7:
                out.setdefault(chess.square(f + df, r + dr), []).append(p)
    return out


def knight_route(b: chess.Board, side: bool, targets: set[int],
                 max_hops: int = 4,
                 respect_pawns: bool = True) -> list[int] | None:
    """Shortest geometric knight path from any of `side`'s knights to any
    square in `targets`, hopping only via squares not occupied by own pieces
    and (when respect_pawns) not attacked by ENEMY PAWNS. Returns the square
    path INCLUDING the start knight square, or None.

    A route is SKELETON-CONDITIONAL, not a prescription: it's computed
    against the CURRENT pawn structure, and multi-hop plans execute plies
    later, by which time blocking pawns may be gone or advanced (user
    ruling 2026-07-22). Callers should pair the pawn-safe route with the
    unconstrained one via knight_route_conditional(), which names WHICH
    pawns block the shortcut — 'c6-d4-e6-f4 opens if White's c3 pawn
    leaves' is the honest annotation."""
    from collections import deque
    enemy = not side
    pawn_ctrl = set(_pawn_control(b, enemy)) if respect_pawns else set()
    own_occ = {sq for sq in chess.SQUARES
               if (pc := b.piece_at(sq)) and pc.color == side}
    best = None
    for start in b.pieces(chess.KNIGHT, side):
        prev = {start: None}
        q = deque([(start, 0)])
        while q:
            cur, d = q.popleft()
            if d >= max_hops:
                continue
            for nxt in chess.SquareSet(chess.BB_KNIGHT_ATTACKS[cur]):
                if nxt in prev or nxt in own_occ:
                    continue
                # intermediate squares must be pawn-safe; the TARGET may be
                # pawn-covered only if it's a hole (targets are holes anyway)
                if nxt in pawn_ctrl and nxt not in targets:
                    continue
                prev[nxt] = cur
                if nxt in targets:
                    path = [nxt]
                    n = cur
                    while n is not None:
                        path.append(n)
                        n = prev[n]
                    path.reverse()
                    if best is None or len(path) < len(best):
                        best = path
                    break
                q.append((nxt, d + 1))
    return best


def knight_route_conditional(b: chess.Board, side: bool,
                             targets: set[int], max_hops: int = 4):
    """(safe_route, shortcut_route, blockers) — the pawn-safe route under
    the CURRENT skeleton, plus the shorter unconstrained route when one
    exists, with the enemy pawn squares that currently block it. blockers
    empty when the safe route is already shortest. Either route may be
    None."""
    safe = knight_route(b, side, targets, max_hops, respect_pawns=True)
    free = knight_route(b, side, targets, max_hops, respect_pawns=False)
    if free is None or (safe is not None and len(free) >= len(safe)):
        return safe, None, []
    ctrl = _pawn_control(b, not side)
    blockers = sorted({p for sq in free[1:-1] for p in ctrl.get(sq, [])})
    return safe, free, blockers


def census(b: chess.Board, side: bool) -> dict:
    """All fixed targets in `side`'s camp; 'total' is the census number."""
    wp = weak_pawns(b, side)
    eb = entombed_bishops(b, side)
    op = occupied_outposts(b, side)
    ek = exposed_king(b, side)
    pr = passive_rooks(b, side)
    cc = weak_color_complex(b, side)
    br = back_rank_weak(b, side)
    ox = overextended_pawns(b, side)
    return {"weak_pawns": wp, "entombed_bishops": eb,
            "occupied_outposts": op, "exposed_king": ek,
            "passive_rooks": pr, "weak_color_complex": cc,
            "back_rank_weak": br, "overextended_pawns": ox,
            "backward_half_open": backward_half_open(b, side),
            "total": (len(wp) + len(eb) + len(op) + (1 if ek else 0)
                      + len(pr) + (1 if cc else 0) + (1 if br else 0)
                      + len(ox))}
