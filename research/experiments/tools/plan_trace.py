"""plan_trace — ply-by-ply deterministic plan accounting for a whole game.

For EVERY position along the game:
  - which plan triggers are ON for each side (the standing "offers")
Joined with one parse of the full delta stream:
  - which plans were EXECUTED, at which ply, at what stage
Verdict per (side, plan): offered@ply -> executed@ply (lag) / never executed.
Also reports emergent executions (plans executed without a recorded trigger
onset — grammar/trigger mismatches worth inspecting).

Pure geometry; same input -> same trace, every run.

    ./plan_trace.py <pgn-file> [game-index]
"""
from __future__ import annotations

import sys

import chess
import chess.pgn

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-plans/src")
from plan_diff import snapshot, parse_line, _minority_pre
from weaknesses import weak_pawns, entombed_bishops
from suggest import CANDIDATE_FAMILIES

FAM_TO_LABEL = {f: lab for lab, fams in CANDIDATE_FAMILIES.items() for f in fams}


def triggers(b: chess.Board) -> set[tuple[str, str]]:
    s = snapshot(b)
    out = set()
    for t, side in (("W", chess.WHITE), ("B", chess.BLACK)):
        o = "B" if t == "W" else "W"
        enemy = not side
        if weak_pawns(b, enemy):
            out.add((t, "HARVEST"))
        if entombed_bishops(b, enemy):
            out.add((t, "KEEP IT ENTOMBED"))
        if entombed_bishops(b, side):
            out.add((t, "ESCAPE"))
        opp_q = s[f"{o}.king_file"] <= 2 and s[f"{t}.king_file"] >= 4
        opp_k = s[f"{t}.king_file"] <= 2 and s[f"{o}.king_file"] >= 5
        if (opp_q or opp_k) and s[f"{o}.castled"]:
            out.add((t, "STORM"))
        if not opp_q and _minority_pre(b, side):
            out.add((t, "MINORITY ATTACK"))
        if s[f"{t}.castled"] and not s[f"{o}.castled"] \
                and (s[f"{o}.can_castle"] or s[f"{o}.king_central"]):
            out.add((t, "BREAK OPEN THE CENTER"))
            out.add((t, "DENY CASTLING"))
        if s[f"{t}.n_passers"]:
            out.add((t, "PUSH THE PASSER"))
        # breadth-pass triggers (2026-07-22)
        from plan_diff import _chain_bases
        if _chain_bases(s[f"{o}.pawns"], s[f"{t}.pawns"],
                        enemy == chess.WHITE):
            out.add((t, "ATTACK THE CHAIN BASE"))
        for wing in ("q", "k"):
            if s[f"{t}.{wing}_n"] > s[f"{o}.{wing}_n"] >= 1:
                out.add((t, "ROLL THE MAJORITY"))
                break
        if s[f"{o}.minority_pre"]:
            out.add((t, "BLOCK THE MINORITY ATTACK"))
        if s[f"{t}.space"] - s[f"{o}.space"] >= 4:
            out.add((t, "SQUEEZE"))
        own_f = s["wf"] if t == "W" else s["bf"]
        if any(f not in own_f for f in range(8)):
            out.add((t, "ROOK ACTIVATION"))
        if s[f"{t}.backward"]:
            out.add((t, "FREE THE BACKWARD PAWN"))
        # outpost trigger: any prime hole in enemy camp
        from weaknesses import is_hole, side_rank
        for sq in chess.SQUARES:
            if b.piece_at(sq):
                continue
            if not 1 <= chess.square_file(sq) <= 6:
                continue
            if 4 <= side_rank(sq, side) <= 5 and is_hole(b, sq, enemy):
                out.add((t, "OUTPOST"))
                break
    return out


