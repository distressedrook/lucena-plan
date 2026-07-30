"""position_read — the DETERMINISTIC user-facing position read.

Owner ruling 2026-07-24: "none of this goes to LLM. We must
deterministically present this." This module is what replaced
`PlansReadPrompt` in the backend's freeform plans route.

It is NOT `fact_sheet.build_fact_sheet`. That one is a GROUNDING
artifact built FOR a model — exhaustive, redundant and hedged on purpose,
so a narrator could select from it. A presentation has to do the
selecting itself. Concretely, this module owns the editorial decisions the
prompt used to delegate:

  - the RELIABILITY TIER IS A CODE LABEL. `PlansReadPrompt` carried the
    rule "NEVER mention an entry with verified=false or null" as an
    instruction to a model — i.e. the one guarantee about what reached a
    student was a sentence in a prompt. Here the tier is computed from the
    verdict and PRINTED with the plan. It cannot be ignored, drifted from,
    or lost to a temperature setting.

    Owner ruling 2026-07-25: "surface all the plans that we detect" under
    three tags. Hiding an unconfirmed plan was costing real ideas — the
    minority attack confirms on only about half of the rolls of the SAME
    Carlsbad position (the longest-horizon family against 4 engine lines),
    so a student saw a correct plan flicker in and out. The honest fix is
    to show it and say what backs it, not to drop it:

      ENGINE_TAG     the plan appears in an eval-equal engine line here
                     (verdict CONFIRMED-SOUND / -SOUND-LATER)
      HUMAN_TAG      no engine line, but strong-human (Maia) rollouts from
                     THIS position play it (verdict HUMAN-TYPICAL)
      STRUCTURE_TAG  neither leg fired here: the plan is the corpus/theory
                     pattern for this structure, unverified in this
                     position. Includes the advisory tier (COMPLETE
                     DEVELOPMENT, SIMPLIFY — calibrated ideas that have no
                     engine contract to check at all).

    The tags are ordered strongest-evidence-first and never merged: a
    structural plan must never read like an engine-confirmed one.
  - selection and ordering, rather than dumping every fact and hoping the
    narrator picks well: capped weakness lists, plans ranked by evidence
    tier, material spoken only when it is actually doing something.
  - no model-facing artifacts: no opaque POSITION-<hash> id (that existed
    so a narrator could not cheat off the FEN), no "textbook theory may be
    drawn on" hint (an instruction to a narrator that no longer exists).

DELIBERATELY DROPPED with the LLM: the THEORY paragraph. It was the one
sanctioned place a model spoke from its own knowledge (named structures
only, per LLD §9). Deterministic code cannot invent it and must not fake
it — the structure is NAMED here and nothing more is claimed about it.
Authored structure blurbs would be the honest way to bring it back.

Input is `fact_sheet.post_verify_json(...)` (the verified artifact).
Output is markdown-lite text for the client.
"""
from __future__ import annotations

MAX_WEAKNESSES = 3

# The three evidence tags, strongest first. Wording is deliberate: the human
# leg is Maia rollouts FROM THIS POSITION (strong-human policy), not a claim
# about GM games — the GM corpus is what backs the STRUCTURE tag, so calling
# the Maia tier "GMs" would swap the two sources.
ENGINE_TAG = "Engine confirmed"
HUMAN_TAG = "Strong humans play this"
STRUCTURE_TAG = "The structure suggests this"

_ENGINE_VERDICTS = ("CONFIRMED-SOUND", "CONFIRMED-SOUND-LATER")


def _humanize_structure(name: str) -> str:
    return name.replace("_", " ")


def _tier(p: dict) -> int:
    """0 engine / 1 human / 2 structure — from the VERDICT, not `verified`
    (which pools the engine and human legs into one boolean)."""
    verdict = p.get("verdict")
    if verdict in _ENGINE_VERDICTS:
        return 0
    if verdict == "HUMAN-TYPICAL":
        return 1
    return 2


_TAGS = (ENGINE_TAG, HUMAN_TAG, STRUCTURE_TAG)


def _plan_sentence(p: dict) -> str:
    """One plan, as a sentence. Timing rides inside the sentence (never as a
    bare label), and verdict codes/effect numbers/maia_frac never surface —
    they are internal jargon. Timing is an ENGINE-leg fact (it is measured
    from where the idea lands in the line), so it is absent on the human and
    structure tiers and the sentence simply ends."""
    idea = (p.get("idea") or "").rstrip(".")
    timing = p.get("timing")
    if timing == "immediate":
        return f"{idea} — available right now."
    if timing == "developing":
        return f"{idea} — playable in the short term."
    if timing == "long-term":
        return f"{idea} — a longer-term idea, not for right now."
    return f"{idea}."


