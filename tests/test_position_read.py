"""The read surfaces EVERY detected plan, tagged by evidence tier (owner
2026-07-25: "surface all the plans that we detect ... Engine Confirmed, GMs
tend to do this (human lines), structure suggests this").

The old rule dropped anything the verify gate did not confirm, which cost
real ideas: the minority attack confirms on only ~half the rolls of the same
Carlsbad position, so a correct plan flickered in and out. The tag — never a
filter — is now the reliability contract.
"""

import position_read as pr


def _post(white_plans, white_advisory=None):
    return {
        "assessment": {"verdict": "roughly equal"},
        "weaknesses": {"white": [], "black": []},
        "plans": {"white": white_plans, "black": []},
        "advisory": {"white": white_advisory or [], "black": []},
    }


def test_the_three_tags_come_from_the_verdict():
    plans = [
        {"idea": "Minority attack", "verdict": "CONFIRMED-SOUND-LATER",
         "verified": True, "timing": "long-term"},
        {"idea": "Knight to e5", "verdict": "HUMAN-TYPICAL", "verified": True},
        {"idea": "Outpost plan", "verdict": "NOT-IN-BEST-LINES",
         "verified": False},
    ]
    out = pr._side_plans(plans)
    assert [t for t, _ in out] == [pr.ENGINE_TAG, pr.HUMAN_TAG,
                                   pr.STRUCTURE_TAG]
    # timing rides inside the engine-tier sentence, and nothing else leaks
    assert out[0][1] == "Minority attack — a longer-term idea, not for right now."
    assert out[1][1] == "Knight to e5."
    assert "NOT-IN-BEST-LINES" not in out[2][1]


def test_nothing_is_dropped_and_strongest_evidence_leads():
    # Arrival order is corpus effect, descending; the tiers re-order it so a
    # structural 8.3 never outranks an engine-confirmed 4.0 — but both print.
    plans = [
        {"idea": "Outpost plan", "verdict": "NOT-IN-BEST-LINES"},
        {"idea": "Knight to e5", "verdict": "UNSUPPORTED"},
        {"idea": "Minority attack", "verdict": "CONFIRMED-SOUND"},
        {"idea": "Rook activation", "verdict": "CONFIRMED-SOUND"},
    ]
    out = pr._side_plans(plans)
    assert len(out) == 4                      # no cap: every detected plan
    assert [i.rstrip(".") for _, i in out] == [
        "Minority attack", "Rook activation", "Outpost plan", "Knight to e5"]


def test_advisory_candidates_are_structural_by_construction():
    # No family -> no engine contract to check -> the structure tag, always.
    out = pr._side_plans([], [{"idea": "Complete development",
                               "evidence": "factual geometry", "effect": 4.5}])
    assert out == [(pr.STRUCTURE_TAG, "Complete development.")]


def test_advisory_ranks_against_family_plans_inside_the_structure_tier():
    # Both are structural — an advisory idea with the bigger corpus effect
    # must not sort below every unconfirmed family plan just because it came
    # from the other list.
    plans = [{"idea": "Rook activation", "verdict": "NOT-IN-BEST-LINES",
              "effect": 2.6}]
    advisory = [{"idea": "Complete development", "evidence": "geometry",
                 "effect": 4.5}]
    assert [i.rstrip(".") for _, i in pr._side_plans(plans, advisory)] == [
        "Complete development", "Rook activation"]


def test_an_unverified_plan_now_reaches_the_read():
    text = pr.render(_post([{"idea": "Outpost plan",
                             "verdict": "NOT-IN-BEST-LINES",
                             "verified": False}]))
    assert text is not None                   # used to render None here
    assert f"_{pr.STRUCTURE_TAG}_ — Outpost plan." in text
    assert "**White**" in text


def test_the_human_tag_does_not_claim_gm_games():
    # The human leg is Maia rollouts from THIS position; the GM corpus is
    # what backs the STRUCTURE tag. Swapping the two would misattribute the
    # evidence, so the wording stays off "GM".
    assert "GM" not in pr.HUMAN_TAG
    assert pr.HUMAN_TAG != pr.STRUCTURE_TAG
