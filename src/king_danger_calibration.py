"""king_danger_calibration — P(catastrophe) for the king-safety composite.

`positional.py`'s `danger` score is a hand-authored composite (SAFETY_TABLE
+ shield/file/center penalties); `danger / DANGER_MAX` (`danger_bounded`,
2026-07-24) is a BOUNDED version of that formula, not a probability — its
"1.0" means "maxed out the formula", not "certain mate".

This module is the calibrated version, and it is deliberately LEVEL-
CONDITIONED (why it lives in lucena-plans, not the level-agnostic
lucena-core): "0 = safe, 1 = checkmated" is a claim about what happens
when someone actually defends, and defense quality depends on who's
defending. `p_catastrophe(danger)` reads P(the at-risk king is mated, or
that side's eval collapses below -700cp, within 16 plies) UNDER A ~1500
MAIA DEFENSE against engine-strength pressure — not under perfect play.

Provenance (2026-07-24, research/experiments/studies/king_danger_calibration/
calibrate_v2.py): v1 (engine defends itself) found ZERO catastrophes even
at danger=239 — the engine never blunders into its own mate, so that
counterfactual is uninformative for a coaching product. v2 replaced the
defender's moves with Maia's top policy choice at DEFENDER_ELO while the
attacker keeps playing the engine's best move (also the free eval read).
280 positions sourced from the residual-attribution study's interior
dataset (root-only benchmark positions starved the high end: only 2/300
were above danger=200). Fit: isotonic regression (monotone by
construction), n=278 after excluding 2 already-lost starts.

  positive rate   30.9%  (86/278)
  Brier           0.189  vs base-rate baseline 0.214 (beats it)
  spearman        +0.248 (p=3.0e-05)
  point-biserial  +0.227 (p=1.3e-04)

Reliability by bin (danger range: n, observed rate):
  0-40:    n=70   obs 8.6%
  40-100:  n=68   obs 35.3%
  100-200: n=70   obs 41.4%
  200-350: n=70   obs 38.6%  (this bin's own isotonic step is pooled with
                              the 260+ tail below it — PAVA merges
                              adjacent non-monotone blocks)

CAVEAT: danger >= 264 (the isotonic table's top step, ~0.75) rests on
only 10 samples — real per the monotone fit, not a bug, but treat as
"very high, imprecise" rather than a literal 75%. Do not speak a number
in that range to more than one significant figure.

This is ONE Maia-Elo slice (1500). It is not yet a per-level PROFILE the
way personal_sharpness.py is — extending it across levels (a defender
gets safer at their OWN danger threshold as rating rises, same as
sharpness) is future work, not yet run.

CONFOUND CHECK (2026-07-24, owner question: "if you make 1500 play
against an engine, he's getting checkmated 100% of the times regardless
of king safety"): the low-danger bin's 8.6% observed rate already argues
against the strong form, but two direct tests confirm the signal is
about THE KING specifically, not general 1500-vs-engine collapse:
  - standardized logistic coefficients, at-risk danger controlling for
    the ATTACKER's own king danger and |material imbalance|: at-risk
    +0.33 vs attacker-danger +0.08 (near-zero — rules out "both kings
    are just in chaos") vs material +0.28 (real, smaller, separate).
  - direct replay of 8 sampled catastrophes: 6/8 end in literal
    checkmate, all 8 show attacker checks in the terminal sequence
    (e.g. "D:Rg1 A:Qxh2+ D:Ke1 A:Qxg1#") — genuine mating attacks
    against the flagged king, not incidental material grabs elsewhere.

===============================================================================
THREE REGIMES, not one number (2026-07-24 owner correction: "if you make
1500 play against an engine, of course it will be less [dangerous] [in
real games] — the actual opponent isn't even 1500"). "P(catastrophe)"
depends entirely on who's attacking, not just who's defending:

  regime            attacker         defender    positive rate   n(pos)
  IF_PRESSED (v2)   Stockfish        Maia @1500     30.9%        86/278
  TYPICAL_1500      real human       real human      6.9%        11/159
                    (rating-matched, both sides 1450-1550, Lichess 2013-01)
  TYPICAL_GM        real GM          real GM         1.2%         3/245
                    (TWIC classical corpus, research/data/gm_classical.pgn)

Source (TYPICAL_1500): validate_real_games.py, matched-band run
(real_games_matched_report.json). Brier 0.058 vs 0.064 baseline;
spearman +0.243 (p=0.002), point-biserial +0.238 (p=0.0025) — properly
powered and significant. A FIRST pass with only one side rating-matched
(the opponent could be any rating) diluted the signal to spearman +0.107,
NOT significant — confirms the owner's point directly: attacker strength,
not just defender strength, sets the base rate.

Source (TYPICAL_GM): validate_gm_games_fast.py (gm_games_report.json).
Brier 0.0115 vs 0.0121 (base rate too low for Brier to be informative);
spearman +0.122 (p=0.056), point-biserial +0.126 (p=0.048) — DIRECTIONALLY
consistent with the other two regimes (same sign, same rough shape) but
NOT independently significant at n_pos=3. Do not oversell this: it is
compatible with "the danger-catastrophe relationship holds at every skill
level, just at falling magnitude" (the owner's hypothesis), but a 3-event
sample cannot rule out "GM technique fully absorbs geometric danger and
what we're seeing is noise" either. Spot-checked qualitatively real
(Gukesh,D vs Ding Liren among the 3 hits) — not a corpus artifact — but
statistically inconclusive pending a larger GM sample (rare events at
this level; would need several more corpus-months' worth of positions to
power a hard claim the way TYPICAL_1500 is powered).

The clean summary across all three: correlation sign and rough magnitude
(~0.12-0.25) is fairly stable across wildly different regimes; what
actually moves is the BASE RATE, which falls off a cliff with skill:
31% (weak defense, strong attack) -> 6.9% (matched amateurs) -> 1.2%
(matched GMs). "The king is unsafe" is evidence, never a verdict (this
mirrors positional.py's own stated design for the raw terms) — even the
worst simulated bin tops out at ~75%, and the strongest real signal
(TYPICAL_1500) tops out at 25%.
===============================================================================
"""
from __future__ import annotations

