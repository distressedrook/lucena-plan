"""position_read — the DETERMINISTIC user-facing position read.

Owner ruling 2026-07-24: "none of this goes to LLM. We must
deterministically present this." This module is what replaced
`PlansReadPrompt` in the backend's freeform plans route.

It is NOT `fact_sheet.build_fact_sheet`. That one is a GROUNDING
artifact built FOR a model — exhaustive, redundant and hedged on purpose,
so a narrator could select from it. A presentation has to do the
selecting itself. Concretely, this module owns the editorial decisions the
prompt used to delegate:

  - the RELIABILITY TIER IS NOW A CODE FILTER. `PlansReadPrompt` carried
    the rule "NEVER mention an entry with verified=false or null" as an
    instruction to a model — i.e. the one guarantee that stopped an
    unconfirmed candidate reaching a student was a sentence in a prompt.
    Here it is `if not p.get("verified"): continue`. It cannot be
    ignored, drifted from, or lost to a temperature setting.
  - selection and ordering, rather than dumping every fact and hoping the
    narrator picks well: capped weakness lists, verified plans only,
    material spoken only when it is actually doing something.
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
MAX_PLANS = 2


def _humanize_structure(name: str) -> str:
    return name.replace("_", " ")


def _plan_sentence(p: dict) -> str:
    """One verified plan, as a sentence. Timing rides inside the sentence
    (never as a bare label), and verdict codes/effect numbers/maia_frac
    never surface — they are internal jargon."""
    idea = (p.get("idea") or "").rstrip(".")
    timing = p.get("timing")
    if timing == "immediate":
        return f"{idea} — available right now."
    if timing == "developing":
        return f"{idea} — playable in the short term."
    if timing == "long-term":
        return f"{idea} — a longer-term idea, not for right now."
    return f"{idea}."


def _side_plans(plans: list | None) -> list[str]:
    """VERIFIED plans only — the reliability gate, in code."""
    out = []
    for p in plans or []:
        if not p.get("verified"):
            continue
        out.append(_plan_sentence(p))
        if len(out) >= MAX_PLANS:
            break
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
        head = f"{head}. Character: {char}"
    lines.append(head.rstrip(".") + ".")

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
        named = ", ".join(f"{_humanize_structure(s['name'])} (owned by "
                          f"{s['owner']})" for s in structs[:2])
        lines.append(f"Structure: {named}.")

    weak = post.get("weaknesses") or {}
    plans = post.get("plans") or {}
    body: list[str] = []
    for side in ("white", "black"):
        side_name = side.capitalize()
        ws = (weak.get(side) or [])[:MAX_WEAKNESSES]
        ps = _side_plans(plans.get(side))
        if not ws and not ps:
            continue
        if body:
            body.append("")             # blank line between side blocks
        body.append(f"**{side_name}**")
        for w in ws:
            body.append(f"- {w}")
        for p in ps:
            body.append(f"- Plan: {p}")

    if not body:
        return None                 # nothing verified and nothing to flag
    return "\n".join(lines) + "\n\n" + "\n".join(body)
