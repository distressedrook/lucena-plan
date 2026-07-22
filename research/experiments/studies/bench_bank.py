"""bench_bank — the banked-rollout lookup. The 4,000-position benchmark
already carries engine MultiPV lines (eng_shards) and Maia rollouts
(maia_shards); this indexes them by FEN so verify can gate plans with ZERO
new engine calls (user ruling 2026-07-22: 'this is why I have 4000
positions with this data — wire it').

    pvs, rolls = bank_lookup(fen)     # (engine PVs, Maia rollouts) or (None, None)

Lazy-loaded and cached; the index build reads the benchmark manifest once.
For positions NOT in the benchmark, both are None and the caller decides
whether to fall back to a live roll or simply stay silent.
"""
from __future__ import annotations

import glob
import json

BENCH = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/benchmark_v1.jsonl"
ENG = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/eng_shards"
MAIA = "/Users/avismara/Development/lucena/lucena-plans/research/experiments/maia_shards"

_fen2id: dict[str, str] | None = None
_eng: dict[str, list] | None = None
_maia: dict[str, list] | None = None


def _norm(fen: str) -> str:
    """Match on the board+side+castling+ep fields only — the half-move and
    full-move counters don't affect the rollout, and benchmark FENs may
    carry different counters than a caller's live FEN."""
    return " ".join(fen.split()[:4])


def _ensure_loaded() -> None:
    global _fen2id, _eng, _maia
    if _fen2id is not None:
        return
    _fen2id = {}
    for line in open(BENCH):
        if line.strip():
            r = json.loads(line)
            _fen2id[_norm(r["fen"])] = r["id"]
    _eng = {}
    for p in sorted(glob.glob(f"{ENG}/engine_*.jsonl")):
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                _eng[r["id"]] = r.get("pvs")
    _maia = {}
    for p in sorted(glob.glob(f"{MAIA}/bench_*.jsonl")):
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                _maia[r["id"]] = r.get("samples")


def bank_lookup(fen: str) -> tuple[list | None, list | None]:
    """(engine PVs, Maia rollouts) for `fen` from the banked benchmark, or
    (None, None) if the position isn't in it."""
    _ensure_loaded()
    _id = _fen2id.get(_norm(fen))
    if _id is None:
        return None, None
    return _eng.get(_id), _maia.get(_id)


def in_bank(fen: str) -> bool:
    _ensure_loaded()
    return _norm(fen) in _fen2id
