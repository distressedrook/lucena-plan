# Known issues

Open bugs that are understood but not yet fixed. Each entry: what's wrong,
where, why it hasn't bitten yet (if masked), and the fix.

## 1. `holes_in()` mislabels every deep hole as an OUTPOST (2026-07-22)

**Where:** `suggest.py::holes_in()` and the OUTPOST candidate loop in
`build_menus()`.

**What's wrong:** a hole is any square the enemy can never guard with a
pawn. An OUTPOST is a hole *defended by a friendly pawn* — that pawn
support is what lets a piece stay there when challenged. The detector
surfaces every deep hole as an "OUTPOST PLAN" with no friendly-pawn-support
check, so it names bogus outposts on squares where the planted piece can't
be maintained.

**Evidence** (FEN `1r4k1/5pp1/3p1n1p/prpP4/1q3P2/R3PBP1/RPQ2P2/6K1 w - - 2
26`): surfaced "plant White's bishop on c6" (only c6 is real — d5 supports
it) alongside b6/a4/a6 (no White pawn supports any) and, for Black,
b3/d3/h3 (no Black pawn supports any). Only c6 is a genuine outpost; the
rest are just holes.

**Why it hasn't bitten (masked):** the fact-sheet PLAN section is now
VERIFY-gated (see `fact_sheet.py::_plan_lines`), so unsupported "outposts"
get dropped downstream as `NOT-IN-BEST-LINES` before reaching the student.
The bug is invisible in the fact sheet but still present in `suggest.py`'s
raw menu output and anything else that consumes it unverified.

**Fix:** gate the OUTPOST candidate on friendly-pawn support — a hole with
no supporting own pawn is at most a traversal square, not an outpost.
Compute support as: an own pawn sits one rank behind the hole, on an
adjacent file (i.e. the pawn attacks the hole square). Only holes that pass
become OUTPOST candidates; the rest can still be reported as holes in the
WEAKNESSES section but never as outpost *plans*.

## 2. `knight_route()` is pawn-safe but not piece-safe (2026-07-22)

**Where:** `weaknesses.py::knight_route()` / `knight_route_conditional()`.

**What's wrong:** the BFS avoids squares controlled by enemy *pawns* but
not by enemy *pieces*, so it produces routes that walk a knight through /
onto squares defended by major pieces (it gets captured there).

**Evidence** (same FEN): route `f6-e4-d2-b3` passes through d2 (guarded by
Qc2) and lands on b3 (guarded by Qc2 *and* Ra3).