def plan_trace(game) -> list[str]:
    start = game.board()
    moves = list(game.mainline_moves())
    b = start.copy()
    onset = {}                       # (t,label) -> first ply trigger ON
    active_last = {}                 # (t,label) -> last ply seen ON
    for i, mv in enumerate(moves):
        b.push(mv)
        for key in triggers(b):
            onset.setdefault(key, i)
            active_last[key] = i
    executed = parse_line(start, moves, horizon=len(moves), tail=6)
    events = []                      # (ply, t, label, family, stage)
    for pl in executed:
        lab = FAM_TO_LABEL.get(pl["name"])
        events.append((pl["ply"], pl["side"], lab or pl["name"],
                       pl["name"], pl["stage"]))
    events.sort()
    L = [f"== PLAN TRACE ({len(moves)} plies) =="]
    L.append("-- execution timeline --")
    for ply, t, lab, fam, stage in events:
        off = onset.get((t, lab))
        lag = f", offered since ply {off} (lag {ply - off})" if off is not None \
            else " [EMERGENT: no trigger onset recorded]"
        L.append(f"  ply {ply:>3}: {('White' if t == 'W' else 'Black')} "
                 f"{fam} [{stage}]{lag}")
    L.append("-- offers never executed --")
    done = {(t, lab) for _, t, lab, _, _ in events}
    for (t, lab), off in sorted(onset.items(), key=lambda kv: kv[1]):
        if (t, lab) not in done:
            L.append(f"  {('White' if t == 'W' else 'Black')} {lab}: offered "
                     f"ply {off}-{active_last[(t, lab)]}, never executed")
    return L


if __name__ == "__main__":
    path = sys.argv[1]
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    with open(path) as f:
        for _ in range(idx + 1):
            game = chess.pgn.read_game(f)
    print(f"{game.headers.get('White','?')} - {game.headers.get('Black','?')} "
          f"{game.headers.get('Result','')}")
    print("\n".join(plan_trace(game)))


# ---------------------------------------------------------------- decision points

def decision_points(game, top=6):
    """Plies where the DECISION MENU changed: candidate-plan sets (either
    side), structure set, or castling configuration. Weighted by the corpus
    price of plans entering/leaving. Deterministic."""
    from plan_diff import PRICES
    start = game.board()
    moves = list(game.mainline_moves())
    b = start.copy()
    prev_trig = triggers(b)
    prev_struct = frozenset(snapshot(b)["structures"])
    prev_kings = (snapshot(b)["W.king_file"], snapshot(b)["B.king_file"])
    LABEL_PRICE = {"HARVEST": 8.4, "OUTPOST": 8.3, "ESCAPE": 6.0,
                   "KEEP IT ENTOMBED": 4.9, "MINORITY ATTACK": 4.0,
                   "BREAK OPEN THE CENTER": 5.0, "DENY CASTLING": 3.0,
                   "STORM": 2.0, "PUSH THE PASSER": 4.0}
    events = []
    for i, mv in enumerate(moves):
        san = b.san(mv)
        b.push(mv)
        s = snapshot(b)
        trig = triggers(b)
        struct = frozenset(s["structures"])
        kings = (s["W.king_file"], s["B.king_file"])
        w, notes = 0.0, []
        for t, lab in trig - prev_trig:
            w += LABEL_PRICE.get(lab, 2.0)
            notes.append(f"+{('W' if t == 'W' else 'B')}:{lab}")
        for t, lab in prev_trig - trig:
            w += LABEL_PRICE.get(lab, 2.0)
            notes.append(f"-{('W' if t == 'W' else 'B')}:{lab} (window closed)")
        if struct != prev_struct:
            w += 3.0
            gained = {n for n, _ in struct} - {n for n, _ in prev_struct}
            lost = {n for n, _ in prev_struct} - {n for n, _ in struct}
            if gained:
                notes.append("entered " + ",".join(gained))
            if lost:
                notes.append("left " + ",".join(lost))
        if kings != prev_kings:
            w += 2.0
            notes.append("king address changed")
        if w > 0:
            events.append((w, i, san, "; ".join(notes)))
        prev_trig, prev_struct, prev_kings = trig, struct, kings
    events.sort(key=lambda e: -e[0])
    picked = sorted(events[:top], key=lambda e: e[1])
    return [f"  ply {i:>3} ({san:>6}, weight {w:.1f}): {n}"
            for w, i, san, n in picked]