def _side_plans(plans: list | None,
                advisory: list | None = None) -> list[tuple[str, str]]:
    """EVERY detected plan as (tag, sentence), strongest evidence first
    (owner 2026-07-25). Order inside a tier is the artifact's own — corpus
    effect, descending — so the ranking within equal evidence is unchanged.
    Nothing is dropped and nothing is silently promoted: the tag is the
    whole reliability contract."""
    tiered: list[list[dict]] = [[], [], []]
    for p in plans or []:
        tiered[_tier(p)].append(p)
    # Advisory candidates carry no family, so there is no engine contract to
    # check for them — they are structural by construction, and they rank
    # against the unconfirmed family plans by the same corpus effect (they
    # carry `effect` for exactly this).
    tiered[2].extend(advisory or [])
    out = []
    for t in (0, 1, 2):
        # stable: equal effect keeps the artifact's own order
        for p in sorted(tiered[t], key=lambda e: -(e.get("effect") or 0.0)):
            out.append((_TAGS[t], _plan_sentence(p)))
    return out


def render(post: dict) -> str | None:
    """Deterministic position read from a post-verify sheet. Returns None
    when there is nothing worth showing (no verified plan and no
    weakness) — the caller then falls back to its plain read rather than
    printing an empty shell."""
    if not post:
        return None
    a = post.get("assessment") or {}
    lines: list[str] = []

    # 1. ASSESSMENT — the verdict plus what KIND of position it is. The
    # eval alone must never imply "quiet" (dynamism's founding ruling), so
    # the character verdict travels with it.
    verdict = (a.get("verdict") or "").rstrip(".")
    char = (a.get("character") or {}).get("summary")
    head = verdict or "Here's the position."
    if char:
        head = f"{head} — {char}"
    lines.append(head.rstrip(".") + ".")

    # 1b. THE COMMITTED RECOMMENDATION (owner ruling 2026-07-30: "I am OK
    # with the commit, as long as we tell the student why"). Spoken only when
    # the sheet grounded a why — the move is the top engine line's first move,
    # the why is the plan that line enacts (fact_sheet._recommendation_block).
    # A move without its why never renders; that is the ruling, not a style
    # choice. Measured basis: reading/LOG.md P11/P18 — naming the move is
    # +34pp for a weak reader; everything short of it measures ~0.
    rec = post.get("recommendation")
    if rec and rec.get("move") and rec.get("why"):
        # Wording is deliberately about the LINE, not the single move — that
        # is exactly what the attribution witnessed (the top line enacts the
        # plan; the move is its first step). "This move achieves X" would
        # claim more than the evidence.
        why = rec["why"].rstrip(".")
        lines.append(f"**Play {rec['move']}** — the strongest continuation "
                     f"pursues this plan: {why}.")

    # 2. MATERIAL — spoken only when it is actually saying something.
    # `standing` is the SETTLED (SEE-quiescent) sentence, never the raw
    # count (finding 27: the raw one said "Black is up a queen for a
    # bishop" about a queen White captured for free next move).
    ms = a.get("material_stability") or {}
    standing = ms.get("standing")
    if standing and standing != "material is even":
        line = standing[0].upper() + standing[1:]
        if ms.get("soft") and ms.get("why"):
            line += f" — though {ms['why'][0]}"
        lines.append(line.rstrip(".") + ".")

    # 3. STRUCTURE — named, and nothing more is claimed about it.
    structs = post.get("structure") or []
    if structs:
        named = ", ".join(f"{_humanize_structure(s['name'])} — "
                          f"{s['owner']}'s side" for s in structs[:2])
        lines.append(f"Structure: {named}.")

    weak = post.get("weaknesses") or {}
    plans = post.get("plans") or {}
    advisory = post.get("advisory") or {}
    body: list[str] = []
    for side in ("white", "black"):
        side_name = side.capitalize()
        ws = (weak.get(side) or [])[:MAX_WEAKNESSES]
        ps = _side_plans(plans.get(side), advisory.get(side))
        if not ws and not ps:
            continue
        if body:
            body.append("")             # blank line between side blocks
        body.append(f"**{side_name}**")
        for w in ws:
            body.append(f"- {w}")
        for tag, p in ps:
            body.append(f"- _{tag}_ — {p}")

    if not body:
        return None                 # nothing detected and nothing to flag
    return "\n".join(lines) + "\n\n" + "\n".join(body)