DEFENDER_ELO = 1500
N_CALIBRATION = 278
POSITIVE_RATE = 0.309
BRIER = 0.189
BASELINE_BRIER = 0.214
SPEARMAN = 0.248

# Isotonic step functions, compressed to change-points (piecewise constant
# between them — this IS what isotonic regression fits, not an
# approximation). (danger_from, p_catastrophe).

# IF_PRESSED: Maia@1500 defends, Stockfish attacks — a worst-case/ceiling
# read ("if this gets punished correctly"), NOT the typical real outcome.
_STEPS_IF_PRESSED = (
    (0, 0.0833), (6, 0.087), (38, 0.1605), (40, 0.3077), (74, 0.3088),
    (76, 0.3111), (114, 0.4124), (260, 0.4416), (262, 0.5), (264, 0.75),
)
DANGER_MAX_CALIBRATED = 264   # beyond this, the reading is the same
                              # small-sample (n=10) plateau — see CAVEAT

# TYPICAL_1500: real 1450-1550-vs-1450-1550 Lichess games (2013-01),
# real continuations. Properly powered (p=0.002) — the number to use for
# "what usually happens to a player like you", not the ceiling.
_STEPS_TYPICAL_1500 = (
    (0, 0.0), (50, 0.0208), (90, 0.0566), (92, 0.0924), (94, 0.1282),
    (212, 0.2222), (276, 0.2257), (278, 0.2326), (280, 0.2396),
    (282, 0.2465), (284, 0.25),
)

# TYPICAL_GM: real GM-vs-GM classical games (TWIC corpus), real
# continuations. DIRECTIONALLY consistent but NOT independently
# significant (n_pos=3, p~0.05) — carry with a wide-uncertainty caveat,
# do not present with the same confidence as the other two tables.
_STEPS_TYPICAL_GM = (
    (0, 0.0), (152, 0.0242), (154, 0.0364), (336, 0.0413), (338, 0.0513),
    (340, 0.0613), (342, 0.0712), (344, 0.0812), (346, 0.0912),
    (348, 0.1011), (350, 0.1111),
)

_TABLES = {
    "if_pressed": _STEPS_IF_PRESSED,
    "typical_1500": _STEPS_TYPICAL_1500,
    "typical_gm": _STEPS_TYPICAL_GM,
}
_CONFIDENCE = {
    "if_pressed": "validated",       # n=278, p=3e-5
    "typical_1500": "validated",     # n=159, p=0.002
    "typical_gm": "indicative",      # n=245 but only 3 positives, p~0.05
}


def _lookup(steps, danger: float) -> float:
    val = steps[0][1]
    for threshold, p in steps:
        if danger >= threshold:
            val = p
        else:
            break
    return val


def p_catastrophe(danger: float, regime: str = "if_pressed") -> float:
    """Calibrated P(catastrophe within 16 plies) for a raw king_safety
    `danger` score, under one of three regimes (see module docstring):
    'if_pressed' (Maia@1500 vs engine — ceiling), 'typical_1500' (real
    matched 1450-1550 games — the number for "a player like you"),
    'typical_gm' (real GM-vs-GM — indicative only, n_pos=3). Monotone
    non-decreasing within each regime by construction (isotonic fit)."""
    if regime not in _TABLES:
        raise ValueError(f"unknown regime {regime!r}: {sorted(_TABLES)}")
    return _lookup(_TABLES[regime], danger)


def p_catastrophe_labeled(danger: float, regime: str = "if_pressed") -> dict:
    """The speakable form: value + confidence tier (small-n tail flagged)."""
    p = p_catastrophe(danger, regime)
    low_n = regime == "if_pressed" and danger >= DANGER_MAX_CALIBRATED
    return {"p_catastrophe": round(p, 2), "regime": regime,
           "confidence": _CONFIDENCE[regime],
           "defender_elo": DEFENDER_ELO if regime == "if_pressed" else None,
           "low_n_tail": low_n,
           "precision": "one_sig_fig" if (low_n or regime == "typical_gm")
                        else "two_sig_fig"}


def p_catastrophe_profile(danger: float) -> dict:
    """All three regimes at once — the honest full picture: what happens
    if this gets punished correctly, vs what typically happens at 1500,
    vs what typically happens at GM level."""
    return {regime: p_catastrophe_labeled(danger, regime)
           for regime in _TABLES}