**Status:** lower priority — the destination in the evidence case (b3) is
also a non-outpost (issue #1), so fixing #1 removes this particular
surfaced route. The route generator is intentionally "skeleton-
conditional" (pawn structure only, since pieces move), so making it fully
piece-aware is a design change, not an obvious fix. Revisit if piece-
defended routes surface on *real* (supported) outpost targets after #1 is
fixed.

## 3. EVERY weakness in the WEAKNESSES section states the fact but never
   says whether it's currently being EXPLOITED (2026-07-22, generalized)

**Where:** `fact_sheet.py::_weakness_lines`, ALL of it — not just
`weak_color_complex`. Weak pawns, holes, isolated/backward/doubled/
overextended pawns, bad bishops, passive rooks, back-rank weakness — every
line in WEAKNESSES FOR WHITE/BLACK is a flat geometric assertion with no
per-position check against the banked lines. Some of these already have a
matching PLAN family (weak pawns -> harvest, backward pawn -> free-it,
bad bishop -> free/exchange) and so get an indirect signal ONLY if that
plan happens to also appear in PLAN FOR X — but the WEAKNESS line itself
never says so, and weaknesses with NO plan family (`passive_rooks`,
`back_rank_weak`, holes generally, `weak_color_complex`) get no signal at
all, direct or indirect.

**User's framing (2026-07-22):** "Weaknesses are brought up, they need to
be verified if they are being exploited." Every weakness statement should
carry a verdict — exploited-in-the-banked-lines vs. real-but-currently-
latent — not just an unqualified fact.

**What's wrong:** the sheet states "A weak light-square complex around
White's king on g2, f3, h3" as a flat fact, with no signal about whether
the banked engine/Maia lines actually do anything with it FROM THIS
POSITION. A student (or narrating model) reading a bare weakness
statement can't tell latent-but-real from currently-actionable — and
without a hint either way, the natural reading skews toward "this is a
target right now," which may be wrong.

**Evidence** (Round 8 position, `POSITION-514df0af36`): the sheet named
Black's king weak light-square complex on g6/f7/h7. Manually consulting
the banked lines (ad hoc, not part of the sheet): 0/4 engine PVs land a
White piece there or build real pressure on it within the horizon, and
only 1/16 Maia rollouts do (a single opportunistic `Qxg6+` in one line,
not a repeated pattern). So on THIS position, strong play does not
currently exploit it — but the sheet doesn't say that; it just states the
weakness and lets the reader assume actionability by default.

**What the coach should say instead** (user's own phrasing): *"Though
there are light-square weaknesses, on strong play they are not
exploitable right now — but always be on the lookout to exploit them."*
I.e. the SAME bare-weakness statement, plus an explicit exploitability
verdict read from the banked lines (exploited-now / not-currently-but-
latent), not a silent omission either way.

**Fix (not yet built), generalized:** a per-weakness banked-line
exploitation check, applied uniformly across ALL of `_weakness_lines` —
not bolted onto individual weakness types one at a time. Two cases:
  - **Weakness HAS a plan family** (weak pawns/harvest, backward-pawn/
    free-it, bad-bishop/free-or-exchange): the WEAKNESS line should cite
    the SAME verdict already computed for the matching PLAN candidate
    (`_CONFIRMED` vs not), rather than silently duplicating/ignoring work
    already done in `_plan_lines`.
  - **Weakness has NO plan family** (holes generally, `passive_rooks`,
    `back_rank_weak`, `weak_color_complex`, `overextended_pawns` outside
    its harvest angle): needs the generic "does any banked engine-equal
    line / Maia rollout attack or occupy this square/piece within the
    horizon" check (prototyped ad hoc for the h4-knight and g6/f7/h7
    questions this session — factor into one reusable function against
    `bench_bank.bank_lookup()`), then append the two-mode template:
    exploited-in-strong-play vs. real-but-latent (user's phrasing: "on
    strong play, they are not exploitable, but always be on the lookout
    to exploit them").
  - Applies per side/per position — the same weakness can be exploited in
    one position and dormant in another, so this cannot be a static label
    per weakness type; it must be computed fresh from the bank every time
    the sheet is built.

## 4. Pawn breaks in POSITION READ are pure geometry — never checked
   against the engine (2026-07-22)

**Where:** `fact_sheet.py::_skeleton_lever_words` (the "White's next pawn
break available: ..." / "Black's next pawn break available: ..." lines),
sourced from `suggest.py::pawn_decomposition()`'s lever computation.

**What's wrong:** a listed break is only a geometric fact — "this pawn CAN
push and it attacks that square" — with zero verification that the break
is actually sound (doesn't just hang the pawn, doesn't lose material,
isn't refuted tactically). Unlike PLAN candidates (which are VERIFY-gated
against the banked engine/Maia lines before they're allowed to render),
every pawn break is listed unconditionally. A break that's geometrically
real but a losing blunder reads exactly the same as one the engine
actually plays.

**Why it matters:** this is the same class of problem the whole
VERIFY-gate architecture exists to solve (see the c6/b3 outpost incident
that motivated wiring PLAN FOR X to the bank) — but the fix was only ever
applied to the PLAN section, not to POSITION READ's break list, so the
same failure mode is still live there.

**Fix (not yet built):** for each listed break, check the banked lines
(same `bank_lookup()` pattern as everything else this session): does the
break move appear in an eval-equal engine PV, or is it at least
eval-neutral if actually played? If a break is geometrically available
but never appears in any eval-equal line (or drops eval sharply if forced
in a counterfactual roll), the line should say so — e.g. "(not favored by
strong play)" — rather than presenting every geometric break as
equally live. Mirrors issue #3's fix in spirit: geometry states the fact,
the bank supplies the verdict.

## 5. `bishop_escape_route()` treats OWN pawns as permanent walls, missing
   the real escape route when it goes through a trade (2026-07-22)

**Where:** `weaknesses.py::bishop_escape_route()`.

**What's wrong:** the BFS's `walls` set is `white_pawns | black_pawns` —
ALL pawns, including the bishop's own side's pawns that are sitting on
squares the bishop could legitimately reach IF that pawn gets traded off.
A pawn that's fixed by a ram (can never move) is a genuine permanent wall;
a pawn that's simply sitting there for now, and gets exchanged a few
moves later, is not — but the algorithm can't tell the difference, so it
routes the bishop around every own pawn as if none of them will ever move.

**Evidence** (`n1883_a30`, FEN `r4rk1/p4pbp/1qp1p1p1/3pP3/2pP4/QPPbB3/
P2N1PPP/R3R1K1 w - - 0 16`): the sheet claimed White's e3 bishop escapes
via "e3-g5". Checked the banked lines directly — that route appears in
**zero** of 4 engine PVs and **zero** of 16 Maia rollouts. What actually
happens: the bishop's own d4 pawn (a permanent wall to the BFS) gets
traded off (`...cxd4`), and the bishop **recaptures on d4** — 11/13
Maia rollouts that move the bishop go there, and engine PV2 does too.
Other real lines detour via c5/a7/a3. The underlying PLAN itself is
genuinely sound (`bad_bishop_escape` verifies `CONFIRMED-SOUND-LATER`,
Maia-typical 3/16, fires at ply 6) — it's specifically the printed
GEOMETRIC ROUTE that's fiction. Same family of bug as issue #2
(`knight_route` piece-blind), but the failure mode here is sharper: not
just "walks through a defended square" but "never considers the single
most common real escape mechanism" (capture-driven repositioning).

**Fix (not yet built):** distinguish RAMMED own pawns (genuinely
immovable — these stay walls) from ordinary own pawns (potential
capture/trade squares — these should be walkable IF a plausible
capture sequence gets the enemy piece there, or at minimum flagged as
"conditional on a trade," mirroring `knight_route_conditional()`'s
safe-route-plus-shortcut pattern already built for knights).
**Update 2026-07-22 (later the same day):** the wall-vs-door primitive
now EXISTS — `weaknesses.bishop_confinement()` classifies a blocking own
pawn as a fixed WALL (front square occupied or enemy-pawn-controlled) vs
a DOOR (can safely advance one step), built for the hemmed-bishop
weakness wording (the Carlsbad c1 case). The escape-route BFS here
should reuse that same fixed-pawn test for its `walls` set instead of
treating every pawn as permanent.

**LARGELY RESOLVED 2026-07-22 (evening), at the REPORTING layer:** the
sheet no longer prints the BFS route as fact anywhere. `verify_plan`
gained `track=` (forward-follow a named piece through the firing
eval-equal lines — `_journey_from`); both the entombed-bishop WEAKNESS
line and the ESCAPE plan line now print the OBSERVED extraction
journeys ('the engine's lines extract it: e3-c5-d6 or e3-g5-e7-d6' on
this issue's own evidence FEN), a lines-play-the-TRADE variant when
`bad_bishop_trade` is what fires, and the geometric route survives only
as an explicitly-unverified aside ('...though the engine's lines don't
play the extraction here'). The BFS itself is still pawn-wall-naive —
fixing THAT (via bishop_confinement's wall test) now only improves the
unverified-aside fallback, so it's low priority. Cheaper
partial fix: when the BFS-found route diverges from what the banked
lines actually show (which `verify_plan` already computes for the
family), don't print the geometric route as-is — either suppress it or
replace it with the real observed escape square(s) from the bank, the
same "read it from the lines, not from geometry alone" principle behind
issues #3/#4 and the whole VERIFY-gate architecture.

## 6. No DEVELOPMENT plan — undeveloped minor pieces are never surfaced
   (2026-07-22, user-defined)

**Where:** missing entirely — no detector, no `plan_diff` family, no
`suggest.py` candidate. Confirmed by grep: nothing in the codebase
currently reasons about "pieces still on their home squares."

**What's wrong:** in an opening/early-middlegame position with an
undeveloped knight or bishop, the fact sheet has nothing to say about it
— WEAKNESSES doesn't flag it, PLAN doesn't recommend fixing it. This is
one of the most basic, most immediate ideas in chess (get your pieces out
before you do anything else) and the vocabulary is silent on it.

**User's request:** surface DEVELOPMENT as a plan — specifically an
IMMEDIATE-tier one (using the timing machinery already built: immediate /
developing / long-term) whenever a side has undeveloped minor pieces.

**Design sketch (not yet built):**
- **Detector**: minor pieces (knight/bishop) still sitting on their
  starting squares (White b1/c1/f1/g1, Black b8/c8/f8/g8) — cheap,
  direct, no geometry needed beyond piece-on-square identity.
- **Precondition/relevance gate**: this should only fire in the
  opening/early middlegame — by move 15-20 a piece still on its home
  square is usually a specific structural choice (a fianchetto slot,
  a piece deliberately held back), not a generic "develop" ask. Natural
  candidates: gate on `game_phase()` != "endgame"/"late-middlegame" (already
  in `suggest.py`), or on ply count directly, or simply let the engine/
  Maia gate handle it — if the banked lines don't actually develop that
  piece, the candidate won't confirm.
- **Plan family**: retrospective event = the piece leaves its home
  square (a simple snapshot diff, similar shape to `castle_kingside`'s
  square-based detection). Evidence tier: likely engine-contract like
  everything else this session — audit against the banked benchmark
  (engine-confirm % vs random floor) before shipping, per this session's
  standing methodology.
- **Naming detail** (matching this session's "name exact squares" pattern
  from castling/holes/isolani): the candidate should name which piece(s)
  are undeveloped and where they naturally want to go, not just say
  "develop your pieces" generically.

## 7. No general BISHOP IMPROVEMENT plan — routing is only computed for
   already-bad/entombed bishops (2026-07-22, user-defined)

**Where:** `weaknesses.py::bishop_escape_route()` is the only bishop-route
generator that exists, and it's gated on entombment — returns `None`/`[]`
for any bishop that isn't already classified bad. There's no analogue of
`strong_squares()`/`strong_outpost` (the knight version, built this
session) for bishops: nothing asks "is there a better diagonal for THIS
bishop, regardless of whether it's currently bad."

**What's wrong:** a perfectly fine bishop that's simply passive — could
redeploy to a more active diagonal, swing to a better square, or reroute
around its own structure — has no detector and no plan. We only reason
about bishops once they're already flagged bad/entombed; general
"improve this piece" reasoning doesn't exist for bishops the way
`strong_outpost` gives knights somewhere to go.

**User's proposed method:** precompute candidate bishop destination
squares/routes geometrically (regardless of current bishop quality), then
check the banked engine lines — does the bishop actually get routed to
any of those squares in an eval-equal line? Same verify-first shape as
everything else this session: geometry proposes, the bank confirms.

**Design sketch (not yet built):**
- **Route generation**: for each own bishop, BFS/diagonal-walk candidate
  squares it could reach (mirrors `bishop_escape_route`'s color-respecting
  diagonal BFS, but without the entombment precondition — run it for
  every bishop, not just bad ones). Candidate destinations plausibly
  filtered to "more active than current" (e.g. more legal diagonal moves
  from there, or a `strong_squares()`-style outpost check reused for
  bishops instead of just knights).
- **Verification**: same pattern as `strong_outpost` — check the banked
  engine PVs / Maia rollouts for whether the bishop actually lands on one
  of the candidate squares within the horizon; only surface if confirmed.
- **Relation to existing families**: this is NOT a replacement for
  `free_bad_bishop`/`exchange_bad_bishop`/`bishop_escape_route` (those
  stay specific to the bad-bishop precondition) — it's a broader,
  precondition-free "bishop improvement" family sitting alongside them,
  the way `strong_outpost` sits alongside `outpost_occupation` for
  knights.

## 8. No kingside/piece-based ATTACK plan is actually surfaced — `piece_attack`
   exists in the grammar but is orphaned (2026-07-22)

**Where:** `plan_diff.py`'s `piece_attack` family (retrospective detector:
3+ non-pawn pieces mass within distance 2 of a CASTLED opponent's king,
held for the tail, with no accompanying pawn storm on that wing — i.e.
a piece-based attack, not a pawn storm). Registered in `suggest.py`'s
`CANDIDATE_FAMILIES` ("PIECE ATTACK ON THE KING": {"piece_attack"}), so
`verify_plan` can check for it — but there is **no `cand()` call anywhere
in `build_menus()`** that ever proposes it. It can be detected
retrospectively in an already-played game, but the suggester never
surfaces it prospectively. Confirmed via grep: `suggest.py` mentions
`piece_attack` exactly once (the `CANDIDATE_FAMILIES` registration) and
nowhere else.

**Why it's been left alone:** finding 12's corpus-scale audit (94,289
anchors, the OLD pre-benchmark corpus scan) marked it "STARVED" —
precondition too rare to validate, not refuted. That verdict predates
this session's grammar changes and the 4,000-position benchmark; it may
or may not still hold. Also worth noting: as currently defined it isn't
kingside-SPECIFIC — it fires for whichever wing the opponent actually
castled to, not scoped the way `STORM`/`BREAK OPEN THE CENTER` are named.

**Not built this session per explicit user instruction** ("Don't build
it, add it known issue log") — deliberately deferred, not overlooked.

**When it's picked up:** re-audit `piece_attack`'s precondition
(opponent castled + 3+ attacking pieces) against the CURRENT
`benchmark_v1` banked lines (engine-confirm % vs random floor, same
methodology as every other family this session) before wiring a
`suggest.py` candidate — the STARVED verdict needs re-checking at the new
scale/grammar before trusting it either way, not assumed correct just
because the old scan said so.

## 9. No STRENGTHS section — the sheet only ever states liabilities
   (2026-07-22)

**Where:** `fact_sheet.py::build_fact_sheet()`. Confirmed via grep: the
sheet has `WEAKNESSES FOR WHITE` / `WEAKNESSES FOR BLACK` sections, and
nothing symmetric. Positive facts exist but are scattered, incidental,
and incomplete inside `POSITION READ` (bishop pair mention, passed-pawn
mention, space-edge mention) rather than collected into a dedicated,
per-side section the way weaknesses are.

**What's wrong:** a coaching sheet that only ever tells a student what's
wrong with their position, never what's going right for them, is
lopsided — and it's an easy thing for a narrating model to over-weight
("your position sounds terrible") when the actual facts include real
assets. It also means several things the pipeline ALREADY computes never
surface as a clean, named strength: `strong_squares()` (a real outpost
target even if not yet occupied), a bishop that ISN'T bad while the
opponent's corresponding bishop IS (the mirror image of `bad_bishop`,
already computed as a side effect of the EXCHANGE THE BAD BISHOP
candidate), a genuinely active/good rook (the inverse of
`passive_rooks`), connected/protected/outside passed pawns (currently
just a bare count in POSITION READ, no per-passer detail the way
WEAKNESSES names exact squares).

**Fix (not yet built):** a `STRENGTHS FOR WHITE` / `STRENGTHS FOR BLACK`
section, symmetric in structure to `_weakness_lines()`, built from data
already on hand where possible: bishop pair (already computed),
non-bad/good bishops when the opponent's corresponding-color bishop IS
bad, `strong_squares()` targets, space edge (already gated at >=6 for the
SIMPLIFY/AVOID TRADES advisories — reuse that threshold), passed pawn
detail (protected/outside/connected, named per pawn like weaknesses name
squares), majorities. Same "present-only, no negative lines" rule
WEAKNESSES already follows (finding 16) should apply symmetrically here.

## 10. `roll_maia()`'s Docker/gpu_bench import has no path wiring — likely
    silently returning None on every off-bank live query (2026-07-22,
    found while packaging)

**Where:** `chess_plans/verify.py::roll_maia()` does
`from gpu_bench import DockerBackend, rollout_gated` — a bare top-level
import of `research/gpu_benchmark/gpu_bench.py`. Nothing on the live hot path
(`fact_sheet.py::build_fact_sheet()` -> `verify.roll_maia()`) ever puts
`research/gpu_benchmark/` on `sys.path`, and `roll_maia()` wraps the whole call in
a bare `except Exception: return None` — so a missing/failing import
degrades silently to "no Maia data" rather than erroring.

**Evidence:** grep confirms zero `sys.path` references to `gpu_benchmark`
anywhere in `chess_plans/` or its callers. `research/gpu_benchmark/` is documented
in its own CLAUDE.md as a standalone kit meant to run on a separate GPU
box via batch shard files (`gpu_bench.py benchmark_v1.jsonl maia_shards/`),
not as an in-process live-query backend — this in-process usage from
`verify.py` looks like it was never actually exercised end-to-end (every
live-roll test this session likely hit the engine leg only, silently
losing the Maia leg).

**Fix (not yet built, needs a design decision, not a path patch):**
decide whether the live server's Maia leg should (a) shell out to a
small persistent Maia inference service the same way the engine leg
shells out to `engine_roll_helper.py`, or (b) vendor the minimal
`DockerBackend`/`rollout_gated` pieces directly into `chess_plans/` so
the package doesn't reach into `research/gpu_benchmark/`'s batch-job-oriented
code. Either way, `roll_maia()`'s silent `except Exception: return None`
should also log/flag the failure rather than swallow it, so a broken
Maia leg is visible instead of just quietly downgrading every fact sheet
to engine-only verification.

## 11. Campaign-scale plans (minority attack) never surface from rolled
    lines — the structure prior is the missing surfacing channel
    (2026-07-22, from the first live backend integration)

**Where:** `fact_sheet.py::_plan_lines` / `verify.py` — architecturally,
not a bug in either: the VERIFY gate can only confirm what appears inside
a rolled window, and campaign-scale plans don't.

**What's wrong:** on a textbook Carlsbad position (the backend's live
plans route), the sheet surfaced both bad bishops, the e5/e4 outposts,
the split majorities — and NOT the White minority attack, the signature
plan of the structure. This is the measured, expected behavior, not a
regression: finding 10 put the minority attack's line-window detector at
**lift 1.06 (near-random)** — it is a whole-phase campaign; even in
carlsbad:W GM futures it appears in only ~16% of windows (which is 20x
the base rate — the concentration lives in the STRUCTURE, not the
window). No horizon fixes this (40 plies was tried live: +4-5s, no
minority attack; horizon is 30 now). The same failure shape applies to
every campaign-tier plan.

**Current mitigation (backend-side, model memory):** the backend's
`PlansReadPrompt` gained a "The Structure" section — when the sheet's
STRUCTURE line names one, the narrating LLM recites textbook theory for
it from its own knowledge (the same carve-out as opening narration). On
the live Carlsbad test it correctly named the minority attack this way.
Works, but it's the model's memory, not our evidence.

**Fix (not yet built): surface campaign plans from the structure->plan
evidence table, not from rolled lines.** The data already exists —
`carlsbad_row.jsonl` (structure in 4.2% of GM games, launch 24%,
complete-given-launch 33%, score none 0.529 / launched 0.551 / completed
0.580) and the finding-10 structure->plan concentration table. Add a
`STRUCTURE PLANS` block to the fact sheet: when `classify()` names a
structure with an evidence-table row, state its tested campaign plan(s)
with the corpus reliability numbers, tagged as corpus-tier (like
SIMPLIFY/AVOID TRADES) rather than verify-tier — grounded fact instead
of model memory, and the "The Structure" prompt section can then cite it
instead of free-reciting. Prereq: stamp the evidence-table template
across more of the 30 structures (roadmap item 1).
